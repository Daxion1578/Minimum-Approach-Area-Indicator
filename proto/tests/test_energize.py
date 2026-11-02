"""
充停電判定のテスト。

実行:
  python3 -m pytest tests/ -q        # pytest があれば
  python3 tests/test_energize.py     # 無ければ素の実行
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from energize import energize, LIVE, DEAD_G, DEAD_U, FAULT, live_conductors  # noqa: E402
import gen_model  # noqa: E402

MODEL = gen_model.build()


def states_of(res, prefix):
    return {k: v for k, v in res.node_state.items() if k.startswith(prefix)}


# ---------------------------------------------------------------- case 1
def test_case1_normal_everything_live_except_new_bay():
    res = energize(MODEL)
    assert res.faults == []
    for nid, s in res.node_state.items():
        if nid.startswith("220_D4_"):
            assert s == DEAD_U, (nid, s)      # 新設ベイ：未接続・未接地
        else:
            assert s == LIVE, (nid, s)
    # 新設ベイには導体がまだ無い。母線は延長済みなので充電導体として存在する
    assert not any(c["node"].startswith("220_D4_") for c in MODEL["conductors"])
    assert all(res.conductor_state[c["id"]] == LIVE for c in MODEL["conductors"] if c["type"] == "bus")


# ---------------------------------------------------------------- case 2
def _d2_tr2_isolation_220_only():
    """D2 の TR2 引出点(T2)を 220kV 側だけで切り離して接地する。66kV 側は触らない。"""
    return {
        "switches": {
            "220_D2_CB2": "open", "220_D2_LS2B": "open",
            "220_D2_CB3": "open", "220_D2_LS3A": "open",
        },
        "earth_switches": {"220_D2_T2_ES": "closed"},
    }


def test_case2a_backfeed_through_transformer_is_detected_as_fault():
    """220kV側だけ切って接地すると、66kV側から TR2 を通って逆送され、充電部に接地を付けたことになる。"""
    res = energize(MODEL, _d2_tr2_isolation_220_only())
    assert "220_D2_T2" in res.faults
    assert res.node_state["220_TR2_HV"] == FAULT
    assert res.node_state["66_TR2_LV"] == FAULT
    # 逆送経路：66kV 母線 → TR2 → T2。66kV 側の電源が T2 の充電元に含まれる
    srcs = res.live_sources_by_node["220_D2_T2"]
    assert any(s.startswith("SRC_66_") for s in srcs), srcs
    # 66kV 母線経由で TR1 にもつながるので、結果として 220kV 線路も同じ電位グループに入る
    assert any(s.startswith("SRC_220_") for s in srcs), srcs


def test_case2b_isolating_both_sides_gives_dead_grounded():
    st = _d2_tr2_isolation_220_only()
    st["switches"]["66_TR2_66_LS"] = "open"   # 66kV 側の TR2 断路器も開く
    res = energize(MODEL, st)
    assert res.faults == []
    assert res.node_state["220_D2_T2"] == DEAD_G
    assert res.node_state["220_TR2_HV"] == DEAD_G
    assert res.node_state["66_TR2_LV"] == DEAD_G
    # 1・1/2 母線なので、同じダイヤの Fable線1L は CB1 経由で運転継続
    assert res.node_state["220_FABLE1L"] == LIVE
    assert res.node_state["220_D2_T1"] == LIVE
    # 母線は両方とも充電のまま
    assert res.node_state["220_BUSA"] == LIVE
    assert res.node_state["220_BUSB"] == LIVE
    # 66kV 母線も他の電源と TR1 で充電のまま
    assert res.node_state["66_BUSA"] == LIVE


def test_case2c_grounding_a_live_bus_is_a_fault():
    res = energize(MODEL, {"earth_switches": {"220_BUSA_ES": "closed"}})
    assert "220_BUSA" in res.faults


# ---------------------------------------------------------------- case 3
def test_case3_new_bay_connection_work():
    """新設 GIS ベイ(D4)の母線接続工事：ベイは停電・未接地、A/B 母線は充電のまま。"""
    res = energize(MODEL)
    d4 = states_of(res, "220_D4_")
    assert d4 and set(d4.values()) == {DEAD_U}
    live = live_conductors(MODEL, res)
    # D4 の x 範囲（x0 + 3*pitch ± pitch/2）に入る充電導体は母線のみ
    cfg = gen_model.P["220"]
    x4 = cfg["x0"] + 3 * cfg["bay_pitch"]
    near = [c for c in live if c["node"].startswith("220_")
            and any(abs(p[0] - x4) <= cfg["bay_pitch"] / 2 for p in c["polyline"])]
    assert near, "D4 付近に充電導体（延長された母線）があるはず"
    assert {c["type"] for c in near} == {"bus"}
    # 母線接地を付けない限り、D4 付近の充電部は消えない
    assert {c["node"] for c in near} == {"220_BUSA", "220_BUSB"}


def test_case3b_closing_bus_side_ls_energizes_first_section_only():
    res = energize(MODEL, {"switches": {"220_D4_LSA": "closed"}})
    assert res.node_state["220_D4_n1"] == LIVE
    assert res.node_state["220_D4_n2"] == DEAD_U
    assert res.faults == []


# ---------------------------------------------------------------- misc
def test_model_validates_against_schema_if_jsonschema_available():
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return
    schema = json.load(open(ROOT / "schema" / "substation.schema.json", encoding="utf-8"))
    jsonschema.validate(MODEL, schema)


if __name__ == "__main__":
    import inspect
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if fails else 0)
