"""重機の包絡・離隔判定（engine/crane.py, engine/clearance.py）と停止ステップ生成（engine/steps.py）。"""
from engine.clearance import CONDITIONAL, NG, OK, evaluate
from engine.crane import Crane
from engine.energize import DEAD_GROUNDED, LIVE, energize
from engine.envelope import ClearanceTable, envelopes
from engine.steps import generate


def _env(topo, site, states, name="normal"):
    res = energize(topo, states[name])
    return envelopes(topo, site.layout, res, ClearanceTable.load())


def test_crane_sweep_has_parts_for_each_angle():
    c = Crane(base=(0, 0), slew_deg=(-10, 10))
    caps = c.sweep(5.0)
    assert [x["part"] for x in caps[:1]] == ["carrier"]
    assert sum(1 for x in caps if x["part"] == "boom") == 5
    tip = c.tip(0.0)
    assert tip[2] > c.pivot()[2]


def test_crane_far_from_everything_is_ok(topo, site, states):
    env = _env(topo, site, states)
    c = Crane(base=(5.0, 5.0), heading_deg=0, boom_len_m=8, boom_elev_deg=80, slew_deg=(-10, 10))
    out = evaluate(env, c)
    assert out["verdict"] == OK and out["ng_count"] == 0


def test_crane_near_live_bus_is_ng_and_names_conductor(topo, site, states):
    """220kV 母線の真下にブームを置くと不可。根拠に導体 ID・必要離隔・旋回角が入る。"""
    env = _env(topo, site, states)
    from synth.gen_site import P
    by = P["220"]["bus"]["y"]
    c = Crane(base=(60.0, by - 20.0), heading_deg=90, boom_len_m=22, boom_elev_deg=25, slew_deg=(-5, 5))
    out = evaluate(env, c)
    assert out["verdict"] == NG
    assert out["worst"]["required_m"] == 5.2 and "R2" in out["reasons"][0]
    assert out["worst"]["conductor_id"].startswith("220-")


def test_outage_removes_envelopes_and_changes_verdict(topo, site, states):
    """2号変圧器を停止すると、その一次まわりの包絡が消えて、そこに近いクレーンが可になる。"""
    from synth.gen_site import P
    x = next(x for (n, x, _) in P["220"]["banks"] if n == 2)
    c = Crane(base=(x + 10.0, P["220"]["tr_y"]), heading_deg=180, boom_len_m=9, boom_elev_deg=45, slew_deg=(-10, 10), hook_drop_m=1.0)
    before = evaluate(_env(topo, site, states, "normal"), c)
    after = evaluate(_env(topo, site, states, "tr2-outage"), c)
    assert before["verdict"] == NG and before["worst"]["conductor_id"] == "220-TR-2-HV"
    assert after["verdict"] in (OK, CONDITIONAL)


def test_steps_for_transformer_isolate_both_sides_and_ground(topo, site, states):
    r = generate(topo, states["normal"], ["TR-2"])
    assert r["ok"], r["problems"]
    titles = [s["title"] for s in r["steps"]]
    assert titles == ["遮断器を開放", "断路器を開放（両側）", "接地開閉器を投入"]
    ids1 = {o["id"] for o in r["steps"][0]["ops"]}
    assert "220-T2-CB" in ids1 and "66-D2-CB1" in ids1 and "66-D2-CB2" in ids1     # 1・1/2 は両隣の遮断器
    ids2 = {o["id"] for o in r["steps"][1]["ops"]}
    assert {"220-T2-BLS", "220-T2-LS", "66-TR-2-LS"} <= ids2
    res = energize(topo, r["steps"][2]["state"])
    assert res.errors == [] and res.state_of("TR-2") == DEAD_GROUNDED
    assert res.state_of("220-BUS-B") == LIVE and res.state_of("220-LINE-E1") == LIVE


def test_steps_for_bus_section_open_section_switches(topo, site, states):
    r = generate(topo, states["normal"], ["220-BUS-B"])
    assert r["ok"], r["problems"]
    ids2 = {o["id"] for o in r["steps"][1]["ops"]}
    assert {"220-SEC-AB", "220-SEC-BC"} <= ids2
    ids3 = {o["id"] for o in r["steps"][2]["ops"]}
    assert "220-BUS-B-ES" in ids3
    res = energize(topo, r["steps"][2]["state"])
    assert res.state_of("220-BUS-A") == LIVE and res.state_of("220-BUS-C") == LIVE and res.state_of("220-BUS-B") == DEAD_GROUNDED


def test_steps_do_not_ground_the_new_bay(topo, site, states):
    r = generate(topo, states["normal"], ["220-L1-CB"])
    assert r["ok"], r["problems"]
    assert "220-L1-CB" in {o["id"] for o in r["steps"][0]["ops"]}
    assert not any(o["id"].startswith("66-D6") for o in r["steps"][2]["ops"])


def test_steps_refuse_empty_or_unknown_targets(topo, states):
    """対象なし・存在しない対象では止める（空の手順を「通った」にしない）。"""
    for targets in ([], ["NO-SUCH-NODE"]):
        r = generate(topo, states["normal"], targets)
        assert r["ok"] is False and r["steps"] == [] and r["problems"], targets


def test_marginal_clearance_is_conditional_with_conditions(topo, site, states):
    """R6: 必要離隔は満たすが余裕が margin_m 未満なら「条件付き可」と条件。余裕の基準を 0 にすれば同じ配置が「可」になる。"""
    from engine.steps import generate
    st = generate(topo, states["normal"], ["TR-2"])
    final = st["steps"][-1]["state"]
    env = envelopes(topo, site.layout, energize(topo, final), ClearanceTable.load())
    c = Crane(base=(88.0, 72.0), heading_deg=0, boom_len_m=14, boom_elev_deg=55, slew_deg=(-50, 50), hook_drop_m=2)  # 画面の初期値で起伏 55°
    out = evaluate(env, c)
    assert out["verdict"] == CONDITIONAL
    assert 0 <= out["worst"]["margin_m"] < 0.5
    assert out["conditions"] and out["reasons"][0].startswith("R6")
    from engine.clearance import load_rules
    relaxed = evaluate(env, c, {**load_rules(), "margin_m": 0.0})
    assert relaxed["verdict"] == OK and relaxed["conditions"] == []
