"""ブラウザ版の入口。Pyodide（ブラウザの中で動く Python）から呼ぶ。

サーバ版 `server/app.py` の処理関数をそのまま呼ぶだけで、判定の中身は持たない（サーバ版と結果が必ず同じになる）。
画面の `fetch('/api/...')` は `web/browser-api.js` が横取りして、ここの `handle()` に回す。
Claude は呼ばない（ブラウザに API キーを置けないため）。全画面が規則の経路で動く。
"""
from __future__ import annotations

import json
import os
import re
import tempfile

os.environ["MAAI_OFFLINE"] = "1"

from fastapi import HTTPException, UploadFile  # noqa: E402
from fastapi.encoders import jsonable_encoder  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from server import app as A  # noqa: E402

_SITE = r"/api/sites/(?P<site>[A-Za-z0-9_-]+)"
ROUTES = [
    ("GET", r"/api/sites", lambda m, b: A.list_sites()),
    ("GET", _SITE, lambda m, b: A.get_site(m["site"])),
    ("POST", _SITE + "/energize", lambda m, b: A.post_energize(m["site"], A.EnergizeRequest(**b))),
    ("POST", _SITE + "/steps", lambda m, b: A.post_steps(m["site"], A.StepsRequest(**b))),
    ("POST", _SITE + "/clearance", lambda m, b: A.post_clearance(m["site"], A.ClearanceRequest(**b))),
    ("POST", _SITE + "/propose", lambda m, b: A.post_propose(m["site"], A.ClearanceRequest(**b))),
    ("POST", _SITE + "/approve", lambda m, b: A.post_approve(m["site"], A.ApproveRequest(**b))),
    ("POST", _SITE + "/explain", lambda m, b: A.post_explain(m["site"], A.ExplainRequest(**b))),
    ("POST", _SITE + "/select", lambda m, b: A.post_select(m["site"], A.SelectRequest(**b))),
    ("POST", _SITE + "/sld", lambda m, b: A.post_sld(m["site"], A.SldRequest(**b))),
    ("GET", r"/api/cranes", lambda m, b: A.get_cranes()),
    ("GET", r"/api/agent", lambda m, b: A.get_agent()),
    ("GET", r"/api/equipment", lambda m, b: A.get_equipment()),
]
_APPROVED = re.compile(_SITE + r"/approved/(?P<name>[A-Za-z0-9_-]+)/(?P<file>[A-Za-z0-9_.-]+)")


def _json(status: int, obj) -> dict:
    return {"status": status, "json": json.dumps(jsonable_encoder(obj), ensure_ascii=False)}


async def handle(method: str, path: str, body: str | None = None, pdf: bytes | None = None) -> dict:
    """1 回の問い合わせ。返り値は {"status", "json"} か、書き出したファイルなら {"status", "file"}（Pyodide の中のパス）。"""
    path = path.split("?", 1)[0]
    try:
        if method == "POST" and path == "/api/ingest":
            if pdf is None:
                return _json(400, {"detail": "PDF がない"})
            # メモリ上のファイルで渡す（ディスク扱いだとスレッドで読みに行き、ブラウザでは動かない）
            f = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
            f.write(bytes(pdf)); f.seek(0)
            return _json(200, await A.post_ingest(UploadFile(file=f, filename="upload.pdf")))
        m = _APPROVED.fullmatch(path)
        if method == "GET" and m:
            p = A.SITES / m["site"] / "approved" / m["name"] / m["file"]
            if not p.is_file():
                return _json(404, {"detail": "not found"})
            return {"status": 200, "file": str(p)}
        for meth, pat, fn in ROUTES:
            m = re.fullmatch(pat, path)
            if meth == method and m:
                return _json(200, fn(m, json.loads(body) if body else {}))
        return _json(404, {"detail": f"{method} {path} はブラウザ版に無い"})
    except HTTPException as e:
        return _json(e.status_code, {"detail": e.detail})
    except ValidationError as e:
        return _json(422, {"detail": e.errors()})
    except Exception as e:  # 画面が待ち続けないように、失敗は 500 で返す
        return _json(500, {"detail": f"{type(e).__name__}: {e}"})
