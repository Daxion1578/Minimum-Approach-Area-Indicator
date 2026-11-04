"""課電判定のテスト（proto/ の 7 件を契約 §6 に移植したもの＋端子の約束）。

合成変電所 SITE-01（220kV 単母線 3 区間・66kV 1・1/2 母線・変圧器 3 バンク、66kV D6 は新設予定）を使う。
"""
from engine.energize import DEAD_GROUNDED, DEAD_UNGROUNDED, INVALID, LIVE, energize, live_edges
from engine.topology import Topology, TopologyError


def states_of(res, prefix):
    return {n: c.state for c in res.components for n in c.nodes if n.startswith(prefix)}


NEW_BAY_BUS_ENDS = ("66-D6-LSA.a", "66-D6-LSB.b")   # 新設ダイヤの母線側端子は母線と同電位


# ---------------------------------------------------------------- case 1
def test_case1_normal_everything_live_except_new_bay(topo, states):
    res = energize(topo, states["normal"])
    assert res.errors == []
    for c in res.components:
        for n in c.nodes:
            if n.startswith("66-D6-") and n not in NEW_BAY_BUS_ENDS:
                assert c.state == DEAD_UNGROUNDED, (n, c.state)   # 新設ダイヤ：未接続・未接地
            else:
                assert c.state == LIVE, (n, c.state)
    for b in ("220-BUS-A", "220-BUS-B", "220-BUS-C", "66-BUS-A", "66-BUS-B"):
        assert res.state_of(b) == LIVE


# ---------------------------------------------------------------- case 2
def test_case2a_backfeed_through_transformer_is_invalid(topo, states):
    """220kV 側だけ切って接地すると、66kV 側から TR-2 を通って逆送され、充電部に接地を付けたことになる。"""
    res = energize(topo, states["tr2-outage-220-only"])
    assert res.state_of("220-TR-2-HV") == INVALID
    assert res.state_of("66-TR-2-LV") == INVALID
    assert [e["code"] for e in res.errors] == ["live_grounded"]
    comp = res.component_of("220-TR-2-HV")
    assert comp.grounded_by == ["220-TR-2-HV-ES"]
    # 逆送経路：66kV 母線 → TR-2 → 一次。66kV 側の電源が充電元に含まれる
    assert any(s.startswith("66-LINE-") for s in comp.live_sources), comp.live_sources
    # 66kV 母線経由で TR-1・TR-3 にもつながるので、220kV の線路も同じ電位グループに入る
    assert any(s.startswith("220-LINE-") for s in comp.live_sources), comp.live_sources
    # 遮断器と断路器の間の区間は切り離されたまま（接地なし）
    assert res.state_of("220-T2-N2") == DEAD_UNGROUNDED


def test_case2b_isolating_both_sides_gives_dead_grounded(topo, states):
    """両側で切り離して一次に接地: 変圧器まわりは dead_grounded、母線・他バンク・線路は運転継続。"""
    res = energize(topo, states["tr2-outage"])
    assert res.errors == []
    for n in ("220-TR-2-HV", "66-TR-2-LV", "TR-2"):
        assert res.state_of(n) == DEAD_GROUNDED, n
    assert res.state_of("220-T2-N1") == DEAD_UNGROUNDED     # 母線側断路器と遮断器の間（接地なし）
    for n in ("220-BUS-A", "220-BUS-B", "220-BUS-C", "220-LINE-E1", "220-LINE-E2", "220-TR-1-HV", "220-TR-3-HV", "66-BUS-A", "66-BUS-B"):
        assert res.state_of(n) == LIVE, n
    # 開いた遮断器の両側は別の成分
    assert res.state_of("220-T2-CB.a") == DEAD_UNGROUNDED and res.state_of("220-T2-CB.b") == DEAD_UNGROUNDED
    assert res.component_of("220-T2-CB.a") is not res.component_of("220-T2-CB.b")


def test_case2c_grounding_a_live_bus_is_invalid(topo, site):
    res = energize(topo, site.state(0, "", {"220-BUS-A-ES": "closed"}))
    assert res.state_of("220-BUS-A") == INVALID
    assert "220-BUS-A" in res.invalid_ids


def test_case2d_section_outage_keeps_outer_sections_live(topo, states):
    """中央セクション B の停止: B 区間と 2 号変圧器まわりは停電、A・C 区間は線路と変圧器で運転継続。"""
    res = energize(topo, states["sec-b-outage"])
    assert res.errors == []
    assert res.state_of("220-BUS-B") == DEAD_GROUNDED
    assert res.state_of("220-SEC-AB.b") == DEAD_GROUNDED and res.state_of("220-SEC-AB.a") == LIVE
    assert res.state_of("220-SEC-BC.a") == DEAD_GROUNDED and res.state_of("220-SEC-BC.b") == LIVE
    for n in ("220-BUS-A", "220-BUS-C", "220-LINE-E1", "220-LINE-E2", "220-TR-1-HV", "220-TR-3-HV", "66-BUS-A"):
        assert res.state_of(n) == LIVE, n
    # 2 号変圧器は両側で切り離したが接地していない → 保守側では充電扱いになる区間
    assert res.state_of("220-TR-2-HV") == DEAD_UNGROUNDED
    assert res.state_of("TR-2") == DEAD_UNGROUNDED
    # A 区間と C 区間は母線では切れているが、変圧器と 66kV 母線を介して同じ電位グループに入る（逆送の見落とし防止）
    assert res.component_of("220-BUS-A") is res.component_of("220-BUS-C")


# ---------------------------------------------------------------- case 3
def test_case3_new_bay_connection_work(topo, site, states):
    """新設ダイヤ D6 の母線接続工事：ダイヤは停電・未接地、1号/2号母線は充電のまま。D6 付近の機器高さの充電導体は母線だけ
    （引留鉄構の高さを通る変圧器二次の渡り線は別。クレーンの離隔は縦切り2で見る）。"""
    from synth.gen_site import P
    res = energize(topo, states["normal"])
    d6 = {n: s for n, s in states_of(res, "66-D6-").items() if n not in NEW_BAY_BUS_ENDS}
    assert d6 and set(d6.values()) == {DEAD_UNGROUNDED}
    cfg = P["66"]
    x6 = cfg["x0"] + 5 * cfg["bay_pitch"]
    near = []
    for it in site.layout["items"]:
        if not it["id"].startswith("66-") or not it["primitives"]:
            continue
        if res.state_of(it["id"]) != LIVE:
            continue
        if any((abs(p["a"][0] - x6) <= cfg["bay_pitch"] / 2 or abs(p["b"][0] - x6) <= cfg["bay_pitch"] / 2)
               and max(p["a"][2], p["b"][2]) <= cfg["busA"]["z"] + 0.5
               for p in it["primitives"]):
            near.append(it["id"])
    assert set(near) == {"66-BUS-A", "66-BUS-B"}, near


def test_case3b_closing_bus_side_ls_energizes_first_section_only(topo, site):
    res = energize(topo, site.state(0, "", {"66-D6-LSA": "closed"}))
    assert res.state_of("66-D6-N1") == LIVE
    assert res.state_of("66-D6-N2") == DEAD_UNGROUNDED
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
    assert res.state_of("220-TR-2-HV") == LIVE


def test_unknown_switch_in_state_is_reported(topo, site):
    res = energize(topo, site.state(0, "", {"220-T9-CB": "open"}))
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
