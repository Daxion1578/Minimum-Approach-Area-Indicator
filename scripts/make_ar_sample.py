"""AR 試作（web/ar.html）が読むサンプルの envelope.json を書き出す。

包絡の計算は engine が行う（課電判定 engine/energize.py → 安全包絡 engine/envelope.py）。
このスクリプトは合成変電所 SITE-01 の状態を1つ選んで engine を呼び、結果を
web/sample/SITE-01.envelope.json に書くだけ。承認前なので approved は null。
位置合わせの基準点は、ar.html が data/sites/SITE-01/truth/layout.json の reference_points を直接読む。

  python scripts/make_ar_sample.py            # 状態 normal
  python scripts/make_ar_sample.py tr2-outage # 別の状態
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.energize import energize  # noqa: E402
from engine.envelope import ClearanceTable, envelopes  # noqa: E402
from engine.topology import Topology  # noqa: E402

SITE = "SITE-01"


def main(argv: list[str]) -> int:
    state_name = argv[1] if len(argv) > 1 else "normal"
    truth = ROOT / "data" / "sites" / SITE / "truth"
    topo = Topology.load(truth / "topology.json")
    layout = json.loads((truth / "layout.json").read_text(encoding="utf-8"))
    state = json.loads((truth / "states" / f"{state_name}.json").read_text(encoding="utf-8"))

    res = energize(topo, state)
    env = envelopes(topo, layout, res, ClearanceTable.load(), treat_ungrounded_as_live=True)
    env["approved"] = None
    env["generated_by"] = f"scripts/make_ar_sample.py（engine/envelope.py の出力をそのまま書き出し。状態 {state_name}・未承認）"
    env["state_name"] = state_name
    env["state_note"] = state.get("note", "")

    out = ROOT / "web" / "sample" / f"{SITE}.envelope.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(env, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    by_kv: dict = {}
    for e in env["envelopes"]:
        by_kv.setdefault(e["voltage_kv"], [0, e["clearance_m"]])[0] += 1
    summary = "、".join(f"{kv}kV 離隔{v[1]}m ×{v[0]}" for kv, v in sorted(by_kv.items(), reverse=True))
    print(f"{out.relative_to(ROOT)}: 状態 {state_name}、包絡 {len(env['envelopes'])} 本（{summary}）")
    if res.invalid_ids:
        print(f"注意: 充電部に接地（invalid）があります: {', '.join(res.invalid_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
