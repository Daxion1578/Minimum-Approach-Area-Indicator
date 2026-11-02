"""PostToolUse フック: engine/ や contracts/ を編集したら pytest を走らせる。

失敗したら終了コード 2 で、失敗内容を Claude Code に返す（直すまで先へ進ませない）。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WATCHED = ("engine/", "contracts/", "tests/")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in {"Edit", "Write", "MultiEdit"}:
        return 0
    path = (payload.get("tool_input") or {}).get("file_path", "")
    try:
        rel = Path(path).resolve().relative_to(ROOT).as_posix()
    except Exception:
        return 0
    if not rel.startswith(WATCHED):
        return 0
    if not (ROOT / "tests").is_dir():
        return 0
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "--no-header"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if res.returncode == 5:  # テストが1本も無い
        return 0
    if res.returncode != 0:
        tail = "\n".join((res.stdout + res.stderr).splitlines()[-40:])
        print(f"{rel} の編集後にテストが失敗しました。直してから次へ進んでください。\n{tail}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
