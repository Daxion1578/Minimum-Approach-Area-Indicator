"""v9 の 3D 静止画（assets/r9）の入力を engine から書き出す（Claude は呼ばない）。

  python scripts/demo_video/v9/tools/stills/dump9.py      → 同じ所に stills.json と ground.png

scripts/ar_concept/dump.py の build()（220kV 東線1L の遮断器の作業日、母線 A 区間は止められない、資材置場は西 6 m、10 t → 承認した配置）に、
平常の状態（全部が充電）の課電と包絡を足す。地面には機械器具装置図（A1、平面 1/400）の平面の部分を薄く敷く。
"""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts" / "ar_concept"))
import dump as D  # noqa: E402  scripts/ar_concept/dump.py（変えずに使う）
from engine.energize import energize  # noqa: E402
from engine.envelope import ClearanceTable, envelopes  # noqa: E402
from engine.topology import Topology  # noqa: E402
from synth.drawing_rules import PLAN_OX, PLAN_OY  # noqa: E402

# 地面に敷く範囲（構内の座標 m）。装置図は 1/400 = 1 m あたり 2.5 mm
X0, X1, Y0, Y1 = -20.0, 150.0, -20.0, 160.0
DPI = 100
PAPER = np.array([243, 241, 236], float)


def ground_png(out: Path) -> dict:
    pdf = ROOT / "data" / "sites" / "SITE-01" / "drawings" / "SITE-01_layout.pdf"
    page_h_mm = 594.0
    mm = lambda v: v / 25.4 * DPI
    x0, x1 = mm(PLAN_OX + 2.5 * X0), mm(PLAN_OX + 2.5 * X1)
    y0, y1 = mm(page_h_mm - (PLAN_OY + 2.5 * Y1)), mm(page_h_mm - (PLAN_OY + 2.5 * Y0))
    tmp = HERE / "_ground"
    subprocess.run(["pdftoppm", "-r", str(DPI), "-png", "-singlefile", "-x", str(int(x0)), "-y", str(int(y0)), "-W", str(int(x1 - x0)), "-H", str(int(y1 - y0)), str(pdf), str(tmp)], check=True)
    im = np.asarray(Image.open(tmp.with_suffix(".png")).convert("L"), float) / 255.0
    ink = 1.0 - im                                   # 線ほど 1
    rgb = PAPER[None, None, :] * (1 - 0.42 * ink[..., None]) + np.array([120, 124, 130], float)[None, None, :] * 0.0
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(out)
    tmp.with_suffix(".png").unlink()
    return {"x0": X0, "x1": X1, "y0": Y0, "y1": Y1, "px": [int(x1 - x0), int(y1 - y0)]}


def main():
    out = D.build()
    site = out["site"]
    topo = Topology.from_dict(site["topology"])
    res_n = energize(topo, site["states"]["normal"])
    env_n = envelopes(topo, site["layout"], res_n, ClearanceTable.load(), False)
    out["normal"] = {"energization": res_n.to_dict(), "envelope": env_n}
    out["ground"] = ground_png(HERE / "ground.png")
    (HERE / "stills.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    s = out["scenario"]
    print(f"対象 {s['target_name']}、{s['crane_name']}、{s['verdict_ja']}（最小 {s['min_distance_m']} m／必要 {s['required_m']} m）、平常の包絡 {len(env_n['envelopes'])} 件、作業日の包絡 {len(out['envelope']['envelopes'])} 件")


if __name__ == "__main__":
    main()
