"""MAAI の 3 分デモ動画の画面収録（docs/demo-plan.md の秒割りに沿って、画面を順に操作して録画する）。

    MAAI_OFFLINE=1 uvicorn server.app:app --port 8000      # 別の端末で先に起動
    python scripts/demo_video/record.py --out OUTDIR        # OUTDIR/rec/*.webm と OUTDIR/segments.json

1920x1080・拡大率 1 で録画する。各行は「操作 → 台本の秒数まで待つ」。操作が長引いた行は
segments.json の実際の秒数が台本より長くなり、compose.py が速度で合わせる。
外には何も送らない（http://localhost:8000 だけを開く）。

画面は「3D を全面にし、操作を浮かべる HUD」（web/hud.js）。答えは 3D の上の板（#hudAnswer・#hudBar・#hudCard）に出るので、
左の引き出し（#hudDrawer。元の左パネルがそのまま入っている）は、根拠や一覧を見せる場面だけ短く開く。
引き出しの中の要素は閉じていると見えないので、待つときは state="attached"、押すときはページ内で .click() する。
window.hud が無い（旧画面）ときは、引き出しの開閉と 3D 上の見せ場を飛ばして旧画面の手順で録る。
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

ROOT = Path(__file__).resolve().parents[3]

# 台本の行（語り v4）。dur は台本の長さ（秒）。s6（構想映像）と s7（締めの札）は compose.py がつなぐ。
LINES = [   # v9 の C5〜C8（scripts/self.txt）。dur は最低の長さ（秒）。compose9 が語りに合わせて速さを変える
    ("c5", "C5", 16, "まず、図面を入れる。構内の形と電気のつながりが、一緒に立体になる。二つの図面で機器がそろっているかを確かめ、読み切れない所は人に返す。"),
    ("c6", "C6", 20, "工事の依頼文を貼ると、Claude が機器と条件を読み取る。送る前に、名前と定格値は、符号に置き換える。取り替える遮断器が決まると、切る開閉器が計算で出る。送電線は、相手端も切る。"),
    ("c7", "C7", 30, "平面図で資材の置き場を決め、重さを入れる。10トンを吊るのに、100トン級。重さだけなら25トン級でも、母線から離れるには足りない。据えてよい所は、緑のマス。動かすと、その場所で使える級に選び直す。母線は止められないと依頼文にあるので、止める案は出さない。決めるのは、人。"),
    ("c8", "C8", 14, "この配置で OK を押すと、承認。停止範囲の結線図と、クレーンの配置図が出る。これで、期限までに申請できる。"),
]

REQ_TEXT = ("次の作業日に、220kV 東線1L の遮断器 20E1-110 を取り替えます。新しい遮断器は約 10 t です。資材は取り替える遮断器の西側、"
            "6 m ほど離れた空き地に仮置きします。東線1L は相手端も含めて停止します。220kV 母線 A 区間は系統の都合で今回は止められません。")
REQ_TEXT_HEAD = "次の作業日に"


def mask_demo_html() -> str:
    """Claude に送る前の置き換えを、実物の関数（agent/mask.py）に合成データの文を通して見せる。"""
    import html as _h
    sys.path.insert(0, str(ROOT))
    from agent.mask import Mask
    topo = json.loads((ROOT / "data/sites/SITE-01/truth/topology.json").read_text(encoding="utf-8"))
    line = next(n["name"] for n in topo["nodes"] if n["kind"] == "source")
    amp = f"{2 * 1000}A"   # 定格値の例（公開前チェックの定格値の検出に当たらないよう、コードで組む）
    before = f"{line} の 20E1-110 遮断器（定格 {amp}）を、合成変電所 の 220kV 母線から切り離す。クレーンとの距離 8.08 m、吊る重さ 10 t"
    after = Mask().text(before)
    # 依頼文を Claude に読ませたときの、実際の送信記録（logs/outbound/*-structure.request.json の request）があればそれを見せる
    logs = sorted(glob.glob(str(ROOT / "logs/outbound/*-structure.request.json")), key=lambda f: Path(f).stat().st_mtime)
    for f in reversed(logs):
        u = json.loads(Path(f).read_text(encoding="utf-8")).get("user", {})
        if isinstance(u, dict) and str(u.get("request", "")).startswith(REQ_TEXT_HEAD):
            before, after = REQ_TEXT, u["request"]
            break
    box = "background:#11161c;border:1px solid #3a4452;border-radius:10px;padding:28px 36px;font-size:34px;line-height:1.5;width:1600px"
    return (f'<div id="__ov" style="position:fixed;inset:0;z-index:99999;background:#0b0e12;display:flex;flex-direction:column;'
            f'align-items:center;justify-content:flex-start;padding-top:70px;gap:22px;color:#e6e8eb;font-family:\'Noto Sans CJK JP\',\'Noto Sans JP\',sans-serif">'
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


# ページ内で押す・探すための小さな JS（Playwright の click は描画の安定を待って 1 回 8 秒ほどかかる（ソフトウェア描画で 2 コマ/秒）ため、ページ内で押す）
JS_CLICK = "s=>{const e=document.querySelector(s); if(!e) throw new Error('無い: '+s); e.click();}"
JS_SCROLL = "([s,b])=>{const e=document.querySelector(s); if(e) e.scrollIntoView({behavior:'instant',block:b});}"
JS_SCROLL_TEXT = "([c,ws,b])=>{const e=[...document.querySelectorAll(c)].find(x=>ws.some(w=>x.textContent.includes(w))); if(e) e.scrollIntoView({behavior:'instant',block:b}); return !!e;}"
JS_HUD = "async ([n,a])=>{const h=window.hud; if(!h || typeof h[n]!=='function') return false; const r=h[n](...a); if (r && typeof r.then==='function') await r; return true;}"
JS_MARK = "k=>((window.__rec&&window.__rec.n[k])||0)"
JS_WAIT_MARK = "([k,n])=>((window.__rec&&window.__rec.n[k])||0)>n"
# 読み込みの終わり: サイトの表が出て、最初の判定が描かれた（window.maai.lastCounts）。#hud は隠れるが文字は入るので、旧画面では文字で見る
JS_READY = ("()=>{ if(!document.querySelector('#siteSummary tr')) return false; const m=window.maai; if (m && m.lastCounts) return true;"
            " const h=document.querySelector('#hud'); return !!h && !h.textContent.includes('読み込み中'); }")
# 下のバーの級のタイル（0=選んだ級、1=一つ上、2=二つ上）。文言は zoneSets の class（'50t' など）で探し、HUD が無ければ引き出しの #zoneBox の釦を押す
JS_ZONE_TILE = """(k)=>{ const m=window.maai, sets=(m&&m.zoneSets)||[]; const cls=sets[k]&&String(sets[k].class);
  const tiles=[...document.querySelectorAll('#hudBar .tile')];
  let t = document.querySelector('#hudBar .tile[data-act="zone"][data-i="'+k+'"]');
  if (!t && cls) t = tiles.find(b=>b.textContent.replace(/\\s+/g,'').includes(cls)) || null;
  if (!t){ const cl=tiles.filter(b=>/\\d+(\\.\\d)?t/.test(b.textContent)); t=cl[k]||null; }
  if (t){ t.click(); return t.textContent.trim().replace(/\\s+/g,' '); }
  const z=document.querySelectorAll('#zoneBox .zbtn')[k]; if (z){ z.click(); return z.textContent.trim(); } return null; }"""
# 表示中の範囲（緑のます目）のうち、今のクレーンから maxm 以内で一番離れたます目へ移す（画面の外へ飛ばさない）。ok なます目の中の番号を placeAtCell に渡す
JS_PLACE_FAR = """(maxm)=>{ const m=window.maai, h=window.hud; if(!m||!m.zoneCells||!h||typeof h.placeAtCell!=='function') return null;
  const ok=m.zoneCells.filter(c=>c.ok); if(!ok.length) return null;
  const b=(m.lastCrane&&m.lastCrane.base)||[NaN,NaN]; let best=-1, bd=-1, far=-1, fd=-1;
  ok.forEach((c,i)=>{ const d=Math.hypot(c.x-b[0],c.y-b[1]); if(!(d>=1)) return; if(d>fd){fd=d;far=i;} if(d<=maxm && d>bd){bd=d;best=i;} });   /* v9: 今いるます目（1 m 未満）には動かさない */
  const i = best>=0?best:(far>=0?far:0); const info={i, n:ok.length, x:ok[i].x, y:ok[i].y, d:(best>=0?bd:fd)};
  return Promise.resolve(h.placeAtCell(i)).then(()=>{ info.cls=m.lastCrane&&m.lastCrane.class; return info; }); }"""
# 3D の点（地面の x,y,z）を画面の座標に（page.mouse.click で押すため）
JS_SCREEN_XY = """([x,y,z])=>{ const m=window.maai, v=new m.THREE.Vector3(x,y,z||0).project(m.camera), r=m.renderer.domElement.getBoundingClientRect();
  return [r.left+(v.x+1)/2*r.width, r.top+(1-v.y)/2*r.height]; }"""
# 単線図で取り替える機器（見本 66-D1-CB1 = 6T-110）の .mk に寄せて、押すための CSS セレクタを返す
JS_TARGET_MK = """(id)=>{ let e=document.querySelector('.mk[data-id="'+id+'"]') || document.querySelector('.mk[title^="20E1-110 "]');
  if(!e) return null; e.scrollIntoView({block:'center',inline:'center'}); return '.mk[data-id="'+e.dataset.id+'"]'; }"""
JS_CAM = "()=>{const c=window.maai&&window.maai.controls; return c?[c.target.x,c.target.y,c.radius,c.theta,c.phi].map(v=>+v.toFixed(3)):null;}"
# 結線図で押す開閉器: 停止範囲の「切る機器」のうち最初の断路器（無ければ最初の機器）。.mk に寄せて、押すための CSS セレクタを返す
JS_PICK_MK = """()=>{ const m=window.maai, st=m&&m.lastSteps; let id=null;
  if (st && st.ops && st.ops.length){ const kind=x=>{const n=m.site.topology.nodes.find(y=>y.id===x.id); return n&&n.kind;};
    const o=st.ops.find(x=>kind(x)==='disconnector') || st.ops[0]; id=o.id; }
  let e = id ? document.querySelector('.mk[data-id="'+id+'"]') : null;
  if (!e){ const t=document.querySelector('#stepsBox .sw .id'); if (t) e=document.querySelector('.mk[title^="'+t.textContent+' "]'); }
  if (!e) return null; e.scrollIntoView({block:'center',inline:'center'}); return '.mk[data-id="'+e.dataset.id+'"]'; }"""
JS_REMOVE_OV = "()=>{const o=document.getElementById('__ov'); if(o) o.remove();}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--debug", action="store_true", help="場面ごとに PNG を dbg/ へ")
    ap.add_argument("--chrome", default="/usr/bin/google-chrome", help="付属の Chromium が無いときに使う Chrome")
    a = ap.parse_args()
    out = Path(a.out)
    rec = out / "rec"
    rec.mkdir(parents=True, exist_ok=True)
    for f in glob.glob(str(rec / "*.webm")):
        Path(f).unlink()
    (out / "dbg").mkdir(exist_ok=True)

    from playwright.sync_api import sync_playwright

    segs: list[dict] = []
    PAN_FILES = (("SITE-01_plan.pdf", 4500), ("SITE-01_layout.pdf", 5000), ("SITE-01_sld.pdf", 4500))
    PAN = {n: base64.b64encode(pdf_png(ROOT / "data/sites/SITE-01/drawings" / n, 2.0)).decode() for n, _ in PAN_FILES}   # 録画の前に画像にしておく
    with sync_playwright() as p:
        gl = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
        try:
            browser = p.chromium.launch(args=gl)
        except Exception:   # Playwright 付属の Chromium が無い機械では、入っている Chrome を使う
            browser = p.chromium.launch(executable_path=a.chrome, args=gl)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1,
                                  record_video_dir=str(rec), record_video_size={"width": 1920, "height": 1080})
        # 初回の案内を出さない。内部データ（JSON）は引き出しに入るだけなので出さない。maai-update（結果が変わった合図）を数えて待ちに使う
        ctx.add_init_script("try{localStorage.setItem('maai.onboarded','1');localStorage.setItem('maai.json','0')}catch(e){}"
                            "window.__rec={n:{}}; addEventListener('maai-update', e=>{const k=(e.detail&&e.detail.kind)||'?'; window.__rec.n[k]=(window.__rec.n[k]||0)+1;});")
        t0 = time.monotonic()
        page = ctx.new_page()
        page.on("pageerror", lambda e: print("PAGEERROR", e, file=sys.stderr))

        def el() -> float:
            return time.monotonic() - t0

        ctx.request.post(a.url + "/api/site/SITE-01/layout/use-truth")  # 前の収録で「この 3D で続ける」を押した状態が残っていても、合成データから始める
        page.goto(a.url)
        page.wait_for_function(JS_READY, timeout=120000)
        try:
            page.wait_for_function("()=>!!(window.hud && window.maai)", timeout=15000)
            HUD = True
        except Exception:
            HUD = False
            print("HUD（web/hud.js）が無い。旧画面の手順で録る（引き出しの開閉と 3D 上の見せ場は飛ばす）", file=sys.stderr)
        page.wait_for_timeout(1500)

        # ---- 小さな手順（HUD が無ければ何もしないものは、そう書いてある）
        marks: list[dict] = []   # v9: 押した所と時刻（compose9 の C5〜C8 が録画のどこを使うか・どこに波紋を出すかを、これから決める）

        def click(sel: str):
            xy = page.evaluate("s=>{const e=document.querySelector(s); if(!e) return null; const r=e.getBoundingClientRect(); return [Math.round(r.left+r.width/2), Math.round(r.top+r.height/2)];}", sel)
            marks.append({"name": "click " + sel, "t": round(el(), 2), "xy": xy})
            page.evaluate(JS_CLICK, sel)

        def mclick(xy, name: str):
            marks.append({"name": "mouse " + name, "t": round(el(), 2), "xy": [round(xy[0]), round(xy[1])]})
            page.mouse.click(xy[0], xy[1])

        def tab(s: str):
            click(f'#prog [data-goto="{s}"]')   # #prog は隠れているが DOM にあり、押すと window.go が動く

        def smooth(sel: str, block: str = "start"):
            page.evaluate(JS_SCROLL, [sel, block])

        def scroll_text(container: str, words: list[str], block: str = "center") -> bool:
            return bool(page.evaluate(JS_SCROLL_TEXT, [container, words, block]))

        def wait_in(sel: str, timeout: int):
            """引き出しの中（閉じていると visible にならない）の要素を、DOM に付くまで待つ。"""
            # ページ内で querySelector を 250 ms ごとに見る（描き直しの多い画面では wait_for_selector が要素を掴み損ねることがある）
            page.wait_for_function("s=>!!document.querySelector(s)", arg=sel, polling=300, timeout=timeout)

        def hud(name: str, *args) -> bool:
            """window.hud の関数を呼ぶ（Promise なら終わるまで待つ）。無ければ False。"""
            return bool(page.evaluate(JS_HUD, [name, list(args)]))

        def drawer(open_: bool, settle: int = 400):
            """左の引き出し（元の左パネル）を開く・閉じる。HUD が無ければ何もしない（左パネルは常に見えている）。"""
            if not HUD:
                return
            hud("openDrawer" if open_ else "closeDrawer")
            page.wait_for_timeout(settle)

        def sld_full(on: bool):
            """結線図を全面にする（on）／小窓に戻して 3D を見せる。HUD が無ければ #btnViewToggle で結線図⇄3D。"""
            if HUD:
                hud("expandSld", on)
                return
            is_on = page.evaluate("()=>document.getElementById('sldView').classList.contains('on')")
            if bool(is_on) != on:
                click("#btnViewToggle")

        def set_mode(name: str):
            """結線図の押し方（toggle=開閉器を入・切、target=取り替える機器に選ぶ）。ラジオに書き、HUD があれば setMode にも伝える。"""
            page.evaluate("v=>{const r=document.querySelector('input[name=sldMode][value='+v+']'); if(r) r.checked=true; if(window.hud&&window.hud.setMode) window.hud.setMode(v);}", name)

        def mark(kind: str) -> int:
            return int(page.evaluate(JS_MARK, kind))

        def wait_update(kind: str, n0: int, timeout: int = 30000, fallback: int = 2500):
            """kind の maai-update が n0 より増えるまで待つ（判定し直しの終わり）。合図の無い旧画面では fallback ミリ秒だけ待つ。"""
            if not HUD:
                page.wait_for_timeout(fallback)
                return
            try:
                page.wait_for_function(JS_WAIT_MARK, arg=[kind, n0], polling=300, timeout=timeout)
            except Exception:
                print(f"maai-update '{kind}' が来ない（{timeout} ms）。そのまま進む", file=sys.stderr)

        def settle_cam(max_ms: int = 12000):
            """視点の移動（frameTo。ソフトウェア描画では 20 コマに 10 秒ほどかかる）が止まるまで待つ。HUD が無ければ 1.2 秒。"""
            if not HUD:
                page.wait_for_timeout(1200)
                return
            t = time.monotonic()
            prev = page.evaluate(JS_CAM)
            while (time.monotonic() - t) * 1000 < max_ms:
                page.wait_for_timeout(350)
                cur = page.evaluate(JS_CAM)
                if cur == prev:
                    return
                prev = cur

        def toggle_mk(sel: str):
            """結線図の開閉器を押し、描き直した結線図でその開閉器の入・切が変わるまで待つ（判定と描き直しに数秒かかる）。"""
            before = page.evaluate("s=>{const e=document.querySelector(s); return e?e.title:null}", sel)
            click(sel)
            try:
                page.wait_for_function("([s,t])=>{const e=document.querySelector(s); return !!e && e.title!==t}", arg=[sel, before], polling=300, timeout=20000)
            except Exception:
                print("結線図の描き直しが来ない:", sel, file=sys.stderr)

        def zone_tile(k: int) -> str | None:
            """下のバーの k 番目の級のタイルを押して、据えてよい範囲を切り替える。"""
            return page.evaluate(JS_ZONE_TILE, k)

        def place_far_cell(max_m: float = 24.0):
            """緑のます目へクレーンを移して判定し直す（window.hud.placeAtCell）。HUD が無ければ None。"""
            if not HUD:
                return None
            return page.evaluate(JS_PLACE_FAR, max_m)   # 選び直しと判定が終わるまで待つ

        def rotate(deg: float, hold: int):
            """クレーンを deg 度回して判定し直し（window.hud.rotate）、hold ミリ秒止める。HUD が無ければ何もしない。"""
            if not HUD:
                return
            hud("rotate", deg)                          # s2 では向きを変えて級も選び直す。終わるまで待つ
            page.wait_for_timeout(hold)

        def pan(pdf: Path, hold: int):
            """図面 1 枚を画面いっぱいに出し、ゆっくり寄せる（CSS の変形。録画が低いコマ数でも滑らかに見える）。"""
            b64 = PAN[pdf.name]
            page.evaluate("""([b,ms])=>{const o=document.getElementById('__ov'); if(o) o.remove(); const d=document.createElement('div'); d.id='__ov';
              d.style.cssText='position:fixed;inset:0;z-index:99999;background:#fff;overflow:hidden';
              d.innerHTML='<img id="__pan" style="position:absolute;left:0;top:0;width:1920px;height:1080px;object-fit:contain;transform-origin:50% 45%;transform:scale(1);transition:transform '+ms+'ms linear" src="data:image/png;base64,'+b+'">';
              document.body.appendChild(d); requestAnimationFrame(()=>requestAnimationFrame(()=>{document.getElementById('__pan').style.transform='scale(1.35)';}));}""", [b64, hold])
            page.wait_for_timeout(hold)

        RECTS = ["#hudAnswer", "#hudBar", "#hudCard", "#hudSide", "#hudGoals", "#hudNext", "#hudDrawer", "#sldView", "#intakeBox", "#stepsBox",
                 "#selectBox", "#verdictBox", "#approveBox", "#__ov", '.mk[data-id="220-L1-CB"]', "#sldPane", "#planPane", "#hudSteps"]

        def shot(name: str):
            """その時の画面の要素の位置（録画 1920x1080 の画素）も残す。compose9 の枠・札の位置に使う。"""
            r = page.evaluate("ss=>Object.fromEntries(ss.map(s=>{const e=document.querySelector(s); if(!e) return [s,null]; const b=e.getBoundingClientRect();"
                              " return [s, (b.width>0&&b.height>0&&b.bottom>0&&b.right>0)?[Math.round(b.left),Math.round(b.top),Math.round(b.right),Math.round(b.bottom)]:null];}))", RECTS)
            marks.append({"name": name, "t": round(el(), 2), "rects": {k: v for k, v in r.items() if v}})
            if a.debug:
                page.screenshot(path=str(out / "dbg" / f"{name}.png"))

        def run(sid: str):
            if sid == "s1":
                # 図面（一般平面図 → 機械器具装置図〈平面・断面〉→ 単線結線図）をゆっくり寄せて見せる
                for name, hold in PAN_FILES:
                    pan(ROOT / "data/sites/SITE-01/drawings" / name, hold)
                page.evaluate(JS_REMOVE_OV)
            elif sid == "c5":
                tab("s0")
                page.set_input_files("#ingestFile", str(ROOT / "data/sites/SITE-01/drawings/SITE-01_sld.pdf"))
                page.wait_for_timeout(800)
                click("#btnIngest")
                wait_in("#btnConfirmAll", 240000)   # Claude の意味づけを待つ（待ちの静止は compose が縮める）
                page.wait_for_timeout(2500)          # 3D の上の板: 読めた番号 n / m、確かめてほしいこと k
                shot("s2_answer")
                drawer(True)                         # 根拠は引き出し: 人に確かめてほしいことの一覧
                page.evaluate("()=>{const h=[...document.querySelectorAll('#ingestBox h4')].find(x=>x.textContent.includes('確かめてほしい')); if(h) h.scrollIntoView({behavior:'instant',block:'start'});}")
                shot("s2_questions")
                page.wait_for_timeout(4500)
                smooth("#btnConfirmAll", "center")
                page.wait_for_timeout(1500)
                click("#btnConfirmAll")
                page.wait_for_timeout(2000)
                click("#btnLayoutSample")             # 装置図（平面・断面）→ 3D の下書き。小さい 3D と精度の表は引き出しの中（開いたまま。閉じると小さい 3D が描かれない）
                wait_in("#miniR canvas", 90000)
                page.wait_for_timeout(2000)
                smooth("#miniL", "start")
                page.wait_for_timeout(3000)
                page.evaluate("()=>{const t=document.querySelector('#layoutBox table'); if(t) t.scrollIntoView({behavior:'instant',block:'center'});}")
                page.wait_for_timeout(2500)
                page.wait_for_function("()=>{const b=document.querySelector('#btnUseDraft'); return b && !b.disabled}", timeout=30000)
                smooth("#btnUseDraft", "center")
                page.wait_for_timeout(1200)
                click("#btnUseDraft")  # 「この 3D で続ける」（要確認があるときは「要確認 n 件を確認のうえ続ける」）
                page.wait_for_function("()=>{const m=window.maai; if (m&&m.site) return m.site.layout_source==='drawing-draft'; const b=document.getElementById('srcBadge'); return !!b && b.textContent.includes('図面から起こした配置');}",
                                       polling=250, timeout=30000)   # #hud（バッジ）は画面外なので、読み込んだ配置の元で見る
                drawer(False)                        # 図面から起こした配置の 3D を全面で見せる
                page.wait_for_timeout(2500)
            elif sid == "c6":
                tab("s1")                            # 単線図が全面に出る
                page.wait_for_timeout(1200)
                if not page.evaluate("()=>{const b=document.querySelector('#hudSide [data-act=\"intake\"]'); if(b){b.click(); return true;} return false;}"):
                    drawer(True)                     # 「依頼文から入れる」→ 引き出しの依頼文の欄
                page.wait_for_timeout(500)
                page.evaluate("(t)=>{const e=document.getElementById('reqText'); e.value=t;}", REQ_TEXT)
                smooth("#reqText", "start")
                page.wait_for_timeout(2500)
                click("#btnIntake")
                wait_in("#intakeBox .bay", 120000)   # Claude の返事を待つ（オフラインでは規則の読み取り。待ちの静止は compose が縮める）
                page.wait_for_timeout(1000)
                shot("s2b_intake")
                smooth("#intakeBox", "start")        # 読み取った 4 項目と引用、計算で確かめた結果、「この内容で入れる」
                page.wait_for_timeout(4000)
                click("#btnIntakeUse")
                wait_in("#stepsBox .bay", 30000)
                page.wait_for_timeout(800)
                drawer(False)                        # 単線図と平面図の上: 停止範囲の答え（切る開閉器 3・相手端の条件）
                page.wait_for_timeout(3000)
                shot("c6_steps")
                # Claude に送る前の置き換え（実際の送信記録）
                page.evaluate("(h)=>{const d=document.createElement('div'); d.innerHTML=h; document.body.appendChild(d.firstElementChild);}", mask_demo_html())
                shot("c6_mask")
                # 置き換えた語の位置（録画の画素）: compose9 が「手元の文」の語を赤、「送る文」の語を緑で囲む
                words = page.evaluate("""(ws)=>{const ov=document.getElementById('__ov'); const out={}; if(!ov) return out;
                  const boxes=[...ov.children].filter(e=>e.tagName==='DIV' && e.querySelector('span'));
                  boxes.forEach((bx,bi)=>{ const walker=document.createTreeWalker(bx, NodeFilter.SHOW_TEXT); let n;
                    while((n=walker.nextNode())){ for(const w of ws){ const i=n.textContent.indexOf(w); if(i<0) continue; const k=(bi===0?'before:':'after:')+w; if(out[k]) continue;
                      const r=document.createRange(); r.setStart(n,i); r.setEnd(n,i+w.length); const b=r.getBoundingClientRect();
                      out[k]=[Math.round(b.left),Math.round(b.top),Math.round(b.right),Math.round(b.bottom)]; } } });
                  return out;}""", ["東線1L", "LINE-1", "2000A", "RATING-1", "合成変電所", "SITE-1"])
                marks.append({"name": "c6_mask_words", "t": round(el(), 2), "words": words})
                page.wait_for_timeout(4000)
                page.evaluate(JS_REMOVE_OV)
                page.wait_for_timeout(800)
                # 単線図の上で、取り替える遮断器のまわり（緑の区間）に寄る
                page.evaluate("()=>{const b=document.querySelector('#sldZoom button[data-z=\"2.6\"]'); if(b) b.click();}")
                page.wait_for_timeout(1200)
                page.evaluate(JS_TARGET_MK, "220-L1-CB")
                page.wait_for_timeout(3500)
                shot("c6_green")
            elif sid == "s3":
                tab("s1")                            # 単線図は全面、押すと「取り替える機器に選ぶ」
                page.wait_for_timeout(1200)
                page.evaluate("()=>{const b=document.querySelector('#sldZoom button[data-z=\"2.6\"]'); if(b) b.click();}")
                page.wait_for_timeout(1500)
                tgt = page.evaluate(JS_TARGET_MK, "66-D1-CB1")
                if tgt:
                    page.wait_for_timeout(1500)
                    n0 = mark("steps")
                    click(tgt)                       # 取り替える機器を押す → 停止範囲が自動で出る
                    wait_update("steps", n0)
                    page.wait_for_timeout(3000)
                    shot("s3_green")
                else:
                    print("単線図に取り替える機器が見つからない", file=sys.stderr)
                set_mode("toggle")                   # 全面の単線図の上の小さな切替（W）: 押すと開閉器の入・切
                mk = page.evaluate(JS_PICK_MK)       # 切る機器のうち母線側の断路器（入れると対象の区間が赤になる）。Playwright の locator は 1 回 15 秒ほどかかるので使わない
                if mk:
                    page.wait_for_timeout(1200)
                    toggle_mk(mk)                    # 入れる → 赤
                    page.wait_for_timeout(2000)
                    shot("s3_red")
                    toggle_mk(mk)                    # 切り直す → 緑に戻る
                    page.wait_for_timeout(1500)
                else:
                    print("結線図に押す開閉器が見つからない", file=sys.stderr)
                set_mode("target")
                sld_full(False)                      # 3D へ（取り替える機器に寄る）: 見えなかった充電部（赤）と停電（緑）
                settle_cam(20000)                    # 寄る動き（frameTo）が終わってから次の段へ（残っていると s2 の真上の視点を上書きする）
                page.wait_for_timeout(1500)
            elif sid == "c7":
                for _ in range(2):                   # 真上の視点（段に入ると hud-s2 が動かす。前の段の寄る動きに上書きされたら入り直す）
                    tab("s2")
                    try:
                        page.wait_for_function("()=>window.maai.controls.phi>1.4", polling=300, timeout=10000)
                        break
                    except Exception:
                        print("真上の視点にならない。入り直す", file=sys.stderr)
                page.wait_for_timeout(1000)
                page.evaluate("()=>{const t=document.getElementById('pickT'); if(t) t.value=''; window.hud&&window.hud.render();}")   # 重さは画面で入れる（例示値の既定を空けて、入れる順を見せる）
                page.wait_for_timeout(1200)
                shot("s4_top")
                xy = page.evaluate(JS_SCREEN_XY, [26, 108, 0])   # 資材置場: 取り替える遮断器（32, 108）の西 6 m の地面を押す → 箱
                mclick(xy, "laydown")
                page.wait_for_timeout(2500)
                shot("s4_box")
                n0 = mark("clearance")
                page.evaluate("()=>{const i=document.getElementById('s2W'); if(i){ i.value='10'; i.dispatchEvent(new Event('input',{bubbles:true})); } else { const t=document.getElementById('pickT'); t.value='10'; t.dispatchEvent(new Event('input',{bubbles:true})); t.dispatchEvent(new Event('change',{bubbles:true})); } }")
                wait_update("clearance", n0, timeout=120000)   # 重さが入ると自動で選定 → 自動で採用 → 判定（人は押さない）
                settle_cam(6000)
                page.wait_for_timeout(3500)          # 答えの板: 35t 級で置ける（可）、最小離隔／必要
                shot("s4_verdict")
                base = page.evaluate("()=>{const c=window.maai.lastCrane; return c?[c.base[0],c.base[1],2]:null}")
                if base:                             # クレーンを押す → 「動かす」「↺/↻ 5°」のカード
                    xy = page.evaluate(JS_SCREEN_XY, base)
                    mclick(xy, "crane")
                    page.wait_for_timeout(2000)
                    shot("s4_card")
                # 見せ場: 一つ上（50t）の範囲を塗る → 緑のます目へ動かすと、その位置で級を選び直す → 回しても選び直す
                if zone_tile(1):
                    page.wait_for_timeout(2500)
                    shot("s4_tile")
                moved = place_far_cell()
                print("動かした:", moved, file=sys.stderr)
                if moved:
                    page.wait_for_timeout(3000)
                    shot("s4_moved")
                for _ in range(2):                   # 1 回の選び直しに数秒かかるので 2 回
                    rotate(5, 1600)
                shot("s4_rotated")
                n0 = mark("clearance")               # 「一番小さいクレーンを選ぶ」のタイル → 自動で採用し、35t 級の配置に戻る
                if page.evaluate("()=>{const b=document.querySelector('#hudBar .tile[data-act=\"select\"]'); if(b){b.click(); return true;} return false;}"):
                    wait_update("clearance", n0, timeout=120000)
                    settle_cam(6000)
                page.wait_for_timeout(2000)
                shot("s4_back")
                drawer(True)                         # 根拠は引き出し: 重さだけなら 10t・離隔で 35t、一つ下が使えない理由、止められない設備（依頼文）
                smooth("#selectBox", "start")
                page.wait_for_timeout(1200)
                shot("c7_reason")                    # 重さだけなら 25t 級・一つ下が使えない理由
                page.wait_for_timeout(1800)
                scroll_text("#selectBox .bay", ["止められない設備", "追加で止めた場合"], "center")
                page.wait_for_timeout(1000)
                shot("c7_unstoppable")               # 依頼文で止められない設備 → 止める案は出さない
                page.wait_for_timeout(2500)
            elif sid == "c8":
                # 根拠: 導体ごとの距離・必要・余裕の表（引き出し。s4 の終わりから開いたまま）
                drawer(True)
                page.evaluate("()=>{const b=document.getElementById('manualBox'); if(b) b.open=true;}")
                smooth("#verdictBox", "start")
                page.wait_for_timeout(3000)
                shot("s5_evidence")
                drawer(False)
                tab("s3")                            # 答えの板: 対象・切る開閉器・クレーン級・離隔と条件
                page.wait_for_timeout(2000)
                click("#hudNext")                    # 「この配置で OK（承認）」（= #btnApprove）
                wait_in("#approveBox .bay", 60000)
                page.wait_for_timeout(3000)          # 承認済みと、ステップ図のタイル（停止範囲の単線図・クレーン配置の平面図）
                shot("s5_approved")

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

                shot("c8_pdf_sld")
                overlay("step-1-sld.pdf", 4000)
                shot("c8_pdf_crane")
                overlay("plan-crane.pdf", 4500)
                page.evaluate(JS_REMOVE_OV)
                page.wait_for_timeout(2500)          # 承認済みの画面（ステップ図のタイル）に戻る
                shot("c8_tiles")

        try:
            for sid, scr, dur, text in LINES:
                s = el()
                run(sid)
                shot(sid + "_end")
                rest = s + dur - el()
                if rest > 0:
                    page.wait_for_timeout(int(rest * 1000))
                segs.append({"id": sid, "script": scr, "start": round(s, 2), "end": round(el(), 2), "target_sec": dur, "text": text})
                print(sid, segs[-1]["start"], segs[-1]["end"], "(台本", dur, "秒)", flush=True)
        finally:
            ctx.request.post(a.url + "/api/site/SITE-01/layout/use-truth")   # 「この 3D で続ける」はサーバに残るので、途中で落ちても合成データに戻す
        ctx.close()
        browser.close()

    vids = sorted(glob.glob(str(rec / "*.webm")))
    if len(vids) != 1:
        print("録画が1本でない:", vids, file=sys.stderr)
        return 1
    (out / "segments.json").write_text(json.dumps({"video": vids[0], "segments": segs, "marks": marks}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("録画:", vids[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
