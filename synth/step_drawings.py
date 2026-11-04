"""ステップ図（停止の段階ごとに塗り分けた単線結線図）を PDF で書き出す。

停止ステップ（engine/steps.py の出力）を受け取り、段階 0（通常）〜 3 の状態を課電判定で塗って 1 ページずつ描く。
色は 充電=赤、停電・接地=緑、停電・未接地=橙、誤り=紫。線種も変えるのでモノクロ印刷でも読める。
開閉器は操作後の位置を「開」「閉」で示す。
"""
from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.pagesizes import A3

from engine.energize import energize
from engine.topology import Topology
from synth.gen_drawings import SITE_ID, SLD, Sheet, setup_font


def _state_map(res) -> dict:
    st = {}
    for c in res.to_dict()["components"]:
        for n in c["nodes"]:
            st[n] = c["state"]
        for e in c["edges"]:
            st[e] = c["state"]
    return st


def write_step_drawings(site: dict, steps: dict | None, final_state: dict, out_dir: Path) -> list[str]:
    """承認時の書き出し。steps が無ければ最終状態 1 枚だけ。戻り値はファイル名の一覧。"""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    topo = Topology.from_dict(site["topology"])
    font = setup_font()
    pages = []
    if steps and steps.get("steps"):
        base = dict(steps["steps"][0]["state"]); base["switches"] = dict(site["states"].get("normal", steps["steps"][0]["state"])["switches"])
        pages.append((0, "段階 0　通常（停止前）", base, []))
        for s in steps["steps"]:
            pages.append((s["n"], f"段階 {s['n']}　{s['title']}", s["state"], s["ops"]))
    else:
        pages.append((0, "計画の状態", final_state, []))
    files = []
    for n, title, state, ops in pages:
        fn = f"step-{n}-sld.pdf"
        sh = Sheet(out_dir / fn, A3, font, "ステップ図（系統図）", f"S-01-1-{n}", "なし")
        res = energize(topo, state)
        sub = "操作: " + ("、".join(f"{o.get('number') or o['id']} {'開放' if o['to'] == 'open' else '投入'}" for o in ops) if ops else "なし")
        SLD(sh, site["topology"], "jis", states=_state_map(res), switches=state.get("switches", {})).draw(title=title, subtitle=sub)
        sh.save()
        files.append(fn)
    (out_dir / "steps.json").write_text(json.dumps(steps or {}, ensure_ascii=False, indent=1), encoding="utf-8")
    files.append("steps.json")
    return files


if __name__ == "__main__":
    import sys
    from engine.steps import generate
    root = Path(__file__).resolve().parent.parent / "data" / "sites" / SITE_ID
    site = {"topology": json.loads((root / "truth" / "topology.json").read_text(encoding="utf-8")),
            "layout": json.loads((root / "truth" / "layout.json").read_text(encoding="utf-8")),
            "states": {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (root / "truth" / "states").glob("*.json")}}
    targets = sys.argv[1:] or ["TR-2"]
    st = generate(Topology.from_dict(site["topology"]), site["states"]["normal"], targets)
    out = root / "approved" / "_preview"
    print(write_step_drawings(site, st, st["steps"][-1]["state"], out), "->", out)
