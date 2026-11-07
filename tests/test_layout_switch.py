"""有効な配置の切り替え（図面から起こした下書き ⇄ 合成データ）。切り替えは人の操作（API）でだけ起きる。"""
import copy

import pytest
from fastapi.testclient import TestClient

import server.app as appmod


@pytest.fixture()
def client():
    appmod.load_site.cache_clear()
    yield TestClient(appmod.app)
    appmod.load_site.cache_clear()


def _run(client, expect="truth"):
    site = client.get("/api/sites/SITE-01").json()
    assert site["layout_source"] == expect           # 既定は合成データ
    state = site["states"]["normal"]
    steps = client.post("/api/sites/SITE-01/steps", json={"targets": ["66-D1-CB1"], "state": state}).json()
    day = steps["state"]
    crane = {"base": [60, 20], "heading_deg": 90, "boom_len_m": 20, "boom_elev_deg": 60, "slew_deg": [-30, 40]}
    clr = client.post("/api/sites/SITE-01/clearance", json={"state": day, "crane": crane}).json()
    sel = client.post("/api/sites/SITE-01/select", json={"state": day, "pick_id": "66-D1-CB1"}).json()
    return steps, clr, sel


def test_draft_gives_same_results_as_truth(client):
    """同じ図面から起こした下書きを有効にしても、切る機器・クラス・離隔判定が合成データのときと同じ。"""
    s0, c0, k0 = _run(client)
    j = client.post("/api/ingest/layout", json={"sample": True}).json()
    r = client.post("/api/site/SITE-01/layout/use-draft",
                    json={"layout": j["layout"], "questions": j["questions"], "drawing_hash": j["drawing_hash"]})
    assert r.status_code == 200, r.text
    info = client.get("/api/site/SITE-01/layout/source").json()
    assert info["source"] == "drawing-draft" and info["drawing_hash"] == j["drawing_hash"]
    s1, c1, k1 = _run(client, expect="drawing-draft")
    assert s1["steps"] == s0["steps"]
    assert c1["clearance"]["verdict"] == c0["clearance"]["verdict"]
    assert c1["clearance"]["conditions"] == c0["clearance"]["conditions"]
    assert k1 == k0
    client.post("/api/site/SITE-01/layout/use-truth")
    assert client.get("/api/site/SITE-01/layout/source").json()["source"] == "truth"


def test_invalid_layout_is_400_and_nothing_switches(client):
    j = client.post("/api/ingest/layout", json={"sample": True}).json()
    bad = copy.deepcopy(j["layout"])
    bad["items"][0].pop("id")
    r = client.post("/api/site/SITE-01/layout/use-draft", json={"layout": bad})
    assert r.status_code == 400 and "契約" in r.json()["detail"]
    assert client.get("/api/site/SITE-01/layout/source").json()["source"] == "truth"
    assert client.post("/api/site/SITE-01/layout/use-draft", json={"layout": {}}).status_code == 400
