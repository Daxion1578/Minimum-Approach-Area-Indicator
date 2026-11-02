"""開発環境の点検。すべて OK なら準備完了。NG には直し方を出す。

  python scripts/doctor.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
results: list[tuple[bool, str, str]] = []


def item(ok: bool, label: str, fix: str = "") -> None:
    results.append((ok, label, fix))


def main() -> int:
    v = sys.version_info
    item(v >= (3, 11), f"Python {v.major}.{v.minor}", "Python 3.11 以上を入れてください")

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    item(in_venv, "仮想環境で実行中", ".venv\\Scripts\\Activate.ps1 で有効にしてから実行してください")

    missing = [m for m in ["ezdxf", "fastapi", "uvicorn", "anthropic", "numpy", "trimesh", "jsonschema", "dotenv", "pytest"]
               if importlib.util.find_spec(m) is None]
    item(not missing, "依存パッケージ", f"pip install -r requirements.txt（不足: {', '.join(missing)}）")

    item(shutil.which("git") is not None, "git", "Git for Windows を入れてください")
    item(shutil.which("claude") is not None, "Claude Code", "公式クイックスタートの手順で Claude Code を入れてください")

    item("ANTHROPIC_API_KEY" not in os.environ, "環境変数 ANTHROPIC_API_KEY が未設定",
         "設定されていると Claude Code が API 課金で動きます。システムの環境変数から削除し、キーは .env の MAAI_ANTHROPIC_API_KEY に書いてください")

    env = ROOT / ".env"
    item(env.exists(), ".env がある", "copy .env.example .env")
    if env.exists():
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", ".env"], cwd=ROOT, capture_output=True).returncode == 0
        item(not tracked, ".env が git の追跡対象でない", "git rm --cached .env を実行してください")

    terms = ROOT / ".forbidden-terms.local.txt"
    n = 0
    if terms.exists():
        n = sum(1 for l in terms.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#"))
    item(n > 0, f"禁止語ファイル（{n} 語）", "notepad .forbidden-terms.local.txt で社名・事業所名・設備名などを1行1語で書いてください")

    hook = ROOT / ".git" / "hooks" / "pre-commit"
    item(hook.exists() and "MAAI" in hook.read_text(encoding="utf-8", errors="replace"), "git の pre-commit フック",
         "python scripts/install_git_hooks.py")

    settings = ROOT / ".claude" / "settings.json"
    try:
        hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {})
        ok = "PreToolUse" in hooks and "PostToolUse" in hooks
    except Exception:
        ok = False
    item(ok, "Claude Code のフック設定", ".claude/settings.json を確認してください")

    width = max(len(l) for _, l, _ in results)
    bad = 0
    for ok, label, fix in results:
        print(f"{'OK' if ok else 'NG'}  {label.ljust(width)}" + ("" if ok else f"  → {fix}"))
        bad += not ok
    print("\n準備完了です。" if not bad else f"\nNG が {bad} 件あります。")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
