"""サーバ API を通しで（停止ステップ → 離隔 → 修正案 → 承認）。書き出しは一時ディレクトリに。"""
import json
import shutil

import pytest
from fastapi.testclient import TestClient

import server.app as appmod


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # 承認の書き出し先を一時ディレクトリへ（truth は本物を読む）
    real = appmod.SITES
    tmp = tmp_path / "sites"; (tmp / "SITE-01").mkdir(parents=True)
    # シンボリックリンクは Windows で特権が要るので、truth は複製する
    shutil.copytree(real / "SITE-01" / "truth", tmp / "SITE-01" / "truth")
    monkeypatch.setattr(appmod, "SITES", tmp)
    appmod.load_site.cache_clear()
    return TestClient(appmod.app)


def test_full_flow(client):
    site = client.get("/api/sites/SITE-01").json()
    normal = site["states"]["normal"]
    steps = client.post("/api/sites/SITE-01/steps", json={"targets": ["TR-2"], "state": normal}).json()
    assert steps["ok"] and len(steps["steps"]) == 3
    final = steps["steps"][-1]["state"]
    crane = {"base": [86.0, 69.0], "heading_deg": 180, "boom_len_m": 12, "boom_elev_deg": 45, "slew_deg": [-30, 40], "hook_drop_m": 2.0}
    before = client.post("/api/sites/SITE-01/clearance", json={"state": normal, "crane": crane}).json()["clearance"]
    after = client.post("/api/sites/SITE-01/clearance", json={"state": final, "crane": crane}).json()["clearance"]
    assert before["verdict"] == "ng" and after["verdict"] in ("ok", "conditional")
    prop = client.post("/api/sites/SITE-01/propose", json={"state": normal, "crane": crane}).json()
    assert any(c["verdict"] == "ok" and c["kind"] == "outage" for c in prop["candidates"])
    # 不可は承認できない
    r = client.post("/api/sites/SITE-01/approve", json={"state": normal, "crane": crane})
    assert r.status_code == 400
    r = client.post("/api/sites/SITE-01/approve", json={"state": final, "crane": crane, "clearance": after, "steps": steps})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["approval_hash"] and "step-3-sld.pdf" in j["files"] and not j.get("drawing_error")
    plan = client.get(f"/api/sites/SITE-01/approved/{j['name']}/plan.json").json()
    assert plan["approval_hash"] == j["approval_hash"] and plan["verdict"] == after["verdict"]
