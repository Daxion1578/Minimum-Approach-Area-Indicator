"""重機の包絡・離隔判定（engine/crane.py, engine/clearance.py）と停止ステップ生成（engine/steps.py）。"""
from engine.clearance import CONDITIONAL, DEFAULT_RULES, NG, OK, evaluate
from engine.crane import Crane
from engine.energize import LIVE, energize
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
    c2 = Crane(base=(0, 0), slew_deg=(-10, 10), boom_elev2_deg=70)
    assert sum(1 for x in c2.sweep(5.0) if x["part"] == "boom") == 10      # 起伏角が 2 つなら両方で掃引


def test_sweep_does_not_miss_approach_between_steps(topo, site, states):
    """刻みの間の最接近を見落とさない: 粗い刻みの判定は、細かい刻みの判定より近い（保守側）か同じ距離を返す。"""
    env = _env(topo, site, states)
    from synth.gen_site import P
    by = P["220"]["bus"]["y"]
    import math
    for base in ((60.0, by - 16.0), (47.0, by - 14.0), (70.0, by - 15.5)):
        c = Crane(base=base, heading_deg=90, boom_len_m=14, boom_elev_deg=40, slew_deg=(-60, 60))
        fine = min(h["distance_m"] for h in evaluate(env, c, {**DEFAULT_RULES, "slew_step_deg": 0.25})["hits"])
        coarse = min(h["distance_m"] for h in evaluate(env, c, {**DEFAULT_RULES, "slew_step_deg": 10.0})["hits"])
        assert coarse <= fine + 1e-6, (base, coarse, fine)
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
    assert out["worst"]["required_m"] == 7.0 and "R2" in out["reasons"][0]
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


def _opened(r):
    return {o["id"] for o in r["ops"]}


def test_breaker_target_opens_itself_and_both_neighbouring_disconnectors(topo, states):
    """遮断器を取り替える: 遮断器と両隣の断路器を切る。ほかは平常どおり。"""
    r = generate(topo, states["normal"], ["66-D1-CB1"])
    assert r["ok"], r["problems"]
    assert _opened(r) == {"66-D1-CB1", "66-D1-LSA", "66-D1-LS1B"}
    assert len(r["steps"]) == 1 and r["steps"][0]["title"] == "作業日の停止範囲"
    assert r["conditions"][0].startswith("作業する機器に電気が流れ込む端すべてに")   # 接地は条件として必ず書く
    res = energize(topo, r["state"])
    assert res.state_of("66-D1-CB1.a") != LIVE and res.state_of("66-D1-CB1.b") != LIVE
    assert res.state_of("66-BUS-A") == LIVE and res.state_of("TR-1") == LIVE


def test_line_side_disconnector_opens_breaker_and_bus_side_and_asks_remote_end(topo, states):
    """線路側の断路器を取り替える: 構内は遮断器と母線側断路器を切り、相手端の遮断器・断路器を切る条件を書く。"""
    r = generate(topo, states["normal"], ["220-L1-LS"])
    assert r["ok"], r["problems"]
    assert _opened(r) == {"220-L1-LS", "220-L1-CB", "220-L1-BLS"}
    assert any("相手端" in c for c in r["conditions"])
    assert r["state"]["sources"]["220-LINE-E1"] == "dead"
    assert energize(topo, r["state"]).state_of("220-BUS-A") == LIVE


def test_bus_side_disconnector_keeps_bus_live_and_asks_terminal_detach(topo, states):
    """母線側の断路器: 母線は止めず、母線側の端子の切り離しを条件にする。回路側は遮断器と次の断路器まで。"""
    r = generate(topo, states["normal"], ["220-T2-BLS"])
    assert r["ok"], r["problems"]
    assert {"220-T2-BLS", "220-T2-CB", "220-T2-LS"} <= _opened(r)
    assert any("切り離す" in c and "母線は充電のまま" in c for c in r["conditions"])
    res = energize(topo, r["state"])
    assert res.state_of("220-BUS-B") == LIVE and res.state_of("220-T2-BLS.b") != LIVE


def test_bus_section_opens_section_switches(topo, states):
    r = generate(topo, states["normal"], ["220-BUS-B"])
    assert r["ok"], r["problems"]
    assert {"220-SEC-AB", "220-SEC-BC"} <= _opened(r)
    res = energize(topo, r["state"])
    assert res.state_of("220-BUS-A") == LIVE and res.state_of("220-BUS-C") == LIVE and res.state_of("220-BUS-B") != LIVE


def test_steps_refuse_empty_or_unknown_targets(topo, states):
    """対象なし・存在しない対象では止める（空の手順を「通った」にしない）。"""
    for targets in ([], ["NO-SUCH-NODE"]):
        r = generate(topo, states["normal"], targets)
        assert r["ok"] is False and r["steps"] == [] and r["problems"], targets


def test_every_switch_transformer_bus_gets_a_dead_scope_without_errors(topo, states):
    """どの遮断器・断路器・変圧器・母線を対象にしても、対象が停電になり、誤り（充電部への接地）が出ない。
    閉じた接地開閉器は使わない（接地は作業手順で取る前提）。"""
    ids = [n for n, v in topo.nodes.items() if v.kind in ("transformer", "breaker", "disconnector", "bus")]
    assert len(ids) > 80
    for i in ids:
        r = generate(topo, states["normal"], [i])
        assert r["ok"], (i, r["problems"])
        res = energize(topo, r["state"])
        assert res.errors == [] and not res.invalid_ids, i
        assert not any(v == "closed" for k, v in r["state"]["switches"].items() if topo.nodes[k].kind == "earthing"), i


def test_marginal_clearance_is_conditional_with_conditions(topo, site, states):
    """R6: 必要離隔は満たすが余裕が margin_m 未満なら「条件付き可」と条件。
    同じ配置でも、余裕の基準を最小余裕より大きくすると条件付き可になる。"""
    from engine.clearance import load_rules
    from engine.steps import generate
    env = envelopes(topo, site.layout, energize(topo, states["normal"]), ClearanceTable.load())
    c = Crane(base=(5.0, 5.0), heading_deg=0, boom_len_m=8, boom_elev_deg=80, slew_deg=(-10, 10))
    out = evaluate(env, c)
    m = out["worst"]["margin_m"]
    assert out["verdict"] == OK and out["conditions"] == [] and m > 0.5
    strict = evaluate(env, c, {**load_rules(), "margin_m": m + 0.5})
    assert strict["verdict"] == CONDITIONAL and strict["conditions"] and strict["reasons"][0].startswith("R6")


def test_transformer_target_stops_its_own_bay_up_to_the_bus(topo, states):
    """変圧器を取り替える: 専用ベイ（遮断器 1 台）は母線の手前まで止める。共有の遮断器（1・1/2 母線）は平常どおり。"""
    r = generate(topo, states["normal"], ["TR-2"])
    assert r["ok"], r["problems"]
    assert _opened(r) == {"220-T2-CB", "220-T2-LS", "220-T2-BLS", "66-TR-2-LS"}
    res = energize(topo, r["state"])
    assert res.state_of("220-T2-CB.a") != LIVE and res.state_of("220-T2-CB.b") != LIVE   # 遮断器まわりも停電
    assert res.state_of("220-BUS-B") == LIVE                                              # 母線は運転継続
    assert r["state"]["switches"].get("66-D2-CB1", "closed") == "closed"                  # 共有の遮断器は入ったまま


def test_line_bay_target_stops_the_line_too(topo, states):
    """線路ベイの遮断器を取り替えるときは送電線ごと止める（相手端の条件）。1・1/2 母線の変圧器側の遮断器では送電線を止めない。"""
    from engine.steps import generate
    from engine.energize import energize
    g = generate(topo, states["normal"], ["220-L1-CB"])
    assert g["ok"] and g["state"]["sources"]["220-LINE-E1"] == "dead"
    assert any("相手端" in c and "東線1L" in c for c in g["conditions"])
    st = {c["state"] for c in energize(topo, g["state"]).to_dict()["components"] if "220-LINE-E1" in c["nodes"]}
    assert st and "live" not in st
    g66 = generate(topo, states["normal"], ["66-D1-CB1"])
    assert all("相手端" not in c for c in g66["conditions"])
