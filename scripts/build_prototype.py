"""試作画面を組み立てる: web/prototype.src.html に合成変電所の JSON を埋め込み、web/prototype.html を書き出す。

使い方: python scripts/build_prototype.py
できた web/prototype.html はダブルクリックで開ける（three.js は CDN から読むのでネット接続が要る）。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web" / "prototype.src.html"
OUT = ROOT / "web" / "prototype.html"
SITE = ROOT / "proto" / "data" / "substation_fictional.json"


def main() -> int:
    site = json.loads(SITE.read_text(encoding="utf-8"))
    payload = json.dumps(site, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = SRC.read_text(encoding="utf-8").replace("/*__SITE_JSON__*/", payload)
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
