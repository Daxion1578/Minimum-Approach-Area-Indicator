"""重機の選定（engine/crane_select.py）。選んだ配置は、承認と同じ判定でも同じ答えになること。"""
from engine.clearance import NG, evaluate
from engine.crane import Crane
from engine.crane_select import capacity_t, load_classes, select
from engine.energize import energize
from engine.envelope import ClearanceTable, envelopes
from engine.steps import generate


def _day(topo, states, target):
    st = generate(topo, states["normal"], [target])
    assert st["ok"], st["problems"]
    return st["state"]


def test_capacity_uses_the_far_side_of_the_chart():
    k = load_classes()[0]
    assert capacity_t(k, 3.0) == k["chart"][0][1]
    assert capacity_t(k, 3.1) == k["chart"][1][1]      # 表の間は遠い側（小さい方）の値
    assert capacity_t(k, 999) == 0.0


def test_selection_is_smallest_class_that_passes_and_is_reproducible(topo, site, states):
    day = _day(topo, states, "66-D1-CB1")
    r = select(topo, site.layout, day, "66-D1-CB1")
    assert r["ok"]
    ch = r["chosen"]
    ranks = [k["id"] for k in load_classes()]
    assert all(not e["ok"] and e["why_not"] for e in r["tried"][:-1])     # 小さいクラスは使えない理由つき
    assert r["tried"][-1] is ch and ranks.index(ch["class"]) == len(r["tried"]) - 1
    env = envelopes(topo, site.layout, energize(topo, day), ClearanceTable.load())
    again = evaluate(env, Crane.from_dict(ch["crane"]))
    assert again["verdict"] == ch["verdict"] != NG                      # 同じ配置を承認と同じ判定にかけても同じ
    assert ch["crane"]["boom_len_m"] in next(k for k in load_classes() if k["id"] == ch["class"])["boom_m"]


def test_extra_outage_makes_a_smaller_class_possible(topo, site, states):
    """邪魔をしている充電部を止めれば、より小さいクラスで置ける（費用の比較）。止めた状態の答えも再現できる。"""
    day = _day(topo, states, "66-D1-CB1")
    r = select(topo, site.layout, day, "66-D1-CB1")
    wo = r["with_outage"]
    assert wo and wo["chosen"], wo
    ranks = [k["id"] for k in load_classes()]
    assert ranks.index(wo["chosen"]["class"]) < ranks.index(r["chosen"]["class"])
    env = envelopes(topo, site.layout, energize(topo, wo["state"]), ClearanceTable.load())
    assert evaluate(env, Crane.from_dict(wo["chosen"]["crane"]))["verdict"] == wo["chosen"]["verdict"]


def test_heavier_load_never_gets_a_smaller_class(topo, site, states):
    day = _day(topo, states, "220-L1-LS")
    light = select(topo, site.layout, day, "220-L1-LS", weight_t=0.5, suggest_outage=False)
    heavy = select(topo, site.layout, day, "220-L1-LS", weight_t=12.0, suggest_outage=False)
    ranks = [k["id"] for k in load_classes()]
    assert light["ok"]
    if heavy["ok"]:
        assert ranks.index(heavy["chosen"]["class"]) >= ranks.index(light["chosen"]["class"])


def test_transformer_body_has_no_example_weight(topo, site, states):
    r = select(topo, site.layout, states["normal"], "TR-2")
    assert r["ok"] is False and "重さ" in r["problems"][0]
