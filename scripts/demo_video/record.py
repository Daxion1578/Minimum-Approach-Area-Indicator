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

# 台本の行。dur は台本の長さ（秒）。s1 は先頭 5 秒が題の札なので、録画するのは 15 秒。
LINES = [
    ("s1", "0:00-0:20", 15, "機器を取り替える日も、変電所は全部は止められません。隣には電気の流れる線が残り、そこへクレーンが入ります。近づいてはいけない距離は、図面のどこにも描かれていない。担当者の頭の中と、現場で見張る人の目の中にあります。MAAI、間合い。見えない間合いを、見えるようにする道具です。"),
    ("s2", "0:20-0:48", 28, "入口は、いつもの単線結線図です。線と記号と番号から、つながりを起こします。つながりを決めるのは計算。Claude は記号の種別を確かめ、迷った所を人への質問にします。装置図と断面図からは、機器の位置と高さを読んで3Dを組み立て直します。読めなかった所は、要確認として人に戻します。"),
    ("s3", "0:48-1:13", 25, "この日に取り替えるのは66kVの遮断器。電気が流れ込む端すべてで、最初の断路器まで切ります。緑が停電、赤が充電。開閉器を押せば、その場で塗り替わる。接地を取ることは、計画の条件として必ず書きます。"),
    ("s4", "1:13-1:48", 35, "クレーンは小さいほど安い。ブームは取り替える機器の真上と、資材置場の真上に来ます。その2点と重さから、届いて、吊れて、充電部に近づかない一番小さいクレーンを計算で選ぶ。答えは50t級。一つ下は、1号変圧器の線に近づきすぎて使えない。では、その変圧器も止めたら。25t級で済む。止めるかどうかは、人が決めます。"),
    ("s5", "1:48-2:13", 25, "承認は人。承認の瞬間にもう一度判定し直し、不可の計画と、クレーンの無い計画は承認できません。停止範囲図と、接地や追加停止の条件が書き出されます。"),
    ("s6", "2:13-2:21", 8, "安全の判断は計算で、説明はClaudeで。Claudeの出力は計算コードで確かめ直してから出し、採否は人が決めます。"),
]

CARD_HTML = """<div id="__ov" style="position:fixed;inset:0;z-index:99999;background:#000;display:flex;flex-direction:column;
align-items:center;justify-content:center;gap:56px;color:#fff;font-family:'Noto Sans CJK JP','Noto Sans JP',sans-serif;font-size:60px;font-weight:700">
<div>安全の判断は計算で、説明は Claude で</div><div>Claude の出力は計算コードで確かめ直す</div><div>採否は人が決める</div></div>"""


def pdf_png(pdf: Path) -> bytes:
    import pypdfium2 as pdfium

    page = pdfium.PdfDocument(str(pdf))[0]
    w, h = page.get_size()
    img = page.render(scale=min(1880 / w, 1040 / h)).to_pil()
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
        t0 = time.monotonic()
        page = ctx.new_page()

        def el() -> float:
            return time.monotonic() - t0

        page.goto(a.url)
        page.wait_for_function("document.querySelector('#hud') && !document.querySelector('#hud').textContent.includes('読み込み中')", timeout=120000)
        page.wait_for_timeout(1500)

        def click(sel: str):
            # Playwright の click は描画の安定を待って 1 回 8 秒ほどかかる（ソフトウェア描画で 2 コマ/秒）ため、ページ内で押す
            page.evaluate("s=>document.querySelector(s).click()", sel)

        def tab(s: str):
            click(f'.tabs button[data-step="{s}"]')

        def smooth(sel: str, block: str = "start"):
            page.evaluate("([s,b])=>{const e=document.querySelector(s); if(e) e.scrollIntoView({behavior:'instant',block:b});}", [sel, block])

        def shot(name: str):
            if a.debug:
                page.screenshot(path=str(out / "dbg" / f"{name}.png"))

        def run(sid: str):
            if sid == "s1":
                click("#vAll")
                page.mouse.move(1300, 600)
                page.wait_for_timeout(1500)
                page.mouse.down()
                for i in range(6):  # ゆっくり回して立体に見せる
                    page.mouse.move(1300 - i * 40, 600 - i * 5)
                page.mouse.up()
                page.wait_for_timeout(2500)
                click("#vAll")
            elif sid == "s2":
                tab("s0")
                page.set_input_files("#ingestFile", str(ROOT / "data/sites/SITE-01/drawings/SITE-01_sld.pdf"))
                page.wait_for_timeout(800)
                click("#btnIngest")
                page.wait_for_selector("#btnConfirmAll", timeout=60000)
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
            elif sid == "s3":
                tab("s1")
                page.wait_for_timeout(1200)
                click("#btnSteps")
                page.wait_for_selector("#stepsBox .bay", timeout=30000)
                page.wait_for_timeout(2500)
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
                click("#btnAdoptSel")  # 50t を置く
                page.wait_for_timeout(4000)
                smooth("#btnAdoptOutage", "center")
                page.wait_for_timeout(3500)
                click("#btnAdoptOutage")
                page.wait_for_timeout(2500)
                smooth("#verdictBox", "start")
            elif sid == "s5":
                tab("s3")
                page.wait_for_timeout(2000)
                smooth("#planConds", "start")
                page.wait_for_timeout(5000)
                click("#btnApprove")
                page.wait_for_selector("#approveBox .bay", timeout=60000)
                page.wait_for_timeout(2500)
                pdfs = sorted(glob.glob(str(ROOT / "data/sites/SITE-01/approved/plan-*/step-1-sld.pdf")), key=lambda f: Path(f).stat().st_mtime)
                if pdfs:
                    b64 = base64.b64encode(pdf_png(Path(pdfs[-1]))).decode()
                    page.evaluate("""(b)=>{const d=document.createElement('div'); d.id='__ov';
                      d.style.cssText='position:fixed;inset:0;z-index:99999;background:#222;display:flex;align-items:center;justify-content:center';
                      d.innerHTML='<img style="max-width:1900px;max-height:1060px;background:#fff" src="data:image/png;base64,'+b+'">'; document.body.appendChild(d);}""", b64)
            elif sid == "s6":
                page.evaluate("()=>{const o=document.getElementById('__ov'); if(o) o.remove();}")
                page.evaluate("(h)=>{const d=document.createElement('div'); d.innerHTML=h; document.body.appendChild(d.firstElementChild);}", CARD_HTML)

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
