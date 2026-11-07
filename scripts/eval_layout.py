#!/usr/bin/env python3
"""装置図から組み直した 3D レイアウト（下書き）を、正解（truth/layout.json）と比べる。

  python scripts/eval_layout.py            # SITE-01: 装置図 PDF → 読む → 組み直す → 比べる、の表を出す

比べるもの:
  - 機器の位置（平面 x, y の差）と高さ（z の差）。truth の at を持つ機器ごと
  - 導体: truth のカプセルごとに、同じ id・同じ相の下書きのカプセルがあり、両端点の距離が 0.5 m 以内なら一致
    （端の順は問わない。id が下書きに無いときだけ、相が同じで端点が合う別 id のカプセルを探す）
  - 構造物（鉄構・架空地線・避雷器など）も同じ規則で数える
"""
from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

POS_TOL_M = 0.1          # 機器の位置が合ったとみなす差
Z_TOL_M = 0.05           # 高さが合ったとみなす差
COND_TOL_M = 0.5         # 導体の端点が合ったとみなす差


def _d(a, b) -> float:
    return math.dist(a, b)


def _cap_match(t: dict, d: dict, tol: float) -> bool:
    if t.get("phase") != d.get("phase"):
        return False
    return (max(_d(t["a"], d["a"]), _d(t["b"], d["b"])) <= tol or
            max(_d(t["a"], d["b"]), _d(t["b"], d["a"])) <= tol)


def _match_caps(truth_groups: dict[str, list], draft_groups: dict[str, list], tol: float):
    """truth の id → カプセル列、下書きの id → カプセル列。返り値: (一致数, 総数, 一致しなかった truth の id の列)。"""
    used: set[tuple[str, int]] = set()
    matched, total, bad = 0, 0, []
    pending = []
    for tid, caps in truth_groups.items():
        for tc in caps:
            total += 1
            ok = False
            for j, dc in enumerate(draft_groups.get(tid, [])):
                if (tid, j) not in used and _cap_match(tc, dc, tol):
                    used.add((tid, j)); ok = True
                    break
            if ok:
                matched += 1
            elif tid not in draft_groups:
                pending.append((tid, tc))
            else:
                bad.append(tid)
    # id が下書きに無いものだけ、別 id のカプセルと端点で突き合わせる（両端の機器の組が同じなら別の名前でも同じ導体）
    for tid, tc in pending:
        hit = False
        for did, caps in draft_groups.items():
            for j, dc in enumerate(caps):
                if (did, j) not in used and _cap_match(tc, dc, tol):
                    used.add((did, j)); hit = True
                    break
            if hit:
                break
        if hit:
            matched += 1
        else:
            bad.append(tid)
    return matched, total, bad


def evaluate_layout(draft: dict, truth: dict) -> dict:
    """下書き（build_layout の返り値）を truth と比べる。"""
    d_at = {i["id"]: i["at"] for i in draft["items"] if "at" in i}
    t_at = {i["id"]: i["at"] for i in truth["items"] if "at" in i}
    pos_err, z_err = [], []
    pos_ok = z_ok = 0
    for iid, t in t_at.items():
        d = d_at.get(iid)
        if d is None:
            continue
        pe = math.hypot(d[0] - t[0], d[1] - t[1])
        ze = abs(d[2] - t[2])
        pos_err.append(pe); z_err.append(ze)
        pos_ok += pe <= POS_TOL_M
        z_ok += ze <= Z_TOL_M
    drawn = sum(1 for i in draft["items"] if i.get("height_source") == "drawing")

    t_caps = {i["id"]: i["primitives"] for i in truth["items"] if i.get("primitives")}
    d_caps = {i["id"]: i["primitives"] for i in draft["items"] if i.get("primitives")}
    cm, ct, cbad = _match_caps(t_caps, d_caps, COND_TOL_M)

    t_st = {s["id"]: s["primitives"] for s in truth.get("structures", [])}
    d_st = {s["id"]: s["primitives"] for s in draft.get("structures", [])}
    sm, st, sbad = _match_caps(t_st, d_st, COND_TOL_M)

    def mean(v):
        return sum(v) / len(v) if v else float("nan")

    return {
        "apparatus_matched": pos_ok, "apparatus_total": len(t_at), "apparatus_found": len(pos_err),
        "position_error_mean_m": mean(pos_err), "position_error_max_m": max(pos_err, default=float("nan")),
        "height_matched": z_ok, "height_error_mean_m": mean(z_err), "height_error_max_m": max(z_err, default=float("nan")),
        "height_from_drawing": drawn,
        "conductor_match": {"matched": cm, "total": ct, "tolerance_m": COND_TOL_M, "rate": (cm / ct if ct else float("nan")),
                            "unmatched_ids": sorted(set(cbad))},
        "structure_match": {"matched": sm, "total": st, "tolerance_m": COND_TOL_M, "unmatched_ids": sorted(set(sbad))},
    }


def markdown_table(result: dict) -> str:
    c, s = result["conductor_match"], result["structure_match"]
    rows = [
        ("機器の位置が合った数（差 %.1f m 以内）" % POS_TOL_M, f"{result['apparatus_matched']} / {result['apparatus_total']}"),
        ("位置の差 平均 / 最大", f"{result['position_error_mean_m'] * 1000:.1f} mm / {result['position_error_max_m'] * 1000:.1f} mm"),
        ("高さが合った数（差 %.2f m 以内）" % Z_TOL_M, f"{result['height_matched']} / {result['apparatus_total']}"),
        ("高さの差 平均 / 最大", f"{result['height_error_mean_m'] * 1000:.1f} mm / {result['height_error_max_m'] * 1000:.1f} mm"),
        ("うち高さを図面のラベルから取った機器", f"{result['height_from_drawing']}"),
        (f"導体が合った数（端点 {c['tolerance_m']} m 以内）", f"{c['matched']} / {c['total']}（{c['rate'] * 100:.1f}%）"),
        (f"構造物のカプセルが合った数（{s['tolerance_m']} m 以内）", f"{s['matched']} / {s['total']}"),
    ]
    out = ["| 項目 | 結果 |", "|---|---|"]
    out += [f"| {a} | {b} |" for a, b in rows]
    return "\n".join(out)


def main() -> int:
    from ingest.layout_build import build_layout, check_consistency
    from ingest.pdf_layout import extract_layout
    site = ROOT / "data" / "sites" / "SITE-01"
    topo = json.loads((site / "truth" / "topology.json").read_text(encoding="utf-8"))
    truth = json.loads((site / "truth" / "layout.json").read_text(encoding="utf-8"))
    ex = extract_layout(site / "drawings" / "SITE-01_layout.pdf", topology=topo)
    draft = build_layout(topo, ex)
    res = evaluate_layout(draft, truth)
    print(markdown_table(res))
    kinds: dict[str, int] = {}
    for f in check_consistency(topo, ex):
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    print(f"\n照合: {kinds}　質問 {len(draft['questions'])} 件")
    if res["conductor_match"]["unmatched_ids"]:
        print("合わなかった導体の id:", ", ".join(res["conductor_match"]["unmatched_ids"][:20]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
