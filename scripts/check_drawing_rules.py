#!/usr/bin/env python3
"""装置図（layout.pdf）が synth/drawing_rules.py の規則どおりに描けているかを確かめる。

  python scripts/check_drawing_rules.py

確かめること:
  1. 往復: すべての機器で center_from_text(number_text_anchor(...)) が元の at と 1 cm 以内で一致
  2. 機器番号の数: PDF の文字から、at を持つ機器と同じ数の番号が、規則の位置（0.3mm 以内）に見つかる
  3. 断面の高さラベル: 各断面に "GL+" の高さラベルが出ていて、各母線（電圧・号）が含まれる
どれかが外れたら終了コード 1。
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pdfplumber  # noqa: E402

from synth import drawing_rules as dr  # noqa: E402
from synth.gen_site import P, SITE_ID  # noqa: E402

MM = 72 / 25.4
TRUTH = ROOT / "data" / "sites" / SITE_ID / "truth"
PDF = ROOT / "data" / "sites" / SITE_ID / "drawings" / f"{SITE_ID}_layout.pdf"


def words(page):
    """文字を baseline（行）ごとにつなぎ、(文字列, 左下の紙 x mm, baseline の紙 y mm) の列にする。"""
    chars = sorted(page.chars, key=lambda c: (round(c["matrix"][5], 1), c["matrix"][4]))
    out, cur = [], None
    for c in chars:
        e, f = c["matrix"][4], c["matrix"][5]
        if cur and abs(f - cur["f"]) < 0.05 and -0.3 < e - cur["end"] < 0.6:
            cur["text"] += c["text"]; cur["end"] = e + c["adv"] if "adv" in c else c["x1"]
        else:
            if cur:
                out.append(cur)
            cur = {"text": c["text"], "e": e, "f": f, "end": c["x1"]}
        cur["end"] = c["x1"]
    if cur:
        out.append(cur)
    return [(w["text"].strip(), w["e"] / MM, w["f"] / MM) for w in out]


def main() -> int:
    topo = json.loads((TRUTH / "topology.json").read_text(encoding="utf-8"))
    layout = json.loads((TRUTH / "layout.json").read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in topo["nodes"]}
    ok = True

    items = []   # (id, 番号の文字, 記号の種類, 軸, at)
    for it in layout["items"]:
        if "at" not in it or it["id"] not in nodes:
            continue
        n = nodes[it["id"]]
        kind = dr.symbol_kind(n["kind"], n.get("voltage_kv", 220), it["id"])
        label = n.get("number") or n.get("name", "")      # 調相設備は名前が番号
        items.append((it["id"], label, kind, dr.orientation(it["id"])["along"], it["at"][:2]))

    # 1) 往復
    worst = 0.0
    for _id, _, kind, along, at in items:
        c = dr.center_from_text(kind, dr.number_text_anchor(kind, at, along), along)
        worst = max(worst, abs(c[0] - at[0]), abs(c[1] - at[1]))
    r1 = worst <= 0.01
    print(f"[往復] {len(items)} 機器、最大差 {worst * 1000:.3f} mm（構内）→ {'OK' if r1 else 'NG'}")
    ok &= r1

    with pdfplumber.open(PDF) as pdf:
        ws = words(pdf.pages[0])

    # 2) 機器番号の数と位置
    found, missing, worst_pdf = 0, [], 0.0
    index = {}
    for t, x, y in ws:
        index.setdefault(t, []).append((x, y))
    for _id, label, kind, along, at in items:
        ex, ey = dr.number_text_anchor(kind, at, along)
        hit = [(x, y) for x, y in index.get(label, []) if abs(x - ex) < 0.3 and abs(y - ey) < 0.3]
        if hit:
            found += 1
            cx, cy = dr.center_from_text(kind, hit[0], along)
            worst_pdf = max(worst_pdf, abs(cx - at[0]), abs(cy - at[1]))
        else:
            missing.append(_id)
    r2 = found == len(items) and worst_pdf <= 0.01
    print(f"[機器番号] at を持つ機器 {len(items)}、PDF で規則の位置に見つかった番号 {found}、PDF から戻した中心の最大差 {worst_pdf * 1000:.1f} mm → {'OK' if r2 else 'NG'}")
    if missing:
        print("  見つからない:", missing[:10])
    ok &= r2

    # 3) 断面の高さラベル
    specs = dr.section_specs(P)
    for name in dr.SECTION_ORDER:
        sp = dr.section_specs(P)[name]
        x0, y0, x1, y1 = dr.section_paper_box(sp)
        labs = []
        for t, x, y in ws:
            p = dr.parse_height_label(t)
            if p and x0 <= x <= x1 and y0 <= y <= y1:
                labs.append(p)
        buses = sorted(e for e, _ in labs if e.endswith("号母線"))
        need = {dr.bus_label(kv, b["no"]) for kv, lst in dr.BUSES.items() for b in lst
                if sp["y_from"] <= P[str(kv)][b["plan_key"]]["y"] <= sp["y_to"]}
        r3 = bool(labs) and need <= set(buses)
        kinds = {"母線": len(buses), "その他": len(labs) - len(buses)}
        print(f"[断面 {name}] 高さラベル {len(labs)}（{kinds}）、母線 {buses} → {'OK' if r3 else 'NG（期待 ' + str(sorted(need)) + '）'}")
        ok &= r3
    print("結果:", "OK" if ok else "NG")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
