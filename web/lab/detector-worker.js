// MAAI ラボ（実験・本線に入れない）: 端末内で検出器（YOLO-World の ONNX）を動かすワーカー。画像はこの端末の外に出さない。
// 実行部品 onnxruntime-web は jsDelivr から取り、ハッシュ（SRI）で照合できたものだけを使う。照合できなければ動かさない。
// ハッシュは GitHub Actions（lab-yoloworld-export の ort job）が npm の配布物から計算して記録したもの。
// ワーカーの中で動かすので、画面側のキー（sessionStorage）や DOM には触れられない。
import { INPUT, toTensorData, decode } from './detector.js';

const ORT = {
  version: '1.20.1',
  base: 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/',
  code: { file: 'ort.webgpu.bundle.min.mjs', integrity: 'sha384-dInEXRrvRYzqfWyU/mKWamdE46OMNPRwpAWIsyL3DMs9cy2uD5fHLKnsEDYbzaDf' },
  wasm: { file: 'ort-wasm-simd-threaded.jsep.wasm', integrity: 'sha384-HPJ3YfucD9OlwN1TI/3IKakCsWeFCwPQPmbi7TtPkJyZujXCF3TPid7iNbXPz3zU' },
};
let ort = null, session = null, info = null;

async function fetchVerified(f, as) {
  let res;
  try { res = await fetch(ORT.base + f.file, { integrity: f.integrity, mode: 'cors', credentials: 'omit', cache: 'force-cache' }); }
  catch (e) { throw new Error(`${f.file} を取得できないか、ハッシュが合わない（${e && e.message || e}）`); }
  if (!res.ok) throw new Error(`${f.file} を取得できない（HTTP ${res.status}）`);
  return as === 'text' ? res.text() : res.arrayBuffer();
}
async function loadOrt() {
  if (ort) return ort;
  const [code, wasm] = await Promise.all([fetchVerified(ORT.code, 'text'), fetchVerified(ORT.wasm, 'buffer')]);
  const mod = await import(URL.createObjectURL(new Blob([code], { type: 'text/javascript' })));
  mod.env.wasm.wasmBinary = wasm;   // 照合済みの wasm を渡す（パスからは取りに行かせない）
  mod.env.wasm.numThreads = 1;      // Pages は cross-origin isolation が無く、複数スレッドは使えない
  mod.env.wasm.proxy = false;
  mod.env.logLevel = 'error';
  ort = mod;
  return ort;
}
const feed = data => ({ [info.inputName]: new ort.Tensor('float32', data, [1, 3, INPUT, INPUT]) });
async function warm(s, inputName, outputName) {
  const L = toTensorData(new Uint8Array(4 * 64 * 64).fill(128), 64, 64, INPUT), t0 = performance.now();
  const out = await s.run({ [inputName]: new ort.Tensor('float32', L.data, [1, 3, INPUT, INPUT]) });
  const dims = Array.from(out[outputName].dims);
  return { dims, ms: performance.now() - t0 };
}
async function init(modelBuf, prefer) {
  await loadOrt();
  const model = new Uint8Array(modelBuf);
  let ep = '', gpuError = '', w = null;
  if (prefer !== 'wasm' && self.navigator && self.navigator.gpu) {
    try {
      session = await ort.InferenceSession.create(model, { executionProviders: ['webgpu'] });
      w = await warm(session, session.inputNames[0], session.outputNames[0]); ep = 'WebGPU';
    } catch (e) { gpuError = String(e && e.message || e).slice(0, 200); try { await session?.release(); } catch (e2) { /* 無視 */ } session = null; }
  } else gpuError = prefer === 'wasm' ? 'WASM を指定' : 'この環境に WebGPU がない';
  if (!session) {
    session = await ort.InferenceSession.create(model, { executionProviders: ['wasm'] });
    w = await warm(session, session.inputNames[0], session.outputNames[0]); ep = 'WASM';
  }
  const dims = w.dims, nc = (dims[1] < dims[2] ? dims[1] : dims[2]) - 4;
  info = { ep, gpuError, inputName: session.inputNames[0], outputName: session.outputNames[0], dims, nc, warmMs: Math.round(w.ms), ort: ORT.version };
  return info;
}
async function detect({ rgba, W, H, conf }) {
  const L = toTensorData(new Uint8Array(rgba), W, H, INPUT), t0 = performance.now();
  const out = await session.run(feed(L.data));
  const ms = performance.now() - t0, o = out[info.outputName];
  const boxes = decode(o.data, o.dims, info.nc, L, conf ?? 0.25, 0.5, W, H);
  return { boxes, ms: Math.round(ms) };
}

// 1件ずつ順に処理する（同じセッションを同時に走らせない）
let chain = Promise.resolve();
self.onmessage = ev => {
  const m = ev.data;
  chain = chain.then(async () => {
    try {
      if (m.type === 'init') self.postMessage({ type: 'ready', ...(await init(m.model, m.prefer)) });
      else if (m.type === 'detect') {
        if (!session) throw new Error('モデルが読み込まれていない');
        self.postMessage({ type: 'dets', id: m.id, W: m.W, H: m.H, ...(await detect(m)) });
      }
    } catch (e) { self.postMessage({ type: 'error', id: m.id, stage: m.type, message: String(e && e.message || e).slice(0, 300) }); }
  });
};
