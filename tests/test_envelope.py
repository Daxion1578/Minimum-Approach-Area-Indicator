"""安全包絡（engine/envelope.py）のテスト。"""
from engine.energize import DEAD_GROUNDED, DEAD_UNGROUNDED, LIVE, energize
from engine.envelope import ClearanceTable, envelopes


def test_clearance_table_defaults():
    """既定はクレーン作業の目標値（電圧の段ごと）。段の間の電圧は上の段で見る（保守側）。"""
    t = ClearanceTable.load()
    assert t.clearance(0.2)[0] == 2.0
    assert t.clearance(6.6)[0] == 2.0
    assert t.clearance(22)[0] == 3.0
    assert t.clearance(66)[0] == 4.0
    assert t.clearance(154)[0] == 5.0
    assert t.clearance(220)[0] == 7.0    # 154kV と 275kV の間 → 275kV の段
    assert t.clearance(500)[0] == 11.0
    assert all(r.status == "要確認" for r in t.rows)


def test_reference_tables_keep_their_values():
    """比較用の基発759号と、第344条（有資格者の活線作業用、判定には使わない）も読める。"""
    k = ClearanceTable.load(table_id="kihatsu759")
    assert k.clearance(66)[0] == 2.2 and k.clearance(220)[0] == 5.2
    a = ClearanceTable.load(table_id="live-line-344")
    assert a.clearance(66)[0] == 0.5 and a.clearance(220)[0] == 1.6 and a.clearance(275)[0] == 2.0
    # 既定（目標値）は比較用の表より小さくならない
    t = ClearanceTable.load()
    for kv in (0.2, 6.6, 22, 66, 154, 220, 275, 500):
        assert t.clearance(kv)[0] >= k.clearance(kv)[0], kv
    for kv in (22, 66, 154, 220, 275, 500):
        assert k.clearance(kv)[0] >= a.clearance(kv)[0], kv


def test_envelope_radius_is_conductor_radius_plus_clearance(topo, site, states):
    res = energize(topo, states["normal"])
    env = envelopes(topo, site.layout, res)
    by_id = {}
    for e in env["envelopes"]:
        by_id.setdefault(e["conductor_id"], e)
    bus = by_id["220-BUS-A"]
    assert bus["voltage_kv"] == 220 and bus["clearance_m"] == 7.0
    assert bus["primitive"]["r"] == 0.03 + 7.0
    assert env["clearance_table_id"] == "default-jp"


def test_envelope_follows_energization_state(topo, site, states):
    res = energize(topo, states["tr2-outage"])
    assert res.state_of("220-TR-2-HV") == DEAD_GROUNDED
    ids_conservative = {e["conductor_id"] for e in envelopes(topo, site.layout, res)["envelopes"]}
    ids_strict = {e["conductor_id"] for e in envelopes(topo, site.layout, res, treat_ungrounded_as_live=False)["envelopes"]}
    assert "220-TR-2-HV" not in ids_conservative       # 接地済みの区間には包絡を作らない
    assert "220-LINE-E2" in ids_strict                 # 運転継続の線路には作る
    assert "220-T2-N1" in ids_conservative and "220-T2-N1" not in ids_strict  # 未接地は保守側でだけ
    assert res.state_of("220-T2-N1") == DEAD_UNGROUNDED


def test_enclosed_conductors_get_no_envelope(topo, site, states):
    res = energize(topo, states["normal"])
    ids = {e["conductor_id"] for e in envelopes(topo, site.layout, res)["envelopes"]}
    enclosed = {e.id for e in topo.edges if e.conductor == "enclosed"}
    assert not (ids & enclosed)
    assert res.state_of("TR-1") == LIVE
