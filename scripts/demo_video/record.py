"""MAAI の 3 分デモ動画の画面収録（docs/demo-plan.md の秒割りに沿って、画面を順に操作して録画する）。

    MAAI_OFFLINE=1 uvicorn server.app:app --port 8000      # 別の端末で先に起動
    python scripts/demo_video/record.py --out OUTDIR        # OUTDIR/rec/*.webm と OUTDIR/segments.json

1920x1080・拡大率 1 で録画する。各行は「操作 → 台本の秒数まで待つ」。操作が長引いた行は
segments.json の実際の秒数が台本より長くなり、compose.py が速度で合わせる。
外には何も送らない（http://localhost:8000 だけを開く）。
"""
from __future__ import annotations

import argparse
import base64
import glob
import io
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 台本の行（語り v4）。dur は台本の長さ（秒）。s6（構想映像）と s7（締めの札）は compose.py がつなぐ。
LINES = [
    ("s1", "0:00-0:15", 15, "機器を取り替える日も、変電所は全部は止められません。止める範囲は減らしたい。でもその案で大丈夫か。今は図面を見ながら、頭の中で想像しています。"),
    ("s2", "0:15-0:45", 30, "MAAI は、単線結線図と、平面図・断面図を読んで、構内の 3D を組み立てます。機器の位置と高さは図面から、どこがつながっているかは結線図から。読めなかったところは、要確認として人に返します。"),
    ("s2b", "0:45-1:05", 20, "工事の依頼は文章で来ます。Claude がそこから、取り替える機器、止められない設備、置き場、重さを読み取ります。番号が本当にあるかは計算で確かめ、入れるかどうかは人が決めます。"),
    ("s3", "1:05-1:25", 20, "取り替える機器に電気が流れ込んでくる側すべてで、最初の断路器まで切る範囲が出ます。緑が停電、赤が充電。見えなかった充電部が、目に見えるようになります。"),
    ("s4", "1:25-2:00", 35, "次はクレーンです。新任の私には、どのクレーンにするかがすぐには分かりません。MAAI は、吊る場所と置き場と重さから、充電部に近づかずに吊れる一番小さいクレーンを計算で選びます。今回は 35t 級。依頼文で 1 号バンクは止められないので、追加で止める案は出しません。止められるなら 25t 級、という比較は残します。"),
    ("s5", "2:00-2:20", 20, "判定は計算で行い、根拠の表も残します。Claude に送る前に、名前や定格値は符号に置き換えます。採否は人が決め、停止範囲の結線図と、クレーンの位置を描いた平面図を書き出します。"),
]

REQ_TEXT = ("次の作業日に、66kV 1号ダイヤの遮断器 6T-110 を取り替えます。新しい遮断器は約 3.5 t です。資材は取り替える遮断器の西側、"
            "8 m ほど離れた空き地に仮置きします。1号バンクは系統の都合で今回は止められません。東線1L・東線2L は通常どおり運用します。")
REQ_TEXT_HEAD = "次の作業日に"


def mask_demo_html() -> str:
    """Claude に送る前の置き換えを、実物の関数（agent/mask.py）に合成データの文を通して見せる。"""
    import html as _h
    sys.path.insert(0, str(ROOT))
    from agent.mask import Mask
    topo = json.loads((ROOT / "data/sites/SITE-01/truth/topology.json").read_text(encoding="utf-8"))
    line = next(n["name"] for n in topo["nodes"] if n["kind"] == "source")
    amp = f"{2 * 1000}A"   # 定格値の例（公開前チェックの定格値の検出に当たらないよう、コードで組む）
    before = f"{line} の 20E1-110 遮断器（定格 {amp}）を、合成変電所 の 220kV 母線から切り離す。クレーンとの距離 4.02 m、吊る重さ 3.5 t"
    after = Mask().text(before)
    # 依頼文を Claude に読ませたときの、実際の送信記録（logs/outbound/*-structure.request.json の request）があればそれを見せる
    logs = sorted(glob.glob(str(ROOT / "logs/outbound/*-structure.request.json")), key=lambda f: Path(f).stat().st_mtime)
    for f in reversed(logs):
        u = json.loads(Path(f).read_text(encoding="utf-8")).get("user", {})
        if isinstance(u, dict) and str(u.get("request", "")).startswith(REQ_TEXT_HEAD):
            before, after = REQ_TEXT, u["request"]
            break
    box = "background:#11161c;border:1px solid #3a4452;border-radius:10px;padding:28px 36px;font-size:40px;line-height:1.6;width:1600px"
    return (f'<div id="__ov" style="position:fixed;inset:0;z-index:99999;background:#0b0e12;display:flex;flex-direction:column;'
            f'align-items:center;justify-content:center;gap:30px;color:#e6e8eb;font-family:\'Noto Sans CJK JP\',\'Noto Sans JP\',sans-serif">'
            f'<div style="font-size:34px;color:#8b949e">Claude に送る前（agent/mask.py が置き換える。電圧・距離・重さは計算に要るので残す）</div>'
            f'<div style="{box}"><span style="color:#8b949e;font-size:28px">手元の文</span><br>{_h.escape(before)}</div>'
            f'<div style="font-size:48px">↓</div>'
            f'<div style="{box};border-color:#4ea1ff"><span style="color:#4ea1ff;font-size:28px">送る文（logs/outbound/ に記録）</span><br>{_h.escape(after)}</div></div>')


def pdf_png(pdf: Path, k: float = 1.0) -> bytes:
    import pypdfium2 as pdfium

    page = pdfium.PdfDocument(str(pdf))[0]
    w, h = page.get_size()
    img = page.render(scale=min(1880 / w, 1040 / h) * k).to_pil()
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--debug", action="store_true", help="行ごとの終わりに PNG を dbg/ へ")
    a = ap.parse_args()
    out = Path(a.out)
    rec = out / "rec"
    rec.mkdir(parents=True, exist_ok=True)
    for f in glob.glob(str(rec / "*.webm")):
        Path(f).unlink()
    (out / "dbg").mkdir(exist_ok=True)

    from playwright.sync_api import sync_playwright

    segs: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1,
                                  record_video_dir=str(rec), record_video_size={"width": 1920, "height": 1080})
        ctx.add_init_script("try{localStorage.setItem('maai.onboarded','1');localStorage.setItem('maai.json','1')}catch(e){}")  # 初回の案内を出さない・内部データの列を従来どおり出す
        t0 = time.monotonic()
        page = ctx.new_page()

        def el() -> float:
            return time.monotonic() - t0

        ctx.request.post(a.url + "/api/site/SITE-01/layout/use-truth")  # 前の収録で「この 3D で続ける」を押した状態が残っていても、合成データから始める
        page.goto(a.url)
        page.wait_for_function("document.querySelector('#hud') && !document.querySelector('#hud').textContent.includes('読み込み中')", timeout=120000)
        page.wait_for_timeout(1500)

        def click(sel: str):
            # Playwright の click は描画の安定を待って 1 回 8 秒ほどかかる（ソフトウェア描画で 2 コマ/秒）ため、ページ内で押す
            page.evaluate("s=>document.querySelector(s).click()", sel)

        def tab(s: str):
            click(f'#prog [data-goto="{s}"]')

        def smooth(sel: str, block: str = "start"):
            page.evaluate("([s,b])=>{const e=document.querySelector(s); if(e) e.scrollIntoView({behavior:'instant',block:b});}", [sel, block])

        def pan(pdf: Path, hold: int):
            """図面 1 枚を画面いっぱいに出し、ゆっくり寄せる（CSS の変形。録画が低いコマ数でも滑らかに見える）。"""
            b64 = base64.b64encode(pdf_png(pdf, 2.0)).decode()
            page.evaluate("""([b,ms])=>{const o=document.getElementById('__ov'); if(o) o.remove(); const d=document.createElement('div'); d.id='__ov';
              d.style.cssText='position:fixed;inset:0;z-index:99999;background:#fff;overflow:hidden';
              d.innerHTML='<img id="__pan" style="position:absolute;left:0;top:0;width:1920px;height:1080px;object-fit:contain;transform-origin:50% 45%;transform:scale(1);transition:transform '+ms+'ms linear" src="data:image/png;base64,'+b+'">';
              document.body.appendChild(d); requestAnimationFrame(()=>requestAnimationFrame(()=>{document.getElementById('__pan').style.transform='scale(1.35)';}));}""", [b64, hold])
            page.wait_for_timeout(hold)

        def shot(name: str):
            if a.debug:
                page.screenshot(path=str(out / "dbg" / f"{name}.png"))

        def run(sid: str):
            if sid == "s1":
                # 図面（一般平面図 → 機械器具装置図〈平面・断面〉→ 単線結線図）をゆっくり寄せて見せる
                for name, hold in (("SITE-01_plan.pdf", 4500), ("SITE-01_layout.pdf", 5000), ("SITE-01_sld.pdf", 4500)):
                    pan(ROOT / "data/sites/SITE-01/drawings" / name, hold)
                page.evaluate("()=>{const o=document.getElementById('__ov'); if(o) o.remove();}")
            elif sid == "s2":
                tab("s0")
                page.set_input_files("#ingestFile", str(ROOT / "data/sites/SITE-01/drawings/SITE-01_sld.pdf"))
                page.wait_for_timeout(800)
                click("#btnIngest")
                page.wait_for_selector("#btnConfirmAll", timeout=240000)   # Claude の意味づけを待つ（待ちの静止は compose が縮める）
                page.wait_for_timeout(1800)
                page.evaluate("()=>{const h=[...document.querySelectorAll('#ingestBox h4')].find(x=>x.textContent.includes('確かめてほしい')); if(h) h.scrollIntoView({behavior:'instant',block:'start'});}")
                shot("s2_questions")
                page.wait_for_timeout(5500)
                smooth("#btnConfirmAll", "center")
                page.wait_for_timeout(1800)
                click("#btnConfirmAll")
                page.wait_for_timeout(2500)
                click("#btnLayoutSample")
                page.wait_for_selector("#miniR canvas", timeout=90000)
                page.wait_for_timeout(2500)
                smooth("#miniL", "start")
                page.wait_for_timeout(3500)
                page.evaluate("()=>{const t=document.querySelector('#layoutBox table'); if(t) t.scrollIntoView({behavior:'instant',block:'center'});}")
                page.wait_for_timeout(3000)
                page.wait_for_function("()=>{const b=document.querySelector('#btnUseDraft'); return b && !b.disabled}", timeout=30000)
                smooth("#btnUseDraft", "center")
                page.wait_for_timeout(1500)
                click("#btnUseDraft")  # 「この 3D で続ける」（要確認があるときは「要確認 n 件を確認のうえ続ける」）
                page.wait_for_selector("#srcBadge:has-text('図面から起こした配置')", timeout=30000)
                smooth("#hud", "start")
                page.wait_for_timeout(2000)  # バッジが変わったのを見せる
            elif sid == "s2b":
                tab("s1")
                page.wait_for_timeout(1000)
                page.evaluate("(t)=>{const e=document.getElementById('reqText'); e.value=t;}", REQ_TEXT)
                smooth("#reqText", "start")
                page.wait_for_timeout(2500)
                click("#btnIntake")
                page.wait_for_selector("#intakeBox .bay", timeout=120000)   # Claude の返事を待つ（待ちの静止は compose が縮める）
                page.wait_for_timeout(1000)
                shot("s2b_intake")
                smooth("#intakeBox", "start")
                page.wait_for_timeout(5000)
                click("#btnIntakeUse")
                page.wait_for_selector("#stepsBox .bay", timeout=30000)
                page.wait_for_timeout(1500)
            elif sid == "s3":
                tab("s1")
                page.wait_for_timeout(1200)
                smooth("#stepsBox", "start")
                page.wait_for_timeout(2000)
                click('#sldZoom button[data-z="2.6"]')
                page.wait_for_timeout(2500)
                num = page.eval_on_selector("#stepsBox .sw .id", "e=>e.textContent")
                shot("s3_green")
                mk = page.locator(f'.mk[title^="{num} "]').first
                mk.evaluate("e=>e.scrollIntoView({block:'center',inline:'center'})")
                page.wait_for_timeout(1500)
                mk.evaluate("e=>e.click()")
                shot("s3_red")
                page.wait_for_timeout(2000)
                mk.evaluate("e=>e.click()")
                page.wait_for_timeout(1500)
                click("#btnViewToggle")  # 3D へ
                page.wait_for_timeout(800)
                click("#vTarget")
            elif sid == "s4":
                tab("s2")
                page.wait_for_timeout(1000)
                click("#btnSelect")
                page.wait_for_selector("#selectBox .big", timeout=60000)
                page.wait_for_timeout(1500)
                smooth("#selectBox", "start")
                shot("s4_select")
                page.wait_for_timeout(6000)
                smooth("#selectBox .bay:last-of-type", "center")   # 止められない設備（依頼文）と、止められる場合の参考
                page.wait_for_timeout(5000)
                click("#btnAdoptSel")  # 選んだクラスを置く
                page.wait_for_timeout(4000)
                smooth("#verdictBox", "start")
            elif sid == "s5":
                # 根拠: 3D の上の帯（離隔表の ID と「要確認」）と、導体ごとの距離・必要・余裕の表
                smooth("#verdictBox", "start")
                page.wait_for_timeout(3000)
                shot("s5_evidence")
                # Claude に送る前の置き換え（3 秒）
                page.evaluate("(h)=>{const d=document.createElement('div'); d.innerHTML=h; document.body.appendChild(d.firstElementChild);}", mask_demo_html())
                shot("s5_mask")
                page.wait_for_timeout(3200)
                page.evaluate("()=>{const o=document.getElementById('__ov'); if(o) o.remove();}")
                tab("s3")
                page.wait_for_timeout(1200)
                click("#btnApprove")
                page.wait_for_selector("#approveBox .bay", timeout=60000)
                page.wait_for_timeout(1500)

                def overlay(name: str, hold: int):
                    pdfs = sorted(glob.glob(str(ROOT / f"data/sites/SITE-01/approved/plan-*/{name}")), key=lambda f: Path(f).stat().st_mtime)
                    if not pdfs:
                        print("PDF が無い:", name, file=sys.stderr)
                        return
                    b64 = base64.b64encode(pdf_png(Path(pdfs[-1]))).decode()
                    page.evaluate("""(b)=>{const o=document.getElementById('__ov'); if(o) o.remove(); const d=document.createElement('div'); d.id='__ov';
                      d.style.cssText='position:fixed;inset:0;z-index:99999;background:#222;display:flex;align-items:center;justify-content:center';
                      d.innerHTML='<img style="max-width:1900px;max-height:1060px;background:#fff" src="data:image/png;base64,'+b+'">'; document.body.appendChild(d);}""", b64)
                    page.wait_for_timeout(hold)

                overlay("step-1-sld.pdf", 4000)
                overlay("plan-crane.pdf", 4500)

        for sid, scr, dur, text in LINES:
            s = el()
            run(sid)
            shot(sid + "_end")
            rest = s + dur - el()
            if rest > 0:
                page.wait_for_timeout(int(rest * 1000))
            segs.append({"id": sid, "script": scr, "start": round(s, 2), "end": round(el(), 2), "target_sec": dur, "text": text})
            print(sid, segs[-1]["start"], segs[-1]["end"], "(台本", dur, "秒)", flush=True)
        ctx.close()
        browser.close()

    vids = sorted(glob.glob(str(rec / "*.webm")))
    if len(vids) != 1:
        print("録画が1本でない:", vids, file=sys.stderr)
        return 1
    (out / "segments.json").write_text(json.dumps({"video": vids[0], "segments": segs}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("録画:", vids[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
