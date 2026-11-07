"""依頼文から取り出した候補の確かめ（§8.6）。決定論。Claude が返した候補を、そのまま計算に使わないための関門。

  - 機器の id が構内に実在するか（無ければ問題にして外す）
  - 取り替える機器が、止められない設備にも入っていないか（矛盾は問題にして、その機器を止められない側から外さない＝計算に使わない）
  - 重さが 0 より大きく 100 t 以下か
  - 資材置場「基準の機器・方角・距離」を構内の座標に直し、構内（FENCE）に入るか
ok が True のときだけ、画面の「この内容で入れる」が押せる。
"""
from __future__ import annotations

from engine.crane_select import FENCE

DIRS = {"east": (1, 0), "west": (-1, 0), "north": (0, 1), "south": (0, -1)}


def check(extracted: dict, topo: dict, layout: dict) -> dict:
    nodes = {n["id"]: n for n in topo["nodes"]}
    at = {it["id"]: it["at"] for it in layout["items"] if it.get("at")}
    problems: list[str] = []

    def label(i: str) -> str:
        n = nodes[i]
        return f"{n.get('number') or ''} {n.get('name') or i}".strip()

    def keep(ids) -> list[str]:
        out = []
        for i in ids or []:
            if i in nodes:
                out.append(i)
            else:
                problems.append(f"{i} は構内の機器の一覧に無い（読み違いの可能性）")
        return list(dict.fromkeys(out))

    targets = keep(extracted.get("targets"))
    unstoppable = keep(extracted.get("unstoppable"))
    clash = [t for t in targets if t in unstoppable]
    for t in clash:
        problems.append(f"{label(t)} が「取り替える」と「止められない」の両方に入っている。依頼文を確かめる")
    if not targets:
        problems.append("取り替える機器が読み取れない")
    w = extracted.get("weight_t")
    weight = None
    if w is not None:
        try:
            weight = float(w)
            if not 0 < weight <= 100:
                problems.append(f"重さ {weight} t は範囲外（0〜100 t）")
                weight = None
        except (TypeError, ValueError):
            problems.append(f"重さ {w} が数値でない")
    lay = extracted.get("laydown") or None
    xy = None
    if lay:
        near, d, dist = lay.get("near"), DIRS.get(str(lay.get("dir", "")).lower()), lay.get("dist_m")
        if near not in at:
            problems.append(f"資材置場の基準 {near} の位置が配置に無い")
        elif d is None or not isinstance(dist, (int, float)) or not 0 < dist <= 60:
            problems.append(f"資材置場の方角・距離が読めない（{lay}）")
        else:
            x, y = at[near][0] + d[0] * dist, at[near][1] + d[1] * dist
            x0, y0, x1, y1 = FENCE
            if not (x0 < x < x1 and y0 < y < y1):
                problems.append(f"資材置場 ({x:.0f}, {y:.0f}) が構内の外")
            else:
                xy = [round(x, 1), round(y, 1)]
    final = [t for t in targets if t not in clash]
    return {"ok": bool(final) and not clash,   # 外した候補や置き場の問題は画面に出し、人が確かめて入れる
            "targets": final, "unstoppable": [u for u in unstoppable if u not in clash],
            "labels": {i: label(i) for i in targets + unstoppable}, "weight_t": weight, "laydown_xy": xy,
            "problems": problems}
