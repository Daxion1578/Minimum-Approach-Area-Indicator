"""git の pre-commit フックに公開前チェックを登録する（手でコミットするときの保険）。

  python scripts/install_git_hooks.py
"""
from __future__ import annotations

import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".git" / "hooks" / "pre-commit"

SCRIPT = """#!/bin/sh
# MAAI: 公開前チェック（scripts/install_git_hooks.py が作成）
if command -v python >/dev/null 2>&1; then PY=python; else PY=python3; fi
exec "$PY" scripts/public_safety_check.py --staged
"""


def main() -> int:
    if not (ROOT / ".git").is_dir():
        print("git リポジトリの直下で実行してください。")
        return 1
    if HOOK.exists() and "MAAI" not in HOOK.read_text(encoding="utf-8", errors="replace"):
        backup = HOOK.with_suffix(".bak")
        HOOK.rename(backup)
        print(f"既存の pre-commit を {backup.name} に退避しました。")
    HOOK.write_text(SCRIPT, encoding="utf-8", newline="\n")
    HOOK.chmod(HOOK.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("pre-commit フックを登録しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
