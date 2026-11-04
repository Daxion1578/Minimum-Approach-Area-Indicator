"""修正案の候補（engine/propose.py）。候補の判定値は、その候補を engine にかけ直した結果と一致しなければならない。"""
from engine.clearance import NG, OK, evaluate
from engine.crane import Crane
from engine.energize import DEAD_GROUNDED, energize
from engine.envelope import ClearanceTable, envelopes
from engine.propose import propose
from engine.steps import generate

# 画面の初期値（docs/demo-plan.md）。段階 3 で不可、起伏角 65° で可になる位置
DEMO = dict(base=(88.0, 72.0), heading_deg=0, boom_len_m=14, boom_elev_deg=45, slew_deg=(-50, 50), hook_drop_m=2)
ORDER = {OK: 0, "conditional": 1, NG: 2}


def _stage3(topo, states):
    st = generate(topo, states["normal"], ["TR-2"])
    assert st["ok"], st["problems"]
    return st["steps"][-1]["state"]


def _reeval(topo, site, state, crane):
    env = envelopes(topo, site.layout, energize(topo, state), ClearanceTable.load())
    return evaluate(env, crane)


def test_no_candidates_when_already_ok(topo, site, states):
    far = Crane(base=(-500.0, -500.0), boom_len_m=10)
    r = propose(topo, site.layout, states["normal"], far)
    assert r["baseline"] == OK and r["candidates"] == []


def test_demo_crane_gets_ok_candidates_sorted_ok_first(topo, site, states):
    state = _stage3(topo, states)
    r = propose(topo, site.layout, state, Crane(**DEMO))
    assert r["baseline"] == NG
    keys = [ORDER[c["verdict"]] for c in r["candidates"]]
    assert keys == sorted(keys)
    assert any(c["kind"] == "elev" and c["crane"]["boom_elev_deg"] == 65 and c["verdict"] == OK for c in r["candidates"])


def test_every_candidate_verdict_matches_independent_reevaluation(topo, site, states):
    state = _stage3(topo, states)
    r = propose(topo, site.layout, state, Crane(**DEMO))
    assert r["candidates"]
    for c in r["candidates"]:
        out = _reeval(topo, site, c["state"] or state, Crane.from_dict(c["crane"]))
        assert out["verdict"] == c["verdict"], c["title"]


def test_outage_candidate_grounds_its_target(topo, site, states):
    state = _stage3(topo, states)
    r = propose(topo, site.layout, state, Crane(**DEMO))
    outs = [c for c in r["candidates"] if c["kind"] == "outage"]
    assert outs, "追加停止の候補が出ていない"
    for c in outs:
        res = energize(topo, c["state"])
        assert res.errors == [] and res.state_of(c["target"]) == DEAD_GROUNDED
