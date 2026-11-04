"""台本どおりの流れを、サーバを立てずに通しで確かめる（Claude は呼ばない）。

    python scripts/check_demo.py              # 結果の表を画面に出す
    python scripts/check_demo.py --out FILE   # 同じ表を Markdown で FILE に追記（GitHub Actions の Summary 用）

流れ: 図面取込 → 2BK の停止ステップ 段階 3 → 離隔判定「不可」→ 修正案「起伏角 65°」→ 再判定「可」→ 承認（塗り分け PDF）。
クレーンは画面の初期値のまま。一つでも不合格なら終了コード 1。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["MAAI_OFFLINE"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

import server.app as appmod  # noqa: E402

CRANE = {"base": [88, 72], "heading_deg": 0, "boom_len_m": 14, "boom_elev_deg": 45, "slew_deg": [-50, 50],
         "hook_drop_m": 2, "load": {"w": 2.0, "d": 2.0, "h": 2.5}}


def run() -> list[tuple[str, bool, str]]:
    rows: list[tuple[str, bool, str]] = []
    real = appmod.SITES
    c = TestClient(appmod.app)

    pdf = real / "SITE-01" / "drawings" / "SITE-01_sld.pdf"
    j = c.post("/api/ingest", files={"file": ("sld.pdf", pdf.read_bytes(), "application/pdf")}).json()
    ev = j.get("eval") or {}
    num, adj = ev.get("numbers", {}), ev.get("adjacency", {})
    ok = num.get("found", 0) >= 130 and adj.get("precision", 0) >= 0.95
    rows.append(("1 図面取込", ok, f"開閉器番号 {num.get('found')}/{num.get('drawn')}、隣接 precision {adj.get('precision')} / recall {adj.get('recall')}、質問 {ev.get('questions')}"))

    # 承認の書き出しは一時ディレクトリへ（リポジトリを汚さない）
    tmp = Path(tempfile.mkdtemp()) / "sites"
    (tmp / "SITE-01").mkdir(parents=True)
    shutil.copytree(real / "SITE-01" / "truth", tmp / "SITE-01" / "truth")
    appmod.SITES = tmp
    appmod.load_site.cache_clear()

    normal = c.get("/api/sites/SITE-01").json()["states"]["normal"]
    st = c.post("/api/sites/SITE-01/steps", json={"targets": ["TR-2"], "state": normal}).json()
    ok = st.get("ok") and len(st.get("steps", [])) == 3
    rows.append(("2 停止ステップ（2BK）", bool(ok), " → ".join(s["title"] for s in st.get("steps", [])) or "; ".join(st.get("problems", []))))
    final = st["steps"][-1]["state"]

    cl = c.post("/api/sites/SITE-01/clearance", json={"state": final, "crane": CRANE}).json()["clearance"]
    rows.append(("3 離隔判定（段階 3）", cl["verdict"] == "ng", f"{cl['verdict_ja']}: {cl['reasons'][0]}"))

    pr = c.post("/api/sites/SITE-01/propose", json={"state": final, "crane": CRANE}).json()
    pick = next((x for x in pr["candidates"] if x["kind"] == "elev" and x["crane"]["boom_elev_deg"] == 65), None)
    rows.append(("4 修正案「起伏角 65°」", bool(pick and pick["verdict"] == "ok"),
                 f"{pick['verdict_ja']}（最小 {pick['min_distance_m']:.2f} m／必要 {pick['required_m']:.2f} m）" if pick else "候補に無い"))

    crane2 = pick["crane"] if pick else CRANE
    cl2 = c.post("/api/sites/SITE-01/clearance", json={"state": final, "crane": crane2}).json()["clearance"]
    r = c.post("/api/sites/SITE-01/approve", json={"state": final, "crane": crane2, "clearance": cl2, "steps": st})
    a = r.json()
    pdfs = [f for f in a.get("files", []) if f.endswith(".pdf")]
    ok = r.status_code == 200 and len(pdfs) >= 4 and not a.get("drawing_error")
    rows.append(("5 承認と書き出し", ok, f"承認ハッシュ {str(a.get('approval_hash', ''))[:12]}…、PDF {len(pdfs)} 枚" if r.status_code == 200 else f"失敗 {r.status_code}"))

    bad = c.post("/api/sites/SITE-01/approve", json={"state": final, "crane": CRANE})
    rows.append(("6 不可は承認できない", bad.status_code == 400, f"HTTP {bad.status_code}"))
    return rows


def to_markdown(rows: list[tuple[str, bool, str]]) -> str:
    lines = ["## 通しの確認（Claude を呼ばない経路）", "", "| 段階 | 結果 | 中身 |", "|---|---|---|"]
    lines += [f"| {name} | {'✅ 合格' if ok else '❌ 不合格'} | {detail} |" for name, ok, detail in rows]
    passed = sum(1 for _, ok, _ in rows if ok)
    lines += ["", f"**{passed} / {len(rows)} 合格**", ""]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="Markdown を追記するファイル（GitHub Actions では $GITHUB_STEP_SUMMARY）")
    args = ap.parse_args()
    rows = run()
    md = to_markdown(rows)
    print(md)
    if args.out:
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(md + "\n")
    return 0 if all(ok for _, ok, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
