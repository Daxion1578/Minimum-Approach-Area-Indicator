"""ブラウザ版の入口（server/browser.py）が、サーバ版と同じ答えを返すこと。"""
import asyncio
import json
import shutil

from fastapi.testclient import TestClient

import server.app as appmod
from server import browser

CRANE = {"base": [88, 72], "heading_deg": 0, "boom_len_m": 14, "boom_elev_deg": 45, "slew_deg": [-50, 50],
         "hook_drop_m": 2, "load": {"w": 2.0, "d": 2.0, "h": 2.5}}


def call(method, path, body=None, pdf=None):
    r = asyncio.run(browser.handle(method, path, json.dumps(body) if body is not None else None, pdf))
    return r["status"], (json.loads(r["json"]) if "json" in r else r["file"])


def test_same_answers_as_server(tmp_path, monkeypatch):
    real = appmod.SITES
    (tmp_path / "SITE-01").mkdir()
    shutil.copytree(real / "SITE-01" / "truth", tmp_path / "SITE-01" / "truth")
    monkeypatch.setattr(appmod, "SITES", tmp_path)
    appmod.load_site.cache_clear()
    c = TestClient(appmod.app)

    s, sites = call("GET", "/api/sites")
    assert s == 200 and sites == c.get("/api/sites").json()
    s, agent = call("GET", "/api/agent")
    assert s == 200 and agent["available"] is False      # ブラウザ版は Claude を呼ばない
    s, eq = call("GET", "/api/equipment")
    assert s == 200 and eq == c.get("/api/equipment").json()

    normal = call("GET", "/api/sites/SITE-01")[1]["states"]["normal"]
    s, st = call("POST", "/api/sites/SITE-01/steps", {"targets": ["TR-2"], "state": normal})
    assert s == 200 and st == c.post("/api/sites/SITE-01/steps", json={"targets": ["TR-2"], "state": normal}).json()
    final = st["steps"][-1]["state"]

    body = {"state": final, "crane": CRANE}
    s, cl = call("POST", "/api/sites/SITE-01/clearance", body)
    assert s == 200 and cl["clearance"] == c.post("/api/sites/SITE-01/clearance", json=body).json()["clearance"]
    assert cl["clearance"]["verdict"] == "ng"

    s, pr = call("POST", "/api/sites/SITE-01/propose", body)
    assert s == 200 and pr == c.post("/api/sites/SITE-01/propose", json=body).json()

    s, bad = call("POST", "/api/sites/SITE-01/approve", body)
    assert s == 400 and "不可" in bad["detail"]

    pick = next(x for x in pr["candidates"] if x["kind"] == "elev" and x["crane"]["boom_elev_deg"] == 65)
    s, a = call("POST", "/api/sites/SITE-01/approve", {"state": final, "crane": pick["crane"], "steps": st})
    assert s == 200 and any(f.endswith(".pdf") for f in a["files"])
    s, f = call("GET", f"/api/sites/SITE-01/approved/{a['name']}/{a['files'][-1]}")
    assert s == 200 and f.endswith(a["files"][-1])
    assert call("GET", f"/api/sites/SITE-01/approved/{a['name']}/..%2Fx")[0] == 404
    appmod.load_site.cache_clear()


def test_ingest_and_unknown_route():
    pdf = (appmod.SITES / "SITE-01" / "drawings" / "SITE-01_sld.pdf").read_bytes()
    s, j = call("POST", "/api/ingest", pdf=pdf)
    assert s == 200 and j["eval"]["numbers"]["found"] == 136
    assert call("POST", "/api/ingest")[0] == 400
    assert call("GET", "/api/nothing")[0] == 404
    assert call("POST", "/api/sites/SITE-01/clearance", {"state": {}})[0] == 422
