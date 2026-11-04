"""Claude 層と図面取込: 呼べないときも同じ形で返る／マスクが名前を外に出さない／取込の精度が下がっていない。"""
import os
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "data/sites/SITE-01/drawings/SITE-01_sld.pdf"


def test_mask_replaces_names_but_keeps_generic_words():
    from agent.mask import Mask
    m = Mask()
    out = m.text("東線1L を止める。合成変電所の1号母線は充電。線路側断路器")
    assert "東線1L" not in out and "合成変電所" not in out
    assert "1号母線" in out and "線路側断路器" in out
    assert m.unmask_text(out).startswith("東線1L")


def test_mask_obj_recurses():
    from agent.mask import Mask
    o = Mask().obj({"a": ["北変電所", {"b": "港線2L"}], "n": 3})
    assert o["a"][0].startswith("SITE-") and o["a"][1]["b"].startswith("LINE-") and o["n"] == 3


def test_structure_offline_fallback(monkeypatch):
    monkeypatch.setenv("MAAI_OFFLINE", "1")
    from agent.structure import annotate
    from ingest.pdf_sld import extract
    a = annotate(extract(PDF))
    assert a["source"] == "rules" and len(a["labels"]) > 100
    assert all(l["kind"] in ("breaker", "disconnector", "earthing") for l in a["labels"])


def test_explain_offline_fallback(monkeypatch):
    monkeypatch.setenv("MAAI_OFFLINE", "1")
    from agent.explain import explain
    prop = {"candidates": [{"title": "ベースを東へ 6m", "kind": "move", "verdict": "ok", "verdict_ja": "可", "min_distance_m": 6.1, "required_m": 5.2, "margin_m": 0.9}]}
    ex = explain(prop, {"verdict_ja": "不可", "reasons": []})
    assert ex["source"] == "rules" and ex["items"][0]["title"] == "ベースを東へ 6m" and "再判定は 可" in ex["items"][0]["explain"]


def test_ingest_endpoint_matches_truth(monkeypatch):
    monkeypatch.setenv("MAAI_OFFLINE", "1")
    from server.app import app
    c = TestClient(app)
    with PDF.open("rb") as f:
        r = c.post("/api/ingest", files={"file": ("sld.pdf", f, "application/pdf")})
    assert r.status_code == 200
    j = r.json()
    ev = j["eval"]
    assert ev["adjacency"]["precision"] >= 0.99 and ev["adjacency"]["recall"] >= 0.9
    assert ev["numbers"]["found"] >= 130 and ev["kinds"]["ok"] == ev["kinds"]["of"]
    assert j["topology"]["nodes"] and j["annotation"]["source"] in ("rules", "claude")


def test_agent_status_endpoint():
    from server.app import app
    r = TestClient(app).get("/api/agent")
    assert r.status_code == 200 and "available" in r.json()
