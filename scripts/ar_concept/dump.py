"""現地表示（AR）の構想を描く動画のための入力を、engine から書き出す（Claude は呼ばない）。

    python scripts/ar_concept/dump.py [--out scripts/ar_concept/concept.json]

台本と同じ場面（scripts/check_demo.py と同じ）: 66kV 遮断器（66-D1-CB1）の作業日の停止範囲 → 一番小さいクレーン →
1 号変圧器を追加で止めた配置。その計画の課電・包絡（離隔の範囲）・クレーンの配置を、合成変電所の形（layout）と
機器の寸法（synth/equipment.py）と一緒に 1 つの JSON にする。動画はこの JSON を 3D に描くだけで、課電も距離も
ここで engine が決めた値をそのまま使う。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.clearance import evaluate  # noqa: E402
from engine.crane import Crane  # noqa: E402
from engine.crane_select import select as select_crane  # noqa: E402
from engine.energize import energize  # noqa: E402
from engine.envelope import ClearanceTable, envelopes  # noqa: E402
from engine.steps import generate  # noqa: E402
from engine.topology import Topology  # noqa: E402

TARGET = "66-D1-CB1"


def _read(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def load_site(site_id: str) -> dict:
    d = ROOT / "data" / "sites" / site_id / "truth"
    states = {p.stem: _read(p) for p in sorted((d / "states").glob("*.json"))} if (d / "states").is_dir() else {}
    return {"site_id": site_id, "topology": _read(d / "topology.json"), "layout": _read(d / "layout.json"), "states": states}


def dims() -> dict:
    from synth.equipment import EQUIP, GANTRY, LINE_GANTRY_220, LOADS, TOWER_220, TRANSFORMER
    return {"equip": {str(k): v for k, v in EQUIP.items()}, "transformer": TRANSFORMER, "gantry": GANTRY,
            "line_gantry_220": LINE_GANTRY_220, "tower_220": TOWER_220, "loads": LOADS}


def build(site_id: str = "SITE-01") -> dict:
    site = load_site(site_id)
    topo = Topology.from_dict(site["topology"])
    normal = site["states"]["normal"]
    st = generate(topo, normal, [TARGET])
    if not st.get("ok"):
        raise SystemExit("停止範囲を作れない: " + "; ".join(st.get("problems", [])))
    day = st["state"]
    sel = select_crane(topo, site["layout"], day, TARGET, None, None)
    if not sel.get("ok"):
        raise SystemExit("重機を選べない: " + "; ".join(sel.get("problems", [])))
    wo = sel.get("with_outage") or {}
    ch2 = wo.get("chosen")
    state2, crane2, chosen = (wo["state"], ch2["crane"], ch2) if ch2 else (day, sel["chosen"]["crane"], sel["chosen"])
    res = energize(topo, state2)
    env = envelopes(topo, site["layout"], res, ClearanceTable.load(), False)
    cl = evaluate(env, Crane.from_dict(crane2))
    if cl["verdict"] == "ng":
        raise SystemExit("採用した配置が不可: " + cl["reasons"][0])
    nodes = {n["id"]: n for n in site["topology"]["nodes"]}
    return {
        "note": "合成変電所（SITE-01）。課電・包絡・クレーンの配置と距離は engine の出力をそのまま置いた。暦日は入れない。",
        "scenario": {"target": TARGET, "target_name": nodes.get(TARGET, {}).get("name") or TARGET,
                     "ops": [o.get("number") or o["id"] for o in st.get("ops", [])],
                     "extra_outage": wo.get("note"), "crane_name": chosen.get("name"), "verdict_ja": cl.get("verdict_ja"),
                     "min_distance_m": (cl.get("worst") or {}).get("distance_m"), "required_m": (cl.get("worst") or {}).get("required_m")},
        "site": site, "dims": dims(), "energization": res.to_dict(), "envelope": env, "clearance": cl, "crane": crane2,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).with_name("concept.json")))
    a = ap.parse_args()
    out = build()
    Path(a.out).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    s = out["scenario"]
    print(f"対象 {s['target_name']}、切る {len(s['ops'])}、{s['crane_name']}、{s['verdict_ja']}（最小 {s['min_distance_m']} m／必要 {s['required_m']} m）")
    print("包絡", len(out["envelope"]["envelopes"]), "件 →", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
