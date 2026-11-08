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
    k = next(c for c in load_classes() if c["id"] == "13t")
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


def test_weight_only_class_is_not_larger_than_chosen(topo, site, states):
    """重さと届く距離だけで決まるクラスは、離隔も見て選んだクラス以下。差は充電部を避けるための上乗せ。"""
    day = _day(topo, states, "66-D1-CB1")
    r = select(topo, site.layout, day, "66-D1-CB1", suggest_outage=False)
    ranks = [k["id"] for k in load_classes()]
    assert r["by_weight"] and r["chosen"]
    assert ranks.index(r["by_weight"]["class"]) <= ranks.index(r["chosen"]["class"])
    assert len(load_classes()) >= 10
    caps = [k["capacity_t"] for k in load_classes()]
    assert caps == sorted(caps)


def test_charts_grow_with_class_at_every_radius():
    """大きいクラスほど、同じ作業半径で吊れる重さが減らない（例示値の表の整合）。"""
    from engine.crane_select import capacity_t
    ks = load_classes()
    for r in (3, 5, 8, 10, 14, 18):
        vals = [capacity_t(k, r) for k in ks]
        nz = [v for v in vals if v > 0]
        assert nz == sorted(nz), (r, vals)


def test_cells_show_where_the_chosen_class_can_stand(topo, site, states):
    """据えてよい範囲: 選んだクラスのます目ごとの判定を返す。選んだ位置は「置ける」に入り、
    置けるます目の配置は承認と同じ判定（2° 刻み）でも不可にならない（ふるい分けは保守側）。"""
    day = _day(topo, states, "66-D1-CB1")
    r = select(topo, site.layout, day, "66-D1-CB1", suggest_outage=False)
    cells = r["chosen"]["cells"]
    ok = [c for c in cells if c["ok"]]
    assert ok and any(not c["ok"] for c in cells)
    assert all("crane" in c for c in ok) and all("crane" not in c for c in cells if not c["ok"])
    assert r["chosen"]["crane"]["base"][:2] in [[c["x"], c["y"]] for c in ok]
    assert all("cells" not in e for e in r["tried"][:-1])              # 使えないクラスのます目は返さない
    env = envelopes(topo, site.layout, energize(topo, day), ClearanceTable.load())
    for c in ok[:: max(1, len(ok) // 8)]:
        assert evaluate(env, Crane.from_dict(c["crane"]))["verdict"] != NG


def test_larger_classes_show_their_own_placement_area(topo, site, states):
    """一つ上・二つ上のクラスの範囲も返す（動線を考えて人が選ぶ）。置けるます目の配置はそのクラスのもの。"""
    day = _day(topo, states, "66-D1-CB1")
    r = select(topo, site.layout, day, "66-D1-CB1", suggest_outage=False)
    ids = [k["id"] for k in load_classes()]
    i = ids.index(r["chosen"]["class"])
    assert [x["class"] for x in r["larger"]] == ids[i + 1: i + 1 + len(r["larger"])] and r["larger"]
    for x in r["larger"]:
        assert all(c["crane"]["class"] == x["class"] for c in x["cells"] if c["ok"])


def test_select_at_matches_the_chosen_base_and_grows_when_moved_closer(topo, site, states):
    """人が動かした位置で一番小さい級を選び直す。選定で選んだ位置なら同じ級、置けるます目の配置は承認と同じ判定でも不可にならない。"""
    from engine.crane_select import select_at
    day = _day(topo, states, "66-D1-CB1")
    r = select(topo, site.layout, day, "66-D1-CB1", suggest_outage=False)
    ch = r["chosen"]
    a = select_at(topo, site.layout, day, "66-D1-CB1", tuple(ch["crane"]["base"]), set_xy=tuple(r["set"]))
    assert a["ok"] and a["chosen"]["class"] == ch["class"]
    env = envelopes(topo, site.layout, energize(topo, day), ClearanceTable.load())
    assert evaluate(env, Crane.from_dict(a["chosen"]["crane"]))["verdict"] != NG
    ranks = [k["id"] for k in load_classes()]
    # 50t 級の範囲（35t では置けないます目）へ動かせば、35t より大きい級になる
    big = next(x for x in r["larger"] if x["class"] != ch["class"])
    cell = next(c for c in big["cells"] if c["ok"] and not any(cc["ok"] and cc["x"] == c["x"] and cc["y"] == c["y"] for cc in ch["cells"]))
    b = select_at(topo, site.layout, day, "66-D1-CB1", (cell["x"], cell["y"]), set_xy=tuple(r["set"]))
    assert b["ok"] and ranks.index(b["chosen"]["class"]) > ranks.index(ch["class"])
    # 向きを渡すとその向きで判定する
    h = select_at(topo, site.layout, day, "66-D1-CB1", tuple(ch["crane"]["base"]), set_xy=tuple(r["set"]), heading_deg=ch["crane"]["heading_deg"] + 5)
    assert h["chosen"] is None or abs(h["chosen"]["crane"]["heading_deg"] - (ch["crane"]["heading_deg"] + 5)) < 1e-6


def test_reason_names_the_conductor_not_its_id(topo, site, states):
    """一つ下の級が使えない理由は、導体の ID（220-BUS-A）ではなく画面に出す名前（220kV 母線 A区間）で書く。"""
    day = _day(topo, states, "220-L1-CB")
    r = select(topo, site.layout, day, "220-L1-CB", weight_t=10, set_xy=(26, 108), unstoppable=["220-BUS-A"])
    why = r["smaller_why_not"]
    assert why and "220-BUS-A" not in why
    assert topo.nodes["220-BUS-A"].name in why and "まで近づく" in why
    ng = next(e for e in r["tried"] if not e["ok"] and e.get("binding_conductor"))
    assert ng["binding_conductor"] == "220-BUS-A"          # データには ID のまま残す（画面の文だけ名前にする）
