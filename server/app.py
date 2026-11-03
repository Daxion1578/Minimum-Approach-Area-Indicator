"""MAAI サーバ。

起動: uvicorn server.app:app --reload  → http://localhost:8000

API（すべて契約 contracts/ の形でやり取りする）:
  GET  /api/sites                      サイト一覧
  GET  /api/sites/{site_id}            topology / layout / states（状態の例）
  POST /api/sites/{site_id}/energize   body: {"state": state.json, "treat_ungrounded_as_live": true}
                                       → {"energization": §6.4, "envelope": §6.5（承認前）}
画面: GET / → web/index.html、/web/* → 静的ファイル（three.js 同梱）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine.energize import energize
from engine.envelope import ClearanceTable, envelopes
from engine.topology import Topology, TopologyError

ROOT = Path(__file__).resolve().parents[1]
SITES = ROOT / "data" / "sites"
WEB = ROOT / "web"

app = FastAPI(title="MAAI", version="0.1")


def _read(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def load_site(site_id: str) -> dict:
    d = SITES / site_id / "truth"
    if not (d / "topology.json").exists():
        raise HTTPException(404, f"site {site_id} not found")
    states = {p.stem: _read(p) for p in sorted((d / "states").glob("*.json"))} if (d / "states").is_dir() else {}
    return {"site_id": site_id, "topology": _read(d / "topology.json"), "layout": _read(d / "layout.json"), "states": states}


class EnergizeRequest(BaseModel):
    state: dict
    treat_ungrounded_as_live: bool = True


@app.get("/api/sites")
def list_sites():
    return [{"site_id": p.name, "name": _read(p / "truth" / "topology.json").get("name", p.name)}
            for p in sorted(SITES.iterdir()) if (p / "truth" / "topology.json").exists()]


@app.get("/api/sites/{site_id}")
def get_site(site_id: str):
    return load_site(site_id)


@app.post("/api/sites/{site_id}/energize")
def post_energize(site_id: str, req: EnergizeRequest):
    site = load_site(site_id)
    try:
        topo = Topology.from_dict(site["topology"])
    except TopologyError as e:
        raise HTTPException(500, f"topology error: {e}") from e
    res = energize(topo, req.state)
    env = envelopes(topo, site["layout"], res, ClearanceTable.load(), req.treat_ungrounded_as_live)
    return {"energization": res.to_dict(), "envelope": env}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/web", StaticFiles(directory=WEB), name="web")
