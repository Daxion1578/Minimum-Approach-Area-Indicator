"""修正案の候補（§7.7）。不可／条件付き可のとき、決定論で候補を作って一つずつ再判定する。

候補の種類:
  move      クレーンのベースを 2m ずつ四方へ（最大 3 歩）
  slew      旋回範囲を、最悪の角度を避けるように狭める
  elev      ブームの起伏角を上げる（先端が内側に寄る）
  outage    最悪の導体を含む機器（ベイ）を追加で停止する（停止ステップを生成して状態を差し替える）
Claude の役割はこの候補を説明し、順位づけし、人が選ぶのを助けること。候補の採否・判定値はすべてここ（決定論）で決まる。
"""
from __future__ import annotations

from copy import deepcopy

from engine.clearance import NG, OK, evaluate
from engine.crane import Crane
from engine.energize import energize
from engine.envelope import ClearanceTable, envelopes
from engine.steps import generate
from engine.topology import Topology


def _eval(topo, layout, state, crane, table, conservative=True):
    res = energize(topo, state)
    env = envelopes(topo, layout, res, table, conservative)
    return evaluate(env, crane), res


def propose(topo: Topology, layout: dict, state: dict, crane: Crane, max_candidates: int = 8,
            conservative: bool = True) -> dict:
    table = ClearanceTable.load()
    base_out, _ = _eval(topo, layout, state, crane, table, conservative)
    cands: list[dict] = []
    if base_out["verdict"] == OK:
        return {"baseline": base_out["verdict"], "candidates": [], "note": "すでに可。修正案は不要"}
    worst = base_out["worst"]

    def add(kind: str, title: str, new_crane: Crane, new_state: dict | None = None, extra: dict | None = None):
        out, _ = _eval(topo, layout, new_state or state, new_crane, table, conservative)
        cands.append({"kind": kind, "title": title, "verdict": out["verdict"], "verdict_ja": out["verdict_ja"],
                      "min_distance_m": out["worst"]["distance_m"] if out["worst"] else None,
                      "required_m": out["worst"]["required_m"] if out["worst"] else None,
                      "margin_m": out["worst"]["margin_m"] if out["worst"] else None,
                      "reasons": out["reasons"], "conditions": out["conditions"],
                      "crane": new_crane.to_dict(), "state": new_state, **(extra or {})})

    # move: 最悪の導体から遠ざかる向きを優先して四方へ
    px, py = worst["p_crane"][0], worst["p_crane"][1]
    kx, ky = worst["p_conductor"][0], worst["p_conductor"][1]
    away = (px - kx, py - ky)
    dirs = sorted([(1, 0), (-1, 0), (0, 1), (0, -1)], key=lambda d: -(d[0] * away[0] + d[1] * away[1]))
    for dx, dy in dirs[:2]:
        for k in (1, 2, 3):
            c = deepcopy(crane); c.base = (crane.base[0] + dx * 2.0 * k, crane.base[1] + dy * 2.0 * k)
            lab = {(1, 0): "東", (-1, 0): "西", (0, 1): "北", (0, -1): "南"}[(dx, dy)]
            add("move", f"ベースを{lab}へ {2 * k}m", c)
            if cands[-1]["verdict"] == OK:
                break
    # slew: 最悪の角度側を切る
    if worst["slew_deg"] is not None:
        lo, hi = crane.slew_deg; w = worst["slew_deg"]
        if abs(w - hi) <= abs(w - lo):
            new = (lo, max(lo + 5.0, w - 15.0))
        else:
            new = (min(hi - 5.0, w + 15.0), hi)
        c = deepcopy(crane); c.slew_deg = new
        add("slew", f"旋回を {new[0]:+.0f}°〜{new[1]:+.0f}° に制限", c)
    # elev: 起伏角を上げる
    for d in (10.0, 20.0):
        c = deepcopy(crane); c.boom_elev_deg = min(85.0, crane.boom_elev_deg + d)
        add("elev", f"ブームの起伏角を {c.boom_elev_deg:.0f}° に上げる", c)
        if cands[-1]["verdict"] == OK:
            break
    # outage: 最悪の導体の機器を追加停止
    target = _owner_equipment(topo, worst["conductor_id"])
    if target:
        st = generate(topo, state, [target])
        if st["ok"]:
            add("outage", f"{topo.nodes[target].name or target} を追加で停止（接地まで）", crane, st["steps"][-1]["state"],
                {"steps": [{"n": s["n"], "title": s["title"], "ops": s["ops"]} for s in st["steps"]], "target": target})
    order = {OK: 0, "conditional": 1, NG: 2}
    cands.sort(key=lambda c: (order[c["verdict"]], c["kind"] == "outage", -(c["margin_m"] or -9)))
    return {"baseline": base_out["verdict"], "baseline_worst": worst, "candidates": cands[:max_candidates]}


def _owner_equipment(topo: Topology, conductor_id: str) -> str | None:
    """導体 ID（ノードか辺）から、停止の対象にする機器を決める。母線なら母線区間、変圧器まわりなら変圧器、それ以外はその区間のベイの遮断器。"""
    n = topo.nodes.get(conductor_id)
    if n is None:
        for e in topo.edges:
            if e.id == conductor_id:
                n = topo.node_of(e.a)
                break
    if n is None:
        return None
    if n.kind == "bus":
        return n.id
    if "-TR-" in n.id:
        return "TR-" + n.id.split("-TR-")[1].split("-")[0]
    if n.kind == "source":
        return n.id + "-LS" if (n.id + "-LS") in topo.nodes else None
    # 同じベイの遮断器
    if n.bay:
        for m in topo.nodes.values():
            if m.bay == n.bay and m.kind == "breaker":
                return m.id
    return n.id
