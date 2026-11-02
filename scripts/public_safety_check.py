"""公開前の安全チェック。

コミット・push の前に、公開リポジトリに出してはいけないものが含まれていないかを調べる。
見つかったら終了コード 1 で止める。標準ライブラリだけで動く。

  python scripts/public_safety_check.py --staged   # git add 済みのファイル（pre-commit 用）
  python scripts/public_safety_check.py --all      # 追跡中の全ファイル（push 前）

禁止語はリポジトリ直下の .forbidden-terms.local.txt に1行1語で書く（コミットされない）。
検出結果には禁止語そのものを表示しない（ログやClaudeの文脈に残さないため）。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_FILE = ROOT / ".forbidden-terms.local.txt"
MEDIA_ALLOW_FILE = ROOT / ".public-media-allow.txt"  # 合成と確認済みの写真・動画・PDF（1行1パス、コミットする）
MAX_BYTES = 5 * 1024 * 1024

BLOCKED_SUFFIXES = {".dwg", ".xdw", ".xbd", ".pem", ".key", ".p12", ".pfx"}
BLOCKED_NAMES = {".env"}
BLOCKED_NAME_PATTERNS = [re.compile(r"\.local\.")]
ALLOWED_NAME_PATTERNS = [re.compile(r"\.local\.example\.")]

SECRET_PATTERNS = [
    ("Anthropic APIキー", re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")),
    ("OpenAI系APIキー", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("GitHubトークン", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("AWSアクセスキー", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("秘密鍵", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("キーの直書き", re.compile(r"(?i)(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]")),
]

# 日本付近の緯度経度の組（構内ローカル座標は地図と結び付けない。§12）
LATLON = re.compile(r"\b(2[4-9]|3\d|4[0-5])\.\d{4,}\s*[, ]\s*(12[2-9]|13\d|14[0-6])\.\d{4,}\b")

TEXT_SUFFIXES = {
    ".py", ".md", ".txt", ".json", ".csv", ".js", ".mjs", ".html", ".css", ".toml",
    ".yaml", ".yml", ".ini", ".cfg", ".svg", ".dxf", ".example", ".gitignore", ".ps1", ".sh",
}

SELF_EXEMPT = {"scripts/public_safety_check.py"}  # 検出パターン自体を含むため秘密情報の検査から外す


def git_files(staged: bool) -> list[str]:
    if staged:
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    else:
        # 追跡中に加えて、未追跡で ignore されていないもの（次に add されうるもの）も見る
        cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        sys.exit(2)
    return sorted({line for line in out.stdout.splitlines() if line.strip()})


def read_staged_or_worktree(rel: str, staged: bool) -> bytes | None:
    if staged:
        out = subprocess.run(["git", "show", f":{rel}"], cwd=ROOT, capture_output=True)
        return out.stdout if out.returncode == 0 else None
    p = ROOT / rel
    return p.read_bytes() if p.is_file() else None


def normalize(s: str) -> str:
    return unicodedata.normalize("NFKC", s).casefold()


def load_forbidden() -> list[str]:
    if not FORBIDDEN_FILE.exists():
        return []
    terms = []
    for line in FORBIDDEN_FILE.read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t and not t.startswith("#"):
            terms.append(normalize(t))
    return terms


def load_media_allow() -> set[str]:
    if not MEDIA_ALLOW_FILE.exists():
        return set()
    return {l.strip() for l in MEDIA_ALLOW_FILE.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}


def check(files: list[str], staged: bool, terms: list[str]) -> list[str]:
    problems: list[str] = []
    media_allow = load_media_allow()
    for rel in files:
        name = Path(rel).name
        suffix = Path(rel).suffix.lower()
        allowed_name = any(p.search(name) for p in ALLOWED_NAME_PATTERNS)
        if name in BLOCKED_NAMES or suffix in BLOCKED_SUFFIXES or (
            any(p.search(name) for p in BLOCKED_NAME_PATTERNS) and not allowed_name
        ):
            problems.append(f"{rel}: 公開してはいけない種類のファイルです")
            continue

        data = read_staged_or_worktree(rel, staged)
        if data is None:
            continue
        if len(data) > MAX_BYTES:
            problems.append(f"{rel}: {len(data) // 1024}KB と大きすぎます（5MB 超）。実データや動画が混ざっていないか確認してください")
            continue
        if suffix in {".jpg", ".jpeg", ".png", ".heic", ".mp4", ".mov", ".pdf"}:
            if rel not in media_allow:
                problems.append(f"{rel}: 写真・動画・PDF です。合成で作ったものか確認し、問題なければ .public-media-allow.txt にパスを1行追加して出所を docs/decisions.md に書いてください")
            continue
        if suffix not in TEXT_SUFFIXES and name not in {"LICENSE", "CLAUDE.md"}:
            continue

        text = data.decode("utf-8", errors="replace")
        if rel not in SELF_EXEMPT:
            for label, pat in SECRET_PATTERNS:
                if pat.search(text):
                    problems.append(f"{rel}: {label}らしき文字列があります")
            if LATLON.search(text):
                problems.append(f"{rel}: 緯度経度らしき数値の組があります（構内ローカル座標だけを使う）")

        if terms:
            norm = normalize(text)
            for lineno, line in enumerate(norm.splitlines(), 1):
                if any(t in line for t in terms):
                    problems.append(f"{rel}:{lineno}: 禁止語に一致する語があります（語は表示しません）")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="git add 済みのファイルを調べる（既定）")
    g.add_argument("--all", action="store_true", help="追跡中と、未追跡で ignore されていない全ファイルを調べる")
    args = ap.parse_args()

    staged = not args.all
    terms = load_forbidden()
    files = git_files(staged)
    problems = check(files, staged, terms)
    if not terms:
        print("注意: .forbidden-terms.local.txt が無いか空です。社名・設備名の検査は行っていません（docs/setup.md §3）。")
    if problems:
        print("公開前チェックで止めました。直してからもう一度実行してください。")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"公開前チェック OK（{len(files)} ファイル）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
