"""重機の選定（§7.9）。吊る 2 点と重さから、離隔を守れる一番小さいクレーン（＝一番安い）と据付位置を選ぶ。

考え方: ブームの先端は「更新する設備の真上」と「資材置場の真上」に来る。2 点と重さが決まれば、要るクレーンの大きさが決まる。
  1. クラス（data/tables/cranes.json。例示値・要確認）を小さい順に試す。
  2. 構内を網の目で据付位置を試す。機器の基礎・鉄構の柱から、アウトリガーの張り出し＋1m 離れていること。
  3. 2 点に届くこと（最短のブーム長で、起伏角 25〜80°、フックの高さが足りる）。
  4. 遠い方の作業半径での定格総荷重 ≧ 吊る重さ＋フック＋吊具。
  5. 2 点の間の旋回（短い方の円弧）を、両端の起伏角の両方で掃引し、充電部の離隔を保つこと（engine/clearance.py と同じ判定）。
答え: 全部を満たす一番小さいクラスと、その中で余裕が最大の位置。一つ下のクラスが使えない理由。
どのクラスでも置けないときは、邪魔をしている充電部を追加で止めた場合（§7.6 の規則）を計算し、「止めれば何級で置けるか」を出す。
判定はすべて決定論。Claude はここに関与しない。
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from engine.clearance import NG, OK, evaluate, load_rules
from engine.crane import Crane, spec_of
from engine.energize import energize
from engine.envelope import ClearanceTable, envelopes
from engine.geometry import capsule_gap
from engine.topology import Topology

ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "data" / "tables" / "cranes.json"
FENCE = (0.0, 0.0, 135.0, 125.0)     # 構内（合成変電所の基準点 P1・P2 と同じ範囲）
GRID_M = 3.0
ELEV_MIN, ELEV_MAX = 25.0, 80.0
SCREEN_STEP_DEG = 6.0                 # ふるい分けの刻み（刻みの間は半径の上乗せで含める。保守側）


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads(TABLE.read_text(encoding="utf-8"))


def load_classes() -> list[dict]:
    return sorted(_table()["classes"], key=lambda c: c["rank"])


def capacity_t(k: dict, radius_m: float) -> float:
    """作業半径での定格総荷重。表の間は「遠い側の値」を使う（保守側）。表より遠ければ 0。"""
    for r, t in k["chart"]:
        if radius_m <= r:
            return t
    return 0.0


def lift_item(topo: Topology, nid: str) -> dict | None:
    n = topo.nodes.get(nid)
    if n is None:
        return None
    kv = int(n.voltage_kv or 0) if n.voltage_kv else (220 if nid.startswith("220") else 66)
    return _table()["lift_items"].get(f"{n.kind}-{kv}")


def pick_point(layout: dict, nid: str) -> tuple[float, float, float] | None:
    for it in layout["items"]:
        if it["id"] == nid and it.get("at"):
            return tuple(float(v) for v in it["at"])
    return None


def _obstacles(layout: dict) -> list[tuple[float, float]]:
    """据付の邪魔になる地上の点（機器の位置、鉄構の柱）。"""
    pts = [(it["at"][0], it["at"][1]) for it in layout["items"] if it.get("at")]
    for st in layout.get("structures", []):
        for pr in st.get("primitives", []):
            a, b = pr["a"], pr["b"]
            if min(a[2], b[2]) < 3.0 and abs(a[0] - b[0]) < 0.1 and abs(a[1] - b[1]) < 0.1:
                pts.append((a[0], a[1]))
    return pts


def _wires_2d(layout: dict) -> list[tuple[float, float, float, float]]:
    """架線・母線など導体の平面への投影（資材置場をその下に置かない）。"""
    segs = []
    for it in layout["items"]:
        for pr in it.get("primitives", []):
            segs.append((pr["a"][0], pr["a"][1], pr["b"][0], pr["b"][1]))
    return segs


def _dist_seg(x, y, s) -> float:
    ax, ay, bx, by = s
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / L2))
    return math.hypot(x - ax - t * vx, y - ay - t * vy)


def default_laydown(layout: dict, pick: tuple[float, float, float]) -> tuple[float, float]:
    """資材置場の既定: 吊る点から 8m 以上離れ、機器・柱から 6m 以上、導体の真下から 6m 以上空いた、いちばん近い網の目。"""
    obs = _obstacles(layout)
    wires = _wires_2d(layout)
    best = None
    x0, y0, x1, y1 = FENCE
    y = y0 + 4.0
    while y <= y1 - 4.0:
        x = x0 + 4.0
        while x <= x1 - 4.0:
            d = math.hypot(x - pick[0], y - pick[1])
            if d >= 8.0 and all(math.hypot(x - ox, y - oy) >= 6.0 for ox, oy in obs)                     and all(_dist_seg(x, y, w) >= 6.0 for w in wires):
                if best is None or d < best[0]:
                    best = (d, x, y)
            x += 2.0
        y += 2.0
    return (best[1], best[2]) if best else (pick[0] + 10.0, pick[1])


def _ang(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dy, dx))


def _norm(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def _prefilter(env_list: list[dict], pivot, reach: float, az_lo: float, az_hi: float, extra: float, near: float) -> list[dict]:
    """旋回の円弧の近くにある包絡だけを残す（速さのため。距離の判定そのものは capsule_gap で行う）。"""
    px, py = pivot[0], pivot[1]
    out = []
    for e in env_list:
        a, b = e["primitive"]["a"], e["primitive"]["b"]
        ax, ay, bx, by = a[0] - px, a[1] - py, b[0] - px, b[1] - py
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, -(ax * vx + ay * vy) / L2))
        cx, cy = ax + t * vx, ay + t * vy
        dmin = math.hypot(cx, cy)
        r = e["primitive"]["r"] + extra
        if dmin > reach + r:
            continue
        if dmin < near + r:
            out.append(e); continue
        angs = [_ang(ax, ay), _ang(bx, by), _ang(cx, cy)]
        delta = math.degrees(math.asin(min(1.0, r / max(dmin, 0.1))))
        mid = (az_lo + az_hi) / 2.0
        half = (az_hi - az_lo) / 2.0 + delta
        rel = [_norm(x - mid) for x in angs]
        if min(rel) <= half and max(rel) >= -half or any(abs(x) <= half for x in rel) \
                or (max(rel) - min(rel) > 180.0):
            out.append(e)
    return out


def _worst(env_list: list[dict], caps: list[dict]):
    worst = None
    for env in env_list:
        pr = env["primitive"]
        cond_r = pr["r"] - env["clearance_m"]
        for cc in caps:
            gap, _, _ = capsule_gap(cc["a"], cc["b"], cc["r"], pr["a"], pr["b"], cond_r)
            m = gap - env["clearance_m"]
            if worst is None or m < worst[0]:
                worst = (m, env["conductor_id"], env["voltage_kv"], env["clearance_m"], gap)
    return worst


def _try_cell(k: dict, base, pick, setp, need_t: float, load: dict, hook_need_z: float, env_list: list[dict], step: float):
    """1 つの据付位置で、届く・吊れる・離隔の順に確かめる。戻り値 (理由, crane, worst)。理由 None なら置ける。"""
    spec = spec_of(k)
    mid_az = _ang(pick[0] - base[0], pick[1] - base[1])
    az2 = _ang(setp[0] - base[0], setp[1] - base[1])
    heading = _norm(mid_az + _norm(az2 - mid_az) / 2.0)
    c = Crane(base=base, heading_deg=heading, spec=spec, crane_class=k["id"], hook_drop_m=_table()["hook_drop_m"], load=dict(load))
    px, py, pz = c.pivot()
    r1 = math.hypot(pick[0] - px, pick[1] - py)
    r2 = math.hypot(setp[0] - px, setp[1] - py)
    if min(r1, r2) < 3.0:
        return ("near", None, None, max(r1, r2))
    cap = capacity_t(k, max(r1, r2))
    if cap < need_t:
        return ("weight", None, None, max(r1, r2))
    tip_need = hook_need_z + c.hook_drop_m
    boom = None
    for L in k["boom_m"]:
        ok = True
        els = []
        for r in (r1, r2):
            if r >= L:
                ok = False; break
            el = math.degrees(math.acos(r / L))
            if el < ELEV_MIN or el > ELEV_MAX or pz + L * math.sin(math.radians(el)) < tip_need:
                ok = False; break
            els.append(el)
        if ok:
            boom = (L, els); break
    if boom is None:
        return ("reach", None, None, max(r1, r2))
    L, (e1, e2) = boom
    s1 = _norm(_ang(pick[0] - px, pick[1] - py) - heading)
    s2 = _norm(_ang(setp[0] - px, setp[1] - py) - heading)
    c.boom_len_m = L
    c.boom_elev_deg = round(e1, 2)
    c.boom_elev2_deg = round(e2, 2) if abs(e1 - e2) > 0.05 else None
    c.slew_deg = (min(s1, s2), max(s1, s2))
    reach = max(c.reach(e1), c.reach(e2)) + max(load["w"], load["d"]) + 1.0
    lo, hi = heading + c.slew_deg[0], heading + c.slew_deg[1]
    extra = spec["boom_r"] + max(load["w"], load["d"]) / 2 + reach * math.sin(math.radians(step / 2)) + 0.5
    near = spec["carrier"]["len"] / 2 + 1.0
    envs = _prefilter(env_list, (px, py), reach, lo, hi, extra, near)
    w = _worst(envs, c.sweep(step)) if envs else None
    if w is not None and w[0] < 0:
        return ("clearance", c, w, max(r1, r2))
    return (None, c, w, max(r1, r2))


def _cells(layout: dict, k: dict, pick, setp) -> list[tuple[float, float]]:
    obs = _obstacles(layout)
    rmax = k["chart"][-1][0]
    keep = k["outrigger_half_m"] + 1.0
    x0, y0, x1, y1 = FENCE
    out = []
    y = y0 + 2.0
    while y <= y1 - 2.0:
        x = x0 + 2.0
        while x <= x1 - 2.0:
            if math.hypot(x - pick[0], y - pick[1]) <= rmax + 1.5 and math.hypot(x - setp[0], y - setp[1]) <= rmax + 1.5 \
                    and all(math.hypot(x - ox, y - oy) >= keep for ox, oy in obs):
                out.append((x, y))
            x += GRID_M
        y += GRID_M
    return out


def _select_on(env_list, layout, classes, pick, setp, weight_t, load, hook_need_z, rules):
    tbl = _table()
    per_class = []
    for k in classes:
        need = weight_t + k["hook_t"] + tbl["rigging_t"]
        counts = {"near": 0, "weight": 0, "reach": 0, "clearance": 0}
        best_ok = None          # (margin, crane, worst)
        best_ng = None          # 離隔不足のうち一番ましなもの
        min_r = None
        for base in _cells(layout, k, pick, setp):
            why, c, w, r = _try_cell(k, base, pick, setp, need, load, hook_need_z, env_list, SCREEN_STEP_DEG)
            min_r = r if min_r is None else min(min_r, r)
            if why:
                counts[why] += 1
                if why == "clearance" and (best_ng is None or w[0] > best_ng[0]):
                    best_ng = (w[0], c, w)
                continue
            m = w[0] if w else 99.0
            if best_ok is None or m > best_ok[0]:
                best_ok = (m, c, w)
        entry = {"class": k["id"], "name": k["name"], "need_t": round(need, 2), "counts": counts,
                 "reach_and_lift": bool(best_ok or best_ng)}   # 離隔を見なければ、届いて吊れる位置があるか
        if best_ok:
            # ふるい分けで選んだ位置を、承認と同じ判定（2° 刻み）でやり直す
            c = best_ok[1]
            out = evaluate({"site_id": None, "step": None, "envelopes": env_list}, c, rules)
            entry.update({"ok": out["verdict"] != NG, "crane": c.to_dict(), "verdict": out["verdict"], "verdict_ja": out["verdict_ja"],
                          "min_distance_m": out["worst"]["distance_m"] if out["worst"] else None,
                          "required_m": out["worst"]["required_m"] if out["worst"] else None,
                          "margin_m": out["worst"]["margin_m"] if out["worst"] else None, "reasons": out["reasons"],
                          "conditions": out["conditions"]})
            if out["verdict"] == NG:
                entry["why_not"] = out["reasons"][0]
        else:
            entry["ok"] = False
            if best_ng:
                m, c, w = best_ng
                entry["why_not"] = (f"届いて吊れる位置はあるが、どの位置でも {w[1]}（{w[2]:g}kV）に {w[4]:.2f}m まで近づく。"
                                    f"必要 {w[3]:.2f}m")
                entry["binding_conductor"] = w[1]
            elif counts["weight"] and not counts["reach"]:
                cap = capacity_t(k, min_r or 0)
                entry["why_not"] = f"届く位置での作業半径（最短 {min_r:.1f}m）では定格 {cap:g}t しか吊れない。必要 {need:.2f}t（吊る物＋フック＋吊具）"
            elif counts["reach"] or counts["weight"]:
                entry["why_not"] = "ブームが届かない（作業半径とフックの高さ）、または作業半径で定格荷重が足りない"
            else:
                entry["why_not"] = "据え付けられる位置がない（機器・鉄構から離せる位置で 2 点に届かない）"
        per_class.append(entry)
        if entry["ok"]:
            break
    return per_class


def select(topo: Topology, layout: dict, state: dict, pick_id: str, weight_t: float | None = None,
           set_xy: tuple[float, float] | None = None, load: dict | None = None, suggest_outage: bool = True) -> dict:
    """吊る機器 pick_id（layout の at が吊る点）と資材置場 set_xy から、一番小さいクラスと据付位置を選ぶ。"""
    from engine.steps import generate
    rules = load_rules()
    item = lift_item(topo, pick_id)
    p = pick_point(layout, pick_id)
    if p is None:
        return {"ok": False, "problems": [f"{pick_id} の位置が配置に無い"]}
    if weight_t is None:
        if item is None:
            return {"ok": False, "problems": [f"{pick_id} の重さの例示値が無い。重さを入れる（変圧器の本体は移動式クレーンで吊らない想定）"]}
        weight_t = item["t"]
    load = load or ({"w": item["w"], "d": item["d"], "h": item["h"]} if item else {"w": 2.0, "d": 2.0, "h": 2.5})
    setp = tuple(set_xy) if set_xy else default_laydown(layout, p)
    hook_need_z = max(p[2], 0.0) + load["h"] + _table()["sling_m"]   # 吊った物の下端が機器の高さを越える
    pick = (p[0], p[1])
    res = energize(topo, state)
    env = envelopes(topo, layout, res, ClearanceTable.load(), False)
    classes = load_classes()
    per = _select_on(env["envelopes"], layout, classes, pick, setp, weight_t, load, hook_need_z, rules)
    chosen = next((e for e in per if e["ok"]), None)
    out = {"ok": chosen is not None, "pick_id": pick_id, "pick": list(p), "set": list(setp), "weight_t": weight_t, "load": load,
           "item": item, "chosen": chosen, "tried": per, "table_status": _table()["status"], "problems": []}
    # 重さと届く距離だけで決まるクラス（離隔を見ない）。選んだクラスとの差が「充電部を避けるための上乗せ」
    wo = next((e for e in per if e.get("reach_and_lift")), None)
    out["by_weight"] = {"class": wo["class"], "name": wo["name"]} if wo else None
    if wo and chosen and wo["class"] != chosen["class"]:
        out["by_weight"]["note"] = f"重さと届く距離だけなら {wo['name']} で足りる。充電部の離隔を保つために {chosen['name']} が要る"
    elif wo and chosen:
        out["by_weight"]["note"] = f"重さと届く距離で決まる {wo['name']} のまま、充電部の離隔も保てる"
    # 一つ下のクラスが使えない理由（選んだクラスの直前）
    if chosen:
        i = per.index(chosen)
        out["smaller_why_not"] = per[i - 1]["why_not"] if i > 0 else None
    # 置けないとき、または最小クラスで置けないとき: 邪魔をしている充電部を順に止めたらどうなるか（最大 3 か所）
    def binding_of(entries):
        for e in reversed(entries):          # 大きいクラスほど届く位置が多いので、そこで邪魔をしている導体を採る
            if e.get("binding_conductor"):
                return e["binding_conductor"]
        return None
    binding = binding_of(per)
    if suggest_outage and binding and (not chosen or chosen["class"] != classes[0]["id"]):
        from engine.propose import _owner_equipment
        lim = classes[: (per.index(chosen) if chosen else len(classes))] or classes[:1]
        targets, cur = [], state
        for _ in range(3):
            owner = _owner_equipment(topo, binding)
            if not owner or owner in targets:
                break
            st = generate(topo, cur, [owner])
            if not st["ok"]:
                break
            targets.append(owner); cur = st["state"]
            env2 = envelopes(topo, layout, energize(topo, cur), ClearanceTable.load(), False)
            per2 = _select_on(env2["envelopes"], layout, lim, pick, setp, weight_t, load, hook_need_z, rules)
            ch2 = next((e for e in per2 if e["ok"]), None)
            if ch2:
                break
            binding = binding_of(per2)
            if not binding:
                break
        if targets:
            from engine.steps import _label
            names = "、".join(_label(topo, x) for x in targets)
            st_all = generate(topo, state, targets)
            out["with_outage"] = {"targets": targets, "names": names, "ops": st_all["ops"], "conditions": st_all["conditions"],
                                  "state": st_all["state"], "chosen": ch2,
                                  "note": (f"{names} を追加で止めれば {ch2['name']} で置ける" if ch2
                                           else f"{names} を追加で止めても、{lim[-1]['name']}以下では置けない")}
    if not chosen:
        out["problems"].append("どのクラスでも、2 点に届き、吊れて、離隔を保てる位置が見つからない")
    return out
