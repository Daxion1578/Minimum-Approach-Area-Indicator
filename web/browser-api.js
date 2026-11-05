// ブラウザ版: サーバ無しで、画面の fetch('/api/...') をブラウザの中の Python（Pyodide）に回す。
// 判定はサーバ版と同じコード（server/browser.py → server/app.py → engine/）。Claude は呼ばない。
// 有効になるのは、公開用に組んだページ（data-mode="browser"）か、URL に ?browser を付けたときだけ。
(() => {
  const me = document.currentScript;
  const on = me.dataset.mode === 'browser' || new URLSearchParams(location.search).has('browser');
  if (!on) return;
  window.MAAI_BROWSER = true;
  const base = new URL('.', me.src).href;              // .../web/
  const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v314.0.7/full/';
  // 版を固定する（作った日に動いた組み合わせ）
  const WHEELS = ['pdfminer.six==20260107', 'reportlab==5.1.0', 'fastapi==0.162.0', 'starlette==1.10.0',
                  'python-multipart==0.0.33', 'python-dotenv==1.2.4', 'jsonschema'];

  // ---- 上の帯（準備中の表示）
  const bar = document.createElement('div');
  bar.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:9999;padding:6px 12px;font:13px system-ui,sans-serif;' +
                      'background:#1d2a3a;color:#e8eef5;border-bottom:1px solid #3a5070;text-align:center';
  const say = (t) => { bar.textContent = t; };
  say('ブラウザ版を準備しています（初回は 10〜20 秒。計算はすべてこのブラウザの中で行い、どこにも送りません）');
  const mount = () => document.body.prepend(bar);
  document.body ? mount() : document.addEventListener('DOMContentLoaded', mount);

  const realFetch = window.fetch.bind(window);
  let py = null;

  async function boot() {
    const s = document.createElement('script');
    s.src = PYODIDE + 'pyodide.js';
    await new Promise((ok, ng) => { s.onload = ok; s.onerror = () => ng(new Error('Pyodide を読み込めない')); document.head.append(s); });
    py = await loadPyodide({ indexURL: PYODIDE });
    say('ブラウザ版: 部品を読み込んでいます…');
    await py.loadPackage(['micropip', 'pydantic', 'Pillow']);
    const zip = await (await realFetch(base + 'py.zip')).arrayBuffer();
    py.unpackArchive(zip, 'zip', { extractDir: '/repo' });
    await py.runPythonAsync(`
import micropip, sys, os, types
await micropip.install(${JSON.stringify(WHEELS)})
await micropip.install("pdfplumber==0.11.10", deps=False)
# ブラウザで動かない部品の代わり（暗号化 PDF の復号と、ページの画像化。どちらも判定には使わない）
def _stub(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m
def _no(*a, **k): raise RuntimeError("暗号化された PDF はブラウザ版では読めない")
_stub("cryptography.hazmat.backends", default_backend=_no)
_stub("cryptography.hazmat.primitives.ciphers", Cipher=_no, algorithms=types.SimpleNamespace(AES=_no), modes=types.SimpleNamespace(CBC=_no, ECB=_no))
_stub("pypdfium2")
sys.path.insert(0, "/repo"); os.chdir("/repo"); os.makedirs("/repo/web", exist_ok=True)
import json
from server import browser
async def _maai_call(method, path, body, has_pdf):
    pdf = open("/tmp/upload.pdf", "rb").read() if has_pdf else None
    return json.dumps(await browser.handle(method, path, body, pdf))
`);
    say('ブラウザ版（サーバ無し・Claude 無し。判定はサーバ版と同じコード）');
    setTimeout(() => { bar.style.display = 'none'; }, 4000);
    return py.globals.get('_maai_call');
  }
  const ready = boot().catch((e) => { say('ブラウザ版の準備に失敗: ' + e.message); throw e; });

  const MIME = { pdf: 'application/pdf', json: 'application/json' };
  async function api(method, url, body, file) {
    const call = await ready;
    if (file) py.FS.writeFile('/tmp/upload.pdf', new Uint8Array(await file.arrayBuffer()));
    const r = JSON.parse(await call(method, url, body ?? null, !!file));
    if (r.file) {
      const bytes = py.FS.readFile(r.file);
      return new Response(new Blob([bytes], { type: MIME[r.file.split('.').pop()] || 'application/octet-stream' }), { status: 200 });
    }
    return new Response(r.json, { status: r.status, headers: { 'content-type': 'application/json' } });
  }

  window.fetch = async (input, init = {}) => {
    // Pyodide 自身も fetch で部品を取りに行く（URL オブジェクトや Request で来る）。/api/ だけを受ける
    const u = new URL(input instanceof Request ? input.url : String(input), location.href);
    if (u.origin !== location.origin || !u.pathname.startsWith('/api/')) return realFetch(input, init);
    const url = u.pathname + u.search;
    const method = (init.method || 'GET').toUpperCase();
    const file = init.body instanceof FormData ? init.body.get('file') : null;
    return api(method, url, typeof init.body === 'string' ? init.body : null, file);
  };

  // 書き出した PDF / JSON へのリンク（<a href="/api/...">）もブラウザの中から開く
  document.addEventListener('click', async (ev) => {
    const a = ev.target.closest && ev.target.closest('a[href^="/api/"]');
    if (!a) return;
    ev.preventDefault();
    const w = window.open('', '_blank');
    const r = await window.fetch(a.getAttribute('href'));
    const url = URL.createObjectURL(await r.blob());
    if (w) w.location = url; else location.href = url;
  }, true);

  // 取込タブ: 手元に図面が無くても試せるように、合成変電所の図面を選ぶボタン
  document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('ingestFile');
    if (!input) return;
    const b = document.createElement('button');
    b.className = 'sub'; b.textContent = 'サンプル図面で試す';
    b.title = '合成変電所の単線結線図（SITE-01_sld.pdf）を取り込む';
    b.onclick = async () => {
      const blob = await (await realFetch(base + 'sample/SITE-01_sld.pdf')).blob();
      const dt = new DataTransfer();
      dt.items.add(new File([blob], 'SITE-01_sld.pdf', { type: 'application/pdf' }));
      input.files = dt.files;
      document.getElementById('btnIngest').click();
    };
    const link = document.createElement('a');
    link.href = base + 'sample/SITE-01_sld.pdf'; link.target = '_blank'; link.textContent = '図面を見る';
    link.style.cssText = 'color:var(--accent);margin-left:6px;font-size:12px';
    input.after(b, link);
  });
})();
