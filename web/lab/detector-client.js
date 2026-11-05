// MAAI ラボ（実験・本線に入れない）: 画面側から端末内の検出器を使う部品（モデルの保存、ワーカーとのやりとり、画像の縮小）。
// モデル（AGPL-3.0）はリポジトリに置かない。利用者が端末に落としたファイルを選び、このブラウザの IndexedDB にだけ残す。
import { INPUT } from './detector.js';

const DB = 'maai-lab', STORE = 'models', KEY = 'yoloworld';
function openDb() {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1);
    r.onupgradeneeded = () => r.result.createObjectStore(STORE);
    r.onsuccess = () => resolve(r.result); r.onerror = () => reject(r.error);
  });
}
async function withStore(mode, fn) {
  const db = await openDb();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode), req = fn(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(req && req.result); tx.onerror = () => reject(tx.error); tx.onabort = () => reject(tx.error);
    });
  } finally { db.close(); }
}
export const saveModel = (name, buf) => withStore('readwrite', s => s.put({ name, size: buf.byteLength, savedAt: Date.now(), buf }, KEY));
export const loadModel = () => withStore('readonly', s => s.get(KEY)).catch(() => null);
export const deleteModel = () => withStore('readwrite', s => s.delete(KEY));

// 画像（img / canvas / video / ImageBitmap）を長辺 max 以下に縮め、左上原点の RGBA にする
export function imageToRgba(src, sw, sh, max = INPUT) {
  const k = Math.min(1, max / Math.max(sw, sh)), W = Math.max(1, Math.round(sw * k)), H = Math.max(1, Math.round(sh * k));
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d', { willReadFrequently: true }); g.imageSmoothingEnabled = true; g.imageSmoothingQuality = 'medium';
  g.drawImage(src, 0, 0, W, H);
  const d = g.getImageData(0, 0, W, H);
  return { rgba: new Uint8Array(d.data.buffer), W, H, scale: sw / W };
}

// ワーカー（detector-worker.js）とのやりとり
export class Detector {
  constructor() { this.worker = null; this.info = null; this.pending = new Map(); this.seq = 1; this.inflight = 0; }
  get ready() { return !!this.info; }
  close() {
    if (this.worker) this.worker.terminate();
    for (const p of this.pending.values()) p.reject(new Error('検出器を止めた'));
    this.worker = null; this.info = null; this.pending.clear(); this.inflight = 0;
  }
  // model は ArrayBuffer（ワーカーへ移すので、呼んだ側では使えなくなる）。prefer: 'webgpu'（既定）か 'wasm'
  init(model, prefer = 'webgpu') {
    this.close();
    const w = new Worker(new URL('./detector-worker.js', import.meta.url), { type: 'module' });
    this.worker = w;
    return new Promise((resolve, reject) => {
      w.onerror = ev => { ev.preventDefault?.(); reject(new Error('ワーカーを読み込めない: ' + (ev.message || 'ネットワークか構文の誤り'))); };
      w.onmessage = ev => {
        const m = ev.data;
        if (m.type === 'ready') { this.info = m; resolve(m); }
        else if (m.type === 'error' && m.stage === 'init') reject(new Error(m.message));
        else if (m.type === 'dets' || m.type === 'error') {
          const p = this.pending.get(m.id); if (!p) return;
          this.pending.delete(m.id); this.inflight--;
          m.type === 'dets' ? p.resolve(m) : p.reject(new Error(m.message));
        }
      };
      w.postMessage({ type: 'init', model, prefer }, [model]);
    });
  }
  // rgba は Uint8Array（長さ W*H*4 ちょうど。ワーカーへ移す）。戻り値 {boxes, ms, W, H}
  detect(rgba, W, H, conf = 0.25) {
    if (!this.info) return Promise.reject(new Error('検出器の準備ができていない'));
    if (rgba.byteOffset !== 0 || rgba.buffer.byteLength !== W * H * 4) rgba = rgba.slice();
    const id = this.seq++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject }); this.inflight++;
      this.worker.postMessage({ type: 'detect', id, rgba: rgba.buffer, W, H, conf }, [rgba.buffer]);
    });
  }
}
