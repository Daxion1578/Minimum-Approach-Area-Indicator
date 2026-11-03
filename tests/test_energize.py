"""課電判定のテスト（proto/ の 7 件を契約 §6 に移植したもの＋端子の約束）。

合成変電所 SITE-01（220/66kV・1・1/2 母線・変圧器 2 台、D4 は新設ベイ）を使う。
"""
from engine.energize import DEAD_GROUNDED, DEAD_UNGROUNDED, INVALID, LIVE, energize, live_edges
from engine.topology import Topology, TopologyError


def states_of(res, prefix):
    return {n: c.state for c in res.components for n in c.nodes if n.startswith(prefix)}


# ---------------------------------------------------------------- case 1
def test_case1_normal_everything_live_except_new_bay(topo, states):
    res = energize(topo, states["normal"])
    assert res.errors == []
    for c in res.components:
        for n in c.nodes:
            if n.startswith("220-D4-") and n not in ("220-D4-LSA.a", "220-D4-LSB.b"):
                assert c.state == DEAD_UNGROUNDED, (n, c.state)   # 新設ベイ：未接続・未接地
            else:
                assert c.state == LIVE, (n, c.state)
    # 母線は延長済みなので充電。新設ベイの区間にはカプセル（導体）がまだ無い
    assert res.state_of("220-BUS-A") == LIVE and res.state_of("220-BUS-B") == LIVE


# ---------------------------------------------------------------- case 2
def test_case2a_backfeed_through_transformer_is_invalid(topo, states):
    """220kV 側だけ切って接地すると、66kV 側から TR-2 を通って逆送され、充電部に接地を付けたことになる。"""
    res = energize(topo, states["tr2-outage-220-only"])
    assert res.state_of("220-D2-T2") == INVALID
    assert res.state_of("220-TR-2-HV") == INVALID
    assert res.state_of("66-TR-2-LV") == INVALID
    assert [e["code"] for e in res.errors] == ["live_grounded"]
    comp = res.component_of("220-D2-T2")
    assert comp.grounded_by == ["220-D2-T2-ES"]
    # 逆送経路：66kV 母線 → TR-2 → T2。66kV 側の電源が充電元に含まれる
    assert any(s.startswith("66-LINE-") for s in comp.live_sources), comp.live_sources
    # 66kV 母線経由で TR-1 にもつながるので、220kV の線路も同じ電位グループに入る
    assert any(s.startswith("220-LINE-") for s in comp.live_sources), comp.live_sources


def test_case2b_isolating_both_sides_gives_dead_grounded(topo, states):
    res = energize(topo, states["tr2-outage"])
    assert res.errors == []
    for n in ("220-D2-T2", "220-TR-2-HV", "66-TR-2-LV", "TR-2"):
        assert res.state_of(n) == DEAD_GROUNDED, n
    # 1・1/2 母線なので、同じダイヤの東線2L は CB1 経由で運転継続
    assert res.state_of("220-LINE-E2") == LIVE
    assert res.state_of("220-D2-T1") == LIVE
    # 母線は両方とも充電のまま
    assert res.state_of("220-BUS-A") == LIVE
    assert res.state_of("220-BUS-B") == LIVE
    # 66kV 母線も他の電源と TR-1 で充電のまま
    assert res.state_of("66-BUS-A") == LIVE
    # 開いた遮断器の両端子は別の成分: CB2 の a 側は充電、b 側は停電・未接地
    assert res.state_of("220-D2-CB2.a") == LIVE
    assert res.state_of("220-D2-CB2.b") == DEAD_UNGROUNDED


def test_case2c_grounding_a_live_bus_is_invalid(topo, site):
    res = energize(topo, site.state(0, "", {"220-BUS-A-ES": "closed"}))
    assert res.state_of("220-BUS-A") == INVALID
    assert "220-BUS-A" in res.invalid_ids


# ---------------------------------------------------------------- case 3
def test_case3_new_bay_connection_work(topo, site, states):
    """新設ベイ D4 の母線接続工事：ベイは停電・未接地、A/B 母線は充電のまま。D4 付近の充電導体は母線だけ。"""
    from synth.gen_site import P
    res = energize(topo, states["normal"])
    d4 = {n: s for n, s in states_of(res, "220-D4-").items() if n not in ("220-D4-LSA.a", "220-D4-LSB.b")}
    assert d4 and set(d4.values()) == {DEAD_UNGROUNDED}
    cfg = P["220"]
    x4 = cfg["x0"] + 3 * cfg["bay_pitch"]
    near = []
    for it in site.layout["items"]:
        if not it["id"].startswith("220-") or not it["primitives"]:
            continue
        if res.state_of(it["id"]) != LIVE:
            continue
        if any(abs(p["a"][0] - x4) <= cfg["bay_pitch"] / 2 or abs(p["b"][0] - x4) <= cfg["bay_pitch"] / 2
               for p in it["primitives"]):
            near.append(it["id"])
    assert set(near) == {"220-BUS-A", "220-BUS-B"}, near


def test_case3b_closing_bus_side_ls_energizes_first_section_only(topo, site):
    res = energize(topo, site.state(0, "", {"220-D4-LSA": "closed"}))
    assert res.state_of("220-D4-N1") == LIVE
    assert res.state_of("220-D4-N2") == DEAD_UNGROUNDED
    assert res.errors == []


# ---------------------------------------------------------------- 契約・端子の約束
def test_live_edges_exposed_only_excludes_enclosed(topo, states):
    res = energize(topo, states["normal"])
    all_live = live_edges(topo, res)
    exposed = live_edges(topo, res, exposed_only=True)
    assert len(exposed) < len(all_live)
    assert all(e.conductor == "bare" for e in exposed)
    exposed_ids = {e.id for e in exposed}
    assert all(e.conductor == "enclosed" for e in all_live if e.id not in exposed_ids)


def test_conservative_defaults_when_state_is_missing(topo):
    """state に書かれていないものは保守側: 開閉器 closed・接地 open・電源 live。"""
    res = energize(topo, None)
    assert res.errors == []
    assert res.state_of("220-D2-T2") == LIVE


def test_unknown_switch_in_state_is_reported(topo, site):
    res = energize(topo, site.state(0, "", {"220-D9-CB1": "open"}))
    assert [e["code"] for e in res.errors] == ["unknown_switch"]


def test_bare_switch_reference_assigns_a_then_b_and_rejects_third():
    base = {
        "schema_version": "0.1", "site_id": "SITE-09",
        "nodes": [{"id": "L", "kind": "source", "voltage_kv": 66}, {"id": "CB", "kind": "breaker", "voltage_kv": 66},
                  {"id": "B", "kind": "bus", "voltage_kv": 66}, {"id": "X", "kind": "terminal", "voltage_kv": 66}],
        "edges": [{"from": "L", "to": "CB", "conductor": "bare"}, {"from": "CB", "to": "B", "conductor": "bare"}],
    }
    t = Topology.from_dict(base)
    assert [(e.a, e.b) for e in t.edges] == [("L", "CB.a"), ("CB.b", "B")]
    res = energize(t, {"switches": {"CB": "open"}})
    assert res.state_of("L") == LIVE and res.state_of("B") == DEAD_UNGROUNDED
    bad = dict(base, edges=base["edges"] + [{"from": "CB", "to": "X", "conductor": "bare"}])
    try:
        Topology.from_dict(bad)
    except TopologyError:
        pass
    else:
        raise AssertionError("3本目の端子名なし参照は拒否されるべき")
