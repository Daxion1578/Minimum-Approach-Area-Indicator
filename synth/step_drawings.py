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
