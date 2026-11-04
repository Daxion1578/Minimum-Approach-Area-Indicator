#!/usr/bin/env python3
"""図面取込の精度（§4-12）。合成変電所の単線結線図 PDF を取り込み、truth の topology と突き合わせる。

  python scripts/run_eval.py [pdf] [truth/topology.json]

測るもの:
  - 開閉器番号の再現率（図面に書いた番号のうち、取込で拾えた割合）と種別の正答率
  - 隣接の一致: 開閉器ごとに「導体をたどって次に出会う開閉器」の集合を、truth と取込で比べる（precision / recall）
  - 変圧器の一次／二次、線路、母線の対応
出力は表（Markdown）。数字は合成図面に対するもので、実務の図面の精度ではない。
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.topology import SWITCH_KINDS, Topology  # noqa: E402
from ingest.pdf_sld import extract, to_topology  # noqa: E402


def neighbors(topo: Topology, number_of: dict[str, str]) -> dict[str, set[str]]:
    """開閉器（番号）→ 導体をたどって次に出会う開閉器（番号）の集合。接地開閉器は付いているネットの開閉器。"""
    adj: dict[str, list[str]] = {}
    for e in topo.edges:
        adj.setdefault(e.a, []).append(e.b); adj.setdefault(e.b, []).append(e.a)

    def other(term):
        nid, _, t = term.partition(".")
        return f"{nid}.{'b' if t == 'a' else 'a' if t == 'b' else 'lv' if t == 'hv' else 'hv'}"

    out: dict[str, set[str]] = {}
    for n in topo.nodes.values():
        if n.id not in number_of:
            continue
        starts = [f"{n.id}.a", f"{n.id}.b"] if n.kind in SWITCH_KINDS else [topo.earthing_terminal(n)] if n.kind == "earthing" else []
        found: set[str] = set()
        seen: set[str] = set()
        q = deque(starts)
        while q:
            t = q.popleft()
            if t in seen:
                continue
            seen.add(t)
            m = topo.node_of(t)
            if m.id != n.id and m.kind in SWITCH_KINDS:
                if m.id in number_of:
                    found.add(number_of[m.id])
                continue
            if m.kind == "transformer":
                continue    # 変圧器は越えない（一次と二次は別の隣接）
            for nxt in adj.get(t, []):
                q.append(nxt)
            if m.kind in SWITCH_KINDS:
                q.append(other(t))
        out[number_of[n.id]] = found
    return out


def evaluate(pdf: Path, truth_path: Path) -> dict:
    truth_raw = json.loads(truth_path.read_text(encoding="utf-8"))
    truth = Topology.from_dict(truth_raw)
    t_num = {nd["id"]: nd["number"] for nd in truth_raw["nodes"] if nd.get("number") and nd["kind"] in SWITCH_KINDS + ("earthing",)}
    t_kind = {nd["number"]: nd["kind"] for nd in truth_raw["nodes"] if nd.get("number")}
    cand = extract(pdf)
    imp_raw = to_topology(cand)
    imp = Topology.from_dict(imp_raw)
    i_num = {nd["id"]: nd["number"] for nd in imp_raw["nodes"] if nd.get("number") and nd["kind"] in SWITCH_KINDS + ("earthing",)}
    i_kind = {nd["number"]: nd["kind"] for nd in imp_raw["nodes"] if nd.get("number")}
    # 図面に書かれている番号（記号に番号を添えたもの）: 真値の開閉器のうち取込で見つかったもの＋見つからなかったもの
    drawn = set(t_num.values())
    found = set(i_num.values())
    kinds_ok = sum(1 for k in found & drawn if i_kind.get(k) == t_kind.get(k))
    tn = neighbors(truth, t_num); inn = neighbors(imp, i_num)
    tp = fp = fn = 0
    per = []
    for k in sorted(drawn & found):
        a, b = tn.get(k, set()), inn.get(k, set())
        tp += len(a & b); fp += len(b - a); fn += len(a - b)
        if a != b:
            per.append((k, sorted(a - b), sorted(b - a)))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return {
        "numbers": {"drawn": len(drawn), "found": len(found & drawn), "extra": sorted(found - drawn), "missing": sorted(drawn - found)},
        "kinds": {"ok": kinds_ok, "of": len(found & drawn)},
        "adjacency": {"tp": tp, "fp": fp, "fn": fn, "precision": round(prec, 3), "recall": round(rec, 3)},
        "transformers": {"found": len(imp_raw and [n for n in imp_raw["nodes"] if n["kind"] == "transformer"]), "truth": len([n for n in truth_raw["nodes"] if n["kind"] == "transformer"])},
        "questions": len(cand["questions"]),
        "mismatches": per[:15],
    }


def main(argv):
    pdf = Path(argv[1]) if len(argv) > 1 else ROOT / "data/sites/SITE-01/drawings/SITE-01_sld.pdf"
    truth = Path(argv[2]) if len(argv) > 2 else ROOT / "data/sites/SITE-01/truth/topology.json"
    r = evaluate(pdf, truth)
    n, k, a = r["numbers"], r["kinds"], r["adjacency"]
    print("| 項目 | 値 |\n|---|---|")
    print(f"| 開閉器番号の再現 | {n['found']} / {n['drawn']}（見つからず {len(n['missing'])}、余計 {len(n['extra'])}） |")
    print(f"| 種別の正答 | {k['ok']} / {k['of']} |")
    print(f"| 隣接の一致 precision / recall | {a['precision']} / {a['recall']}（TP {a['tp']} FP {a['fp']} FN {a['fn']}） |")
    print(f"| 変圧器 | {r['transformers']['found']} / {r['transformers']['truth']} |")
    print(f"| 質問（人に確かめること） | {r['questions']} |")
    if n["missing"]:
        print(f"\n見つからなかった番号: {', '.join(n['missing'][:20])}{' …' if len(n['missing']) > 20 else ''}")
    if r["mismatches"]:
        print("\n隣接の食い違い（番号: 真値にだけ / 取込にだけ）")
        for k_, miss, extra in r["mismatches"]:
            print(f"- {k_}: {miss} / {extra}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
