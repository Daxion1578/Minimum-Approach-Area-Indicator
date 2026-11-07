"""塗り分けた単線結線図。承認の書き出し（PDF）と、画面の停止条件タブ（SVG）が同じ描き方を使う。

状態は充電・停電の 2 形態（11/6〜）。停電＝開閉器で全方向から切り離された区間。色は 充電=赤（実線）、停電=緑（破線）。
線種も変えるのでモノクロ印刷でも読める。開閉器は切った位置に「開」と書く。
承認の PDF は「作業前（平常）」と「作業日の停止範囲」の 2 枚（追加停止があればその分も）。
"""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape

from engine.energize import DEAD_GROUNDED, DEAD_UNGROUNDED, energize
from engine.topology import Topology
from synth.gen_drawings import MM, SITE_ID, SLD, Sheet, setup_font
from synth.svg_canvas import SvgCanvas


def _state_map(res) -> dict:
    """計算の 4 状態を、図の 2 形態（live / dead）にまとめる。誤り（invalid）はそのまま出す。"""
    two = {DEAD_GROUNDED: "dead", DEAD_UNGROUNDED: "dead"}
    st = {}
    for c in res.to_dict()["components"]:
        s = two.get(c["state"], c["state"])
        for n in c["nodes"]:
            st[n] = s
        for e in c["edges"]:
            st[e] = s
    return st


def _ops_text(ops) -> str:
    return "切る機器: " + ("、".join(o.get("number") or o["id"] for o in ops) if ops else "なし")


def write_step_drawings(site: dict, steps: dict | None, final_state: dict, out_dir: Path) -> list[str]:
    """承認時の書き出し。steps（作業日の停止範囲）があれば平常と停止範囲の 2 枚、無ければ最終状態 1 枚。"""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    topo = Topology.from_dict(site["topology"])
    font = setup_font()
    pages = []
    normal = site["states"].get("normal")
    if steps and steps.get("steps") and normal:
        pages.append((0, "作業前（平常）", normal, []))
        for s in steps["steps"]:
            pages.append((s["n"], s["title"], s["state"], s["ops"]))
        if final_state.get("switches") != steps["steps"][-1]["state"].get("switches"):
            pages.append((len(pages), "承認した状態（追加停止を含む）", final_state, []))
    else:
        pages.append((0, "承認した状態", final_state, []))
    files = []
    for n, title, state, ops in pages:
        fn = f"step-{n}-sld.pdf"
        sh = Sheet(out_dir / fn, A3, font, "停止範囲図（系統図）", f"S-01-1-{n}", "なし")
        res = energize(topo, state)
        SLD(sh, site["topology"], "jis", states=_state_map(res), switches=state.get("switches", {})).draw(title=title, subtitle=_ops_text(ops))
        sh.save()
        files.append(fn)
    (out_dir / "steps.json").write_text(json.dumps(steps or {}, ensure_ascii=False, indent=1), encoding="utf-8")
    files.append("steps.json")
    return files


CRANE_RGB = (0.1, 0.3, 0.85)      # クレーン関係は青
LAYDOWN_RGB = (0.85, 0.45, 0.0)   # 資材置場は橙
VERDICT_JA = {"ok": "可", "conditional": "条件付き可"}


def _wrap(text: str, font: str, size_mm: float, width_mm: float) -> list[str]:
    from reportlab.pdfbase import pdfmetrics
    out, cur = [], ""
    for ch in text:
        if pdfmetrics.stringWidth(cur + ch, font, size_mm * MM) / MM > width_mm and cur:
            out.append(cur); cur = ch
        else:
            cur += ch
    return out + ([cur] if cur else [])


def write_crane_plan(site: dict, plan: dict, out_dir: Path, lift: dict | None = None) -> str:
    """承認したクレーンの配置を、装置図の平面（1/400）に描き込んだ一般平面図 PDF（plan-crane.pdf）。

    plan は plan.json の中身（state, crane, steps, verdict, conditions, approval_hash, inputs）。
    lift は任意で {"pick_id", "set"}（吊る機器と資材置場）。無ければ作業日の対象機器と、選定と同じ既定の資材置場を使う。
    暦日は書かない（表題欄の日付欄は「承認: <ハッシュ先頭 12 桁>」）。判定・距離は engine の結果を写すだけで、ここでは決めない。
    """
    import math
    from reportlab.lib.pagesizes import A1
    from engine.crane import Crane
    from engine.crane_select import default_laydown, pick_point
    from synth import drawing_rules as dr
    from synth.gen_drawings import LW, LayoutDrawing, Plan, STATE_RGB

    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    topo_d, layout = site["topology"], site["layout"]
    topo = Topology.from_dict(topo_d)
    nodes = {n["id"]: n for n in topo_d["nodes"]}
    crane = Crane.from_dict(plan["crane"])
    steps = plan.get("steps") or {}
    h12 = str(plan.get("approval_hash", ""))[:12]
    font = setup_font()
    sh = Sheet(out_dir / "plan-crane.pdf", A1, font, "一般平面図（クレーン配置）", "S-01-4", "1/400", date_text=f"承認: {h12}")
    ld = LayoutDrawing(sh, layout, dr.PLAN_SCALE, ox=dr.PLAN_OX, oy=dr.PLAN_OY)
    ld.fence(); ld.roads_buildings(); ld.grid_lines(); ld.equipment_plan(topo_d)
    sh.north(75, 545)
    sh.text(45, sh.h - 24, "一般平面図　クレーン配置（承認した計画）　1/400", 4.0)

    # 詳細図 A（吊り点・据付位置のまわりを 1/125 に拡大。文字はここに集める）。主図は線だけ
    IX0, IY0, IW, IH, IS = 470.0, 62.0, 350.0, 156.0, 8.0
    ld2 = LayoutDrawing.__new__(LayoutDrawing)
    Plan.__init__(ld2, sh, layout, IS, IX0 + 3.0 * IS, IY0 - 29.0 * IS)
    ld2.numbers = []; ld2.hl_log = {}
    sh.text(IX0, IY0 + IH + 3, "詳細 A（吊り点・据付位置のまわり）　1/125", 3.2)
    sh.rect(IX0, IY0, IW, IH, LW["frame"])
    dead_ids = []
    for pl, labels in ((ld, False), (ld2, True)):
        if labels:
            sh.c.saveState(); pth = sh.c.beginPath(); pth.rect(IX0 * MM, IY0 * MM, IW * MM, IH * MM); sh.c.clipPath(pth, stroke=0, fill=0)
            pl.fence(); pl.equipment_plan(topo_d)
        dead_ids = []

        def L(x1, y1, x2, y2, rgb, w=0.6, dash=None):
            sh.line(pl.X(x1), pl.Y(y1), pl.X(x2), pl.Y(y2), w, dash, rgb=rgb)

        def T(x, y, s, size=2.3, anchor="sw", rgb=None):
            if not labels:
                return
            if rgb:
                sh.c.setFillColorRGB(*rgb)
            sh.text(pl.X(x), pl.Y(y), s, size, 0, anchor)
            sh.c.setFillGray(0)

        # 停止している機器（結線図と同じ緑の破線）
        sm = _state_map(energize(topo, plan["state"]))
        dead_ids = []
        for it in layout["items"]:
            n = nodes.get(it["id"])
            if not n or not it.get("at") or n["kind"] not in ("breaker", "disconnector", "transformer", "load"):
                continue
            st = sm.get(n["id"]) or sm.get(n["id"] + ".a") or sm.get(n["id"] + ".hv")
            if st == "dead":
                x, y = it["at"][0], it["at"][1]; r = 2.0
                g = STATE_RGB["dead"]
                for a, b in (((x - r, y - r), (x + r, y - r)), ((x + r, y - r), (x + r, y + r)), ((x + r, y + r), (x - r, y + r)), ((x - r, y + r), (x - r, y - r))):
                    L(a[0], a[1], b[0], b[1], g, 0.5, [2.0, 1.0])
                dead_ids.append(n["id"])

        # 吊り点と資材置場
        lift = lift or {}
        pick_id = lift.get("pick_id") or next(iter(steps.get("targets") or []), None)
        pk = pick_point(layout, pick_id) if pick_id else None
        setp = tuple(lift["set"]) if lift.get("set") else (default_laydown(layout, pk) if pk else None)
        pk_no = (nodes.get(pick_id) or {}).get("number") or pick_id
        if pk:
            r = 1.6
            sh.circle(pl.X(pk[0]), pl.Y(pk[1]), r * pl.s, 0.7)
            L(pk[0] - r - 1.2, pk[1], pk[0] + r + 1.2, pk[1], CRANE_RGB, 0.5); L(pk[0], pk[1] - r - 1.2, pk[0], pk[1] + r + 1.2, CRANE_RGB, 0.5)
            T(pk[0] + 2.2, pk[1] - 4.5, f"吊り点（{pk_no}）", 2.3, rgb=CRANE_RGB)
        if setp:
            sx, sy = setp; r = 1.6
            for a, b in (((sx - r, sy - r), (sx + r, sy - r)), ((sx + r, sy - r), (sx + r, sy + r)), ((sx + r, sy + r), (sx - r, sy + r)), ((sx - r, sy + r), (sx - r, sy - r)), ((sx - r, sy - r), (sx + r, sy + r)), ((sx - r, sy + r), (sx + r, sy - r))):
                L(a[0], a[1], b[0], b[1], LAYDOWN_RGB, 0.6)
            T(sx - 2.2, sy - 4.5, "資材置場", 2.3, rgb=LAYDOWN_RGB)

        # ブームの水平投影（起伏角ごと）と旋回範囲の扇形・先端の軌跡
        px, py, _ = crane.pivot()
        lo, hi = crane.slew_deg
        elevs = [crane.boom_elev_deg] + ([crane.boom_elev2_deg] if crane.boom_elev2_deg is not None else [])
        for k, el in enumerate(elevs):
            r = crane.reach(el)
            n = max(2, int(math.ceil((hi - lo) / 2.0)))
            pts = [(px + r * math.cos(math.radians(crane.heading_deg + lo + (hi - lo) * i / n)),
                    py + r * math.sin(math.radians(crane.heading_deg + lo + (hi - lo) * i / n))) for i in range(n + 1)]
            for a, b in zip(pts, pts[1:]):
                L(a[0], a[1], b[0], b[1], CRANE_RGB, 0.9, [4.0, 1.5] if k else None)
            for sl in (lo, hi, (lo + hi) / 2):
                ex, ey = crane.tip(sl, el)[:2]
                L(px, py, ex, ey, CRANE_RGB, 0.4 if sl not in (lo, hi) else 0.6, [1.2, 1.2] if sl not in (lo, hi) else None)
            mx, my = pts[len(pts) // 2]
            ux, uy = math.cos(math.radians(crane.heading_deg + (lo + hi) / 2)), math.sin(math.radians(crane.heading_deg + (lo + hi) / 2))
            lx, ly_ = mx - 4.0, my + 5.0 + 3.6 * k        # 文字は円弧の手前（左上の空き地）に置き、細い線でつなぐ
            T(lx, ly_, f"先端の軌跡 R={r:.1f}m（起伏角 {el:.1f}°）" + ("　破線" if k else ""), 2.2, "se", CRANE_RGB)
            if labels:
                L(lx + 0.3, ly_ + 0.6, mx, my, CRANE_RGB, 0.3)

        # 据付位置（車体）と向きの矢印
        bx, by = crane.base; hr = math.radians(crane.heading_deg)
        cl, cw = crane.spec["carrier"]["len"], crane.spec["carrier"]["w"]
        ex, ey, nx, ny = math.cos(hr), math.sin(hr), -math.sin(hr), math.cos(hr)
        corners = [(bx + ex * sx_ * cl / 2 + nx * sy_ * cw / 2, by + ey * sx_ * cl / 2 + ny * sy_ * cw / 2) for sx_, sy_ in ((1, 1), (1, -1), (-1, -1), (-1, 1))]
        for a, b in zip(corners, corners[1:] + corners[:1]):
            L(a[0], a[1], b[0], b[1], CRANE_RGB, 0.9)
        sh.circle(pl.X(bx), pl.Y(by), 0.8 * pl.s, 0.7, fill=True)
        sh.c.setFillGray(0)
        ax, ay = bx + ex * (cl / 2 + 3.5), by + ey * (cl / 2 + 3.5)
        L(bx, by, ax, ay, CRANE_RGB, 0.7)
        for s_ in (1, -1):
            L(ax, ay, ax - ex * 1.2 + nx * 0.7 * s_, ay - ey * 1.2 + ny * 0.7 * s_, CRANE_RGB, 0.7)
        T(bx, by - cw / 2 - 3.0, f"据付 ({bx:.1f}, {by:.1f}) m", 2.6, "s", CRANE_RGB)
        T(bx, by - cw / 2 - 5.8, f"車体の向き {crane.heading_deg:.1f}°", 2.2, "s", CRANE_RGB)

        if labels:
            sh.c.restoreState()

    # 主図に詳細 A の範囲を示す
    wx0, wx1, wy0, wy1 = -3.0, (IX0 + IW - (IX0 + 3.0 * IS)) / IS, 29.0, 29.0 + IH / IS
    for a, b in (((wx0, wy0), (wx1, wy0)), ((wx1, wy0), (wx1, wy1)), ((wx1, wy1), (wx0, wy1)), ((wx0, wy1), (wx0, wy0))):
        sh.line(ld.X(a[0]), ld.Y(a[1]), ld.X(b[0]), ld.Y(b[1]), 0.5, [3.0, 1.5], rgb=CRANE_RGB)
    sh.text(ld.X(wx0), ld.Y(wy1) + 1.0, "詳細 A", 2.8)

    # 右側: 計画の要点
    steps_ops = steps.get("ops") or []
    verdict = plan.get("verdict", "")
    cl_ = plan.get("clearance") or {}
    worst = cl_.get("worst") or {}
    cls_name = crane.spec["model"]
    rows = [
        ("対象機器", f"{pk_no}" + (f"（{(nodes.get(pick_id) or {}).get('name', '')}）" if (nodes.get(pick_id) or {}).get("name") else "")),
        ("切る機器", "、".join(o.get("number") or o["id"] for o in steps_ops) or "なし"),
        ("クレーン", f"{cls_name}　ブーム長 {crane.boom_len_m:.1f} m"),
        ("起伏角・旋回", "起伏角 " + " / ".join(f"{e:.1f}°" for e in elevs) + f"　旋回 {lo:+.1f}°〜{hi:+.1f}°（車体の向きから）"),
        ("判定", VERDICT_JA.get(verdict, verdict) + (f"（最小離隔 {worst['distance_m']:.2f} m／必要 {worst['required_m']:.2f} m）" if worst.get("distance_m") is not None else "")),
        ("承認ハッシュ", h12),
        ("離隔表", str((plan.get("inputs") or {}).get("clearance_table_id", ""))),
    ]
    bx0, by_top, bw = 470.0, 540.0, 350.0
    fs, lh = 2.5, 4.4
    body = []
    for k, v in rows:
        ls = _wrap(v, font, fs, bw - 36)
        body.append((k, ls))
    conds = [c for c in (plan.get("conditions") or [])]
    cond_lines = []
    for c in conds[:8]:
        ls = _wrap("・" + c, font, fs, bw - 8)
        cond_lines.append(ls)
    n_lines = sum(len(ls) for _, ls in body) + sum(len(ls) for ls in cond_lines) + 6 + (1 if len(conds) > 8 else 0)
    h_box = n_lines * lh + 12
    y = by_top - 4
    sh.rect(bx0, by_top - h_box, bw, h_box, LW["thin"])
    sh.text(bx0 + 3, y - 3.5, "承認した計画の要点", 3.4); y -= 9
    for k, ls in body:
        sh.text(bx0 + 3, y - 3, k, fs)
        for i, s_ in enumerate(ls):
            sh.text(bx0 + 33, y - 3 - i * lh, s_, fs)
        y -= len(ls) * lh + 0.8
    sh.line(bx0, y - 1, bx0 + bw, y - 1, LW["dim"]); y -= 5
    sh.text(bx0 + 3, y - 2, "承認の条件（この図の配置で作業する前提）", fs); y -= lh + 1
    for ls in cond_lines:
        for s_ in ls:
            sh.text(bx0 + 5, y - 2, s_, fs); y -= lh
    if len(conds) > 8:
        sh.text(bx0 + 5, y - 2, f"ほか {len(conds) - 8} 件は plan.json", fs); y -= lh

    # 凡例（要点の下）
    ly = by_top - h_box - 10
    sh.text(bx0, ly, "凡例", 2.5)
    items = [("青の実線", CRANE_RGB, None, "ブームの水平投影・先端の軌跡・車体"), ("青の破線", CRANE_RGB, [4.0, 1.5], "2 つ目の起伏角の先端の軌跡"),
             ("緑の破線", STATE_RGB["dead"], [2.0, 1.0], f"停電（切り離した）機器の囲み（{len(dead_ids)} 台）"), ("橙の×", LAYDOWN_RGB, None, "資材置場")]
    for i, (_, rgb, dash, label) in enumerate(items):
        yy = ly - 5 - i * 5.0
        sh.line(bx0 + 2, yy + 1, bx0 + 16, yy + 1, 0.9, dash, rgb=rgb)
        sh.text(bx0 + 19, yy, label, 2.3)
    sh.text(bx0, ly - 5 - len(items) * 5.0 - 1, "クラス・諸元は例示値。実機は荷重表で確認し、据付前に現地で寸法を確かめる", 2.2)
    sh.save()
    return "plan-crane.pdf"


def sld_svg(site: dict, state: dict, title: str = "単線結線図", subtitle: str | None = None) -> dict:
    """画面用: 状態で塗り分けた単線結線図の SVG と、開閉器・変圧器の記号の位置（SVG の座標）。"""
    topo = Topology.from_dict(site["topology"])
    font = setup_font()
    w_pt, h_pt = landscape(A3)
    cv = SvgCanvas(w_pt, h_pt)
    sh = Sheet(None, A3, font, "停止範囲図（系統図）", "S-01-1", "なし", canvas_obj=cv)
    res = energize(topo, state)
    states = _state_map(res)
    sld = SLD(sh, site["topology"], "jis", states=states, switches=state.get("switches", {}))
    sld.draw(title=title, subtitle=subtitle)
    marks = {}
    for nid, (x, y) in sld.marks.items():
        n = topo.nodes.get(nid)
        if n is None:
            continue
        marks[nid] = {"x": round(x * MM, 1), "y": round(h_pt - y * MM, 1), "kind": n.kind,
                      "number": next((d.get("number", "") for d in site["topology"]["nodes"] if d["id"] == nid), ""),
                      "name": n.name or "", "pos": state.get("switches", {}).get(nid, "closed") if n.kind in ("breaker", "disconnector") else None,
                      "state": states.get(nid) or states.get(nid + ".a") or states.get(nid + ".hv")}
    counts = {"live": 0, "dead": 0, "invalid": 0}
    for c in res.to_dict()["components"]:
        k = "dead" if c["state"] in (DEAD_GROUNDED, DEAD_UNGROUNDED) else c["state"]
        counts[k] = counts.get(k, 0) + len(c["nodes"])
    return {"svg": cv.to_svg(), "w": round(w_pt, 1), "h": round(h_pt, 1), "marks": marks, "counts": counts,
            "errors": [e["message"] for e in res.errors]}


if __name__ == "__main__":
    import sys
    from engine.steps import generate
    root = Path(__file__).resolve().parent.parent / "data" / "sites" / SITE_ID
    site = {"topology": json.loads((root / "truth" / "topology.json").read_text(encoding="utf-8")),
            "layout": json.loads((root / "truth" / "layout.json").read_text(encoding="utf-8")),
            "states": {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (root / "truth" / "states").glob("*.json")}}
    targets = sys.argv[1:] or ["220-T2-CB"]
    st = generate(Topology.from_dict(site["topology"]), site["states"]["normal"], targets)
    out = root / "approved" / "_preview"
    print(write_step_drawings(site, st, st["state"], out), "->", out)
