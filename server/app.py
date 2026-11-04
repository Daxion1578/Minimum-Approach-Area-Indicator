"""MAAI サーバ。

起動: uvicorn server.app:app --reload  → http://localhost:8000

API（すべて契約 contracts/ の形でやり取りする）:
  GET  /api/sites                      サイト一覧
  GET  /api/sites/{site_id}            topology / layout / states（状態の例）
  POST /api/sites/{site_id}/energize   body: {"state": state.json, "treat_ungrounded_as_live": true}
                                       → {"energization": §6.4, "envelope": §6.5（承認前）}
  POST /api/sites/{site_id}/steps      body: {"targets": ["TR-2"], "state": 通常状態} → 停止ステップ §6.8（段階ごとの state つき）
  POST /api/sites/{site_id}/clearance  body: {"state", "crane", "treat_ungrounded_as_live"} → {"energization","envelope","clearance" §6.7}
  POST /api/sites/{site_id}/propose    body: {"state", "crane"} → 修正案の候補（決定論。各候補は再判定済み）
  POST /api/sites/{site_id}/approve    body: {"state","crane","clearance","steps","approver"} → approved/ に書き出し、承認ハッシュ
  GET  /api/sites/{site_id}/approved/{name}/{file}   書き出した JSON / PDF
  POST /api/sites/{site_id}/explain    body: {"proposal", "clearance"} → 修正案の説明（Claude。呼べなければ定型文）
  POST /api/ingest                     multipart file=単線結線図 PDF（ベクター）→ 候補グラフ・topology 下書き・意味づけ（Claude）・精度（真値があるとき）
  GET  /api/agent                      Claude を呼べる状態か（キーの有無・オフライン設定）
画面: GET / → web/index.html、/web/* → 静的ファイル（three.js 同梱）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import hashlib
import time

from engine.clearance import evaluate
from engine.crane import Crane
from engine.energize import energize
from engine.envelope import ClearanceTable, envelopes
from engine.propose import propose
from engine.steps import generate
from engine.topology import Topology, TopologyError
from agent import client as agent_client
from agent.explain import explain as explain_proposal
from agent.structure import annotate
from ingest.pdf_sld import extract, to_topology

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


class StepsRequest(BaseModel):
    targets: list[str]
    state: dict | None = None


class ClearanceRequest(BaseModel):
    state: dict
    crane: dict
    treat_ungrounded_as_live: bool = True


class ApproveRequest(BaseModel):
    state: dict
    crane: dict | None = None
    clearance: dict | None = None
    steps: dict | None = None
    approver: str = "APPROVER-01"
    note: str = ""


def _topo(site: dict) -> Topology:
    try:
        return Topology.from_dict(site["topology"])
    except TopologyError as e:
        raise HTTPException(500, f"topology error: {e}") from e


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


@app.post("/api/sites/{site_id}/steps")
def post_steps(site_id: str, req: StepsRequest):
    site = load_site(site_id)
    base = req.state or site["states"].get("normal") or next(iter(site["states"].values()), {})
    return generate(_topo(site), base, req.targets)


@app.post("/api/sites/{site_id}/clearance")
def post_clearance(site_id: str, req: ClearanceRequest):
    site = load_site(site_id)
    topo = _topo(site)
    res = energize(topo, req.state)
    env = envelopes(topo, site["layout"], res, ClearanceTable.load(), req.treat_ungrounded_as_live)
    out = evaluate(env, Crane.from_dict(req.crane))
    return {"energization": res.to_dict(), "envelope": env, "clearance": out}


@app.post("/api/sites/{site_id}/propose")
def post_propose(site_id: str, req: ClearanceRequest):
    site = load_site(site_id)
    return propose(_topo(site), site["layout"], req.state, Crane.from_dict(req.crane), conservative=req.treat_ungrounded_as_live)


@app.post("/api/sites/{site_id}/approve")
def post_approve(site_id: str, req: ApproveRequest):
    """承認: 判定が可／条件付き可であることをもう一度確かめてから書き出す。暦日は入れない（相対時刻だけ）。"""
    site = load_site(site_id)
    topo = _topo(site)
    res = energize(topo, req.state)
    if res.errors:
        raise HTTPException(400, "課電判定に誤りがある状態は承認できない: " + "; ".join(e["message"] for e in res.errors))
    env = envelopes(topo, site["layout"], res, ClearanceTable.load(), True)
    verdict = None
    if req.crane:
        out = evaluate(env, Crane.from_dict(req.crane))
        verdict = out["verdict"]
        if verdict == "ng":
            raise HTTPException(400, "離隔が不可の計画は承認できない: " + out["reasons"][0])
    name = f"plan-{int(time.monotonic() * 1000) % 100000000:08d}"
    out_dir = SITES / site_id / "approved" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": "0.1", "site_id": site_id, "approver": req.approver, "note": req.note, "verdict": verdict,
               "state": req.state, "crane": req.crane, "clearance": req.clearance, "steps": req.steps,
               "envelope_count": len(env["envelopes"])}
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    h = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    payload["approval_hash"] = h
    (out_dir / "plan.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "envelope.json").write_text(json.dumps(env, ensure_ascii=False, indent=1), encoding="utf-8")
    files = ["plan.json", "envelope.json"]
    try:
        from synth.step_drawings import write_step_drawings
        files += write_step_drawings(site, req.steps, req.state, out_dir)
    except Exception as e:  # 図面が出せなくても承認は成立させる（理由は返す）
        payload["drawing_error"] = str(e)
    rel = str(out_dir.relative_to(ROOT)) if ROOT in out_dir.parents else str(out_dir)
    return {"name": name, "approval_hash": h, "files": files, "dir": rel, "drawing_error": payload.get("drawing_error")}


@app.get("/api/sites/{site_id}/approved/{name}/{file}")
def get_approved(site_id: str, name: str, file: str):
    p = SITES / site_id / "approved" / name / file
    if not p.exists() or ".." in name or ".." in file:
        raise HTTPException(404, "not found")
    return FileResponse(p)


class ExplainRequest(BaseModel):
    proposal: dict
    clearance: dict


@app.post("/api/sites/{site_id}/explain")
def post_explain(site_id: str, req: ExplainRequest):
    return explain_proposal(req.proposal, req.clearance)


@app.get("/api/agent")
def get_agent():
    return {"available": agent_client.available(), "models": {k: agent_client.model_for(k) for k in ("structure", "propose")}}


@app.post("/api/ingest")
async def post_ingest(file: UploadFile):
    """単線結線図 PDF → 候補グラフ → topology 下書き。合成変電所の図面なら真値と突き合わせた精度も返す。"""
    import tempfile
    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data); tmp = Path(f.name)
    try:
        cand = extract(tmp)
        topo = to_topology(cand)
        notes = annotate(cand)
        ev = None
        truth = SITES / "SITE-01" / "truth" / "topology.json"
        if truth.exists():
            try:
                from scripts.run_eval import evaluate as run_eval
                ev = run_eval(tmp, truth)
            except Exception as e:   # 真値と違う図面なら比較できない。それは誤りではない
                ev = {"error": str(e)}
    finally:
        tmp.unlink(missing_ok=True)
    return {"candidate": {k: cand[k] for k in ("nets", "switches", "transformers", "lines", "buses", "loads", "questions", "stats", "page_size_mm")},
            "topology": topo, "annotation": notes, "eval": ev}


@app.get("/api/equipment")
def get_equipment():
    """機器の外形寸法（synth/equipment.py）。3D が図面と同じ寸法で形を作るため。"""
    from synth.equipment import EQUIP, GANTRY, LINE_GANTRY_220, LOADS, TOWER_220, TRANSFORMER
    return {"equip": {str(k): v for k, v in EQUIP.items()}, "transformer": TRANSFORMER, "gantry": GANTRY,
            "line_gantry_220": LINE_GANTRY_220, "tower_220": TOWER_220, "loads": LOADS}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/web", StaticFiles(directory=WEB), name="web")
