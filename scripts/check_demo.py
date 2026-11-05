"""台本どおりの流れを、サーバを立てずに通しで確かめる（Claude は呼ばない）。

    python scripts/check_demo.py              # 結果の表を画面に出す
    python scripts/check_demo.py --out FILE   # 同じ表を Markdown で FILE に追記（GitHub Actions の Summary 用）

流れ: 図面取込 → 66kV 遮断器（66-D1-CB1）の作業日の停止範囲 → 重機の選定（一番小さいクラス）→ 追加停止で小さくできるか
→ 採用した配置の離隔判定 → 承認（停止範囲図 PDF）→ 重機の無い計画・不可の計画は承認できない。
一つでも不合格なら終了コード 1。
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

TARGET = "66-D1-CB1"


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

    tmp = Path(tempfile.mkdtemp()) / "sites"
    (tmp / "SITE-01").mkdir(parents=True)
    shutil.copytree(real / "SITE-01" / "truth", tmp / "SITE-01" / "truth")
    appmod.SITES = tmp
    appmod.load_site.cache_clear()

    normal = c.get("/api/sites/SITE-01").json()["states"]["normal"]
    st = c.post("/api/sites/SITE-01/steps", json={"targets": [TARGET], "state": normal}).json()
    ok = st.get("ok") and len(st.get("ops", [])) == 3 and st.get("conditions")
    rows.append(("2 作業日の停止範囲（66kV 遮断器）", bool(ok), "切る: " + "、".join(o["number"] or o["id"] for o in st.get("ops", [])) or "; ".join(st.get("problems", []))))
    day = st["state"]

    sel = c.post("/api/sites/SITE-01/select", json={"state": day, "pick_id": TARGET}).json()
    ch = sel.get("chosen") or {}
    rows.append(("3 重機の選定（一番小さいクラス）", bool(sel.get("ok")),
                 f"{ch.get('name')}（{ch.get('verdict_ja')}、最小 {ch.get('min_distance_m')} m／必要 {ch.get('required_m')} m）。一つ下が使えない理由: {sel.get('smaller_why_not')}" if ch else "; ".join(sel.get("problems", []))))

    wo = sel.get("with_outage") or {}
    ch2 = wo.get("chosen")
    rows.append(("4 追加停止で小さくできるか", bool(ch2), wo.get("note") or "追加停止の案が無い"))

    state2, crane2 = (wo["state"], ch2["crane"]) if ch2 else (day, ch.get("crane"))
    cl = c.post("/api/sites/SITE-01/clearance", json={"state": state2, "crane": crane2}).json()["clearance"]
    rows.append(("5 採用した配置の離隔判定", cl["verdict"] != "ng" and cl["verdict"] == (ch2 or ch)["verdict"],
                 f"{cl['verdict_ja']}: {cl['reasons'][0]}"))

    r = c.post("/api/sites/SITE-01/approve", json={"state": state2, "crane": crane2, "clearance": cl, "steps": st})
    a = r.json()
    pdfs = [f for f in a.get("files", []) if f.endswith(".pdf")]
    ok = r.status_code == 200 and len(pdfs) >= 2 and not a.get("drawing_error")
    rows.append(("6 承認と書き出し", ok, f"承認ハッシュ {str(a.get('approval_hash', ''))[:12]}…、停止範囲図 PDF {len(pdfs)} 枚" if r.status_code == 200 else f"失敗 {r.status_code}"))

    no_crane = c.post("/api/sites/SITE-01/approve", json={"state": day})
    bad = c.post("/api/sites/SITE-01/approve", json={"state": normal, "crane": dict(crane2, base=[34.0, 44.0], boom_elev_deg=30)})
    rows.append(("7 重機の無い計画・不可は承認できない", no_crane.status_code == 400 and bad.status_code == 400,
                 f"重機なし HTTP {no_crane.status_code}、不可 HTTP {bad.status_code}"))
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
