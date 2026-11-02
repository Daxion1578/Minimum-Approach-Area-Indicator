"""PreToolUse フック: Claude Code が git commit / git push を実行する前に公開前チェックを走らせる。

問題があれば終了コード 2 で止め、理由を Claude Code に返す。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    cmd = (payload.get("tool_input") or {}).get("command", "")
    is_commit = re.search(r"\bgit\b[^;&|]*\bcommit\b", cmd)
    is_push = re.search(r"\bgit\b[^;&|]*\bpush\b", cmd)
    if not (is_commit or is_push):
        return 0
    if re.search(r"--no-verify\b|\s-n\b", cmd) and is_commit:
        print("--no-verify で公開前チェックを飛ばすコミットは禁止です。", file=sys.stderr)
        return 2

    mode = "--all" if is_push else "--staged"
    # `git add ... && git commit` の形では、add の前なので staged が空のことがある。push と同じく全体も見る。
    if is_commit and re.search(r"\bgit\b[^;&|]*\badd\b", cmd):
        mode = "--all"
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "public_safety_check.py"), mode],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        print(res.stdout + res.stderr, file=sys.stderr)
        print("公開前チェックに通るまでコミット・push しないでください。禁止語の内容は推測・表示しないこと。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
