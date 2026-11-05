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
    """作業日の停止範囲 → 重機の選定 → 追加停止の比較 → 承認（重機の無い計画と不可は拒否）。"""
    site = client.get("/api/sites/SITE-01").json()
    normal = site["states"]["normal"]
    steps = client.post("/api/sites/SITE-01/steps", json={"targets": ["66-D1-CB1"], "state": normal}).json()
    assert steps["ok"] and len(steps["steps"]) == 1 and steps["conditions"]
    day = steps["state"]
    sel = client.post("/api/sites/SITE-01/select", json={"state": day, "pick_id": "66-D1-CB1"}).json()
    assert sel["ok"] and sel["chosen"]["verdict"] in ("ok", "conditional")
    assert sel["smaller_why_not"]                       # 一つ下のクラスが使えない理由
    crane = sel["chosen"]["crane"]
    cl = client.post("/api/sites/SITE-01/clearance", json={"state": day, "crane": crane}).json()["clearance"]
    assert cl["verdict"] == sel["chosen"]["verdict"]    # 選定の判定と、同じ配置の判定が一致する
    sld = client.post("/api/sites/SITE-01/sld", json={"state": day}).json()
    assert sld["svg"].startswith("<svg") and sld["marks"]["66-D1-CB1"]["pos"] == "open"
    assert sld["counts"]["dead"] > 0 and sld["counts"]["live"] > 0
    # 重機の無い計画・不可の計画は承認できない
    assert client.post("/api/sites/SITE-01/approve", json={"state": day}).status_code == 400
    bad = dict(crane, base=[34.0, 44.0], boom_elev_deg=30)
    assert client.post("/api/sites/SITE-01/approve", json={"state": normal, "crane": bad}).status_code == 400
    r = client.post("/api/sites/SITE-01/approve", json={"state": day, "crane": crane, "clearance": cl, "steps": steps})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["approval_hash"] and "step-1-sld.pdf" in j["files"] and not j.get("drawing_error")
    plan = client.get(f"/api/sites/SITE-01/approved/{j['name']}/plan.json").json()
    assert plan["approval_hash"] == j["approval_hash"] and plan["verdict"] == cl["verdict"]
    assert plan["conditions"][0].startswith("作業する機器に電気が流れ込む端すべてに")
    assert set(plan["inputs"]) >= {"topology_sha256", "layout_sha256", "clearance_table_sha256"}
