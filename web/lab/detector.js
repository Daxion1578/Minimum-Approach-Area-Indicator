// MAAI ラボ（実験・本線に入れない）: 端末内の検出器の前処理・後処理と、検出の追跡・多視点の3D化。
// 純粋な計算だけを置く（画面・ワーカー・Node のテストから同じものを使う）。画像は端末の外に出さない。
// 座標の約束: 画像は左上原点の画素。3D は WebXR の local 空間（m、+Y が上）。行列は WebXR と同じ列優先の長さ16の配列。

export const INPUT = 640;

// 探す語。lab/yoloworld/classes.txt と同じ順（テストで照合する）。
// role: live = 充電部になりうる（離隔帯を出す。既定は充電中） / approach = 近づく物（離隔帯までの距離を出す） / other = その他
export const CLASSES = [
  { en: 'insulator', ja: 'がいし', role: 'live' },
  { en: 'bushing', ja: 'ブッシング', role: 'live' },
  { en: 'overhead power line', ja: '架空線', role: 'live' },
  { en: 'disconnect switch', ja: '断路器', role: 'live' },
  { en: 'circuit breaker', ja: '遮断器', role: 'live' },
  { en: 'transformer', ja: '変圧器', role: 'live' },
  { en: 'lattice steel tower', ja: '鉄塔・鉄構', role: 'other' },
  { en: 'mobile crane', ja: '移動式クレーン', role: 'approach' },
  { en: 'crane boom', ja: 'クレーンのブーム', role: 'approach' },
  { en: 'aerial work platform', ja: '高所作業車', role: 'approach' },
  { en: 'person', ja: '人', role: 'approach' },
];
export const classInfo = cls => CLASSES[cls] || { en: `class ${cls}`, ja: `種類${cls}`, role: 'other' };

// ------------------------------------------------------------ 前処理・後処理（YOLO 系、入力 640×640）
// RGBA（左上原点、W×H、長辺 S 以下）を S×S の中央に置き、[1,3,S,S] の 0〜1 にする（余白は灰色 114）
export function toTensorData(rgba, W, H, S = INPUT) {
  if (W > S || H > S) throw new Error(`画像が ${S} 画素より大きい（${W}×${H}）`);
  const N = S * S, data = new Float32Array(3 * N).fill(114 / 255);
  const dx = Math.floor((S - W) / 2), dy = Math.floor((S - H) / 2);
  for (let y = 0; y < H; y++) {
    const row = (y + dy) * S + dx;
    for (let x = 0; x < W; x++) {
      const i = (y * W + x) * 4, j = row + x;
      data[j] = rgba[i] / 255; data[N + j] = rgba[i + 1] / 255; data[2 * N + j] = rgba[i + 2] / 255;
    }
  }
  return { data, dx, dy, S };
}

export function iou(a, b) {
  const ix = Math.max(0, Math.min(a.x2, b.x2) - Math.max(a.x1, b.x1)), iy = Math.max(0, Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1));
  const inter = ix * iy, u = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter;
  return u > 0 ? inter / u : 0;
}
// 同じ種類で重なる枠は、確からしさの高い方だけ残す
export function nms(boxes, thr = 0.5, max = 100) {
  boxes.sort((a, b) => b.score - a.score);
  const keep = [];
  for (const b of boxes) { if (keep.every(k => k.cls !== b.cls || iou(k, b) < thr)) keep.push(b); if (keep.length >= max) break; }
  return keep;
}
// 出力 [1, 4+nc, N]（または [1, N, 4+nc]）を、元の画像（W×H）の座標の枠にする。letter は toTensorData の戻り値
export function decode(out, dims, nc, letter, conf = 0.25, iouThr = 0.5, W = Infinity, H = Infinity) {
  const chFirst = dims[1] === 4 + nc, N = chFirst ? dims[2] : dims[1], C = 4 + nc;
  if (!chFirst && dims[2] !== C) throw new Error(`出力の形が合わない（${dims.join('×')}、種類 ${nc}）`);
  const at = chFirst ? (c, i) => out[c * N + i] : (c, i) => out[i * C + c];
  const boxes = [];
  for (let i = 0; i < N; i++) {
    let best = -1, bs = conf;
    for (let c = 0; c < nc; c++) { const s = at(4 + c, i); if (s > bs) { bs = s; best = c; } }
    if (best < 0) continue;
    const cx = at(0, i) - letter.dx, cy = at(1, i) - letter.dy, w = at(2, i), h = at(3, i);
    const b = { x1: Math.max(0, cx - w / 2), y1: Math.max(0, cy - h / 2), x2: Math.min(W, cx + w / 2), y2: Math.min(H, cy + h / 2), score: bs, cls: best };
    if (b.x2 - b.x1 >= 2 && b.y2 - b.y1 >= 2) boxes.push(b);
  }
  return nms(boxes, iouThr);
}

// ------------------------------------------------------------ 小さな線形代数（配列 [x,y,z]）
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const add = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const scl = (a, k) => [a[0] * k, a[1] * k, a[2] * k];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const len = a => Math.hypot(a[0], a[1], a[2]);
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const v3 = { sub, add, scl, dot, len };

function invert4(m) {
  const [a00, a01, a02, a03, a10, a11, a12, a13, a20, a21, a22, a23, a30, a31, a32, a33] = m;
  const b00 = a00 * a11 - a01 * a10, b01 = a00 * a12 - a02 * a10, b02 = a00 * a13 - a03 * a10, b03 = a01 * a12 - a02 * a11;
  const b04 = a01 * a13 - a03 * a11, b05 = a02 * a13 - a03 * a12, b06 = a20 * a31 - a21 * a30, b07 = a20 * a32 - a22 * a30;
  const b08 = a20 * a33 - a23 * a30, b09 = a21 * a32 - a22 * a31, b10 = a21 * a33 - a23 * a31, b11 = a22 * a33 - a23 * a32;
  let det = b00 * b11 - b01 * b10 + b02 * b09 + b03 * b08 - b04 * b07 + b05 * b06;
  if (!det) return null;
  det = 1 / det;
  return [
    (a11 * b11 - a12 * b10 + a13 * b09) * det, (a02 * b10 - a01 * b11 - a03 * b09) * det, (a31 * b05 - a32 * b04 + a33 * b03) * det, (a22 * b04 - a21 * b05 - a23 * b03) * det,
    (a12 * b08 - a10 * b11 - a13 * b07) * det, (a00 * b11 - a02 * b08 + a03 * b07) * det, (a32 * b02 - a30 * b05 - a33 * b01) * det, (a20 * b05 - a22 * b02 + a23 * b01) * det,
    (a10 * b10 - a11 * b08 + a13 * b06) * det, (a01 * b08 - a00 * b10 - a03 * b06) * det, (a30 * b04 - a31 * b02 + a33 * b00) * det, (a21 * b02 - a20 * b04 - a23 * b00) * det,
    (a11 * b07 - a10 * b09 - a12 * b06) * det, (a00 * b09 - a01 * b07 + a02 * b06) * det, (a31 * b01 - a30 * b03 - a32 * b00) * det, (a20 * b03 - a21 * b01 + a22 * b00) * det,
  ];
}
const mul4v = (m, x, y, z, w) => [m[0] * x + m[4] * y + m[8] * z + m[12] * w, m[1] * x + m[5] * y + m[9] * z + m[13] * w, m[2] * x + m[6] * y + m[10] * z + m[14] * w, m[3] * x + m[7] * y + m[11] * z + m[15] * w];

// 1コマを撮ったときの射影行列 proj と姿勢 mat（カメラ→世界）から、画素⇔視線の変換を作る
export function makeFrame(proj, mat, W, H) {
  const Pinv = invert4(proj);
  if (!Pinv) throw new Error('射影行列に逆行列がない');
  const o = [mat[12], mat[13], mat[14]];
  const rayOf = (u, v) => {   // 画素 (u,v) を通る視線。d は単位ベクトル
    const q = mul4v(Pinv, 2 * (u + 0.5) / W - 1, 1 - 2 * (v + 0.5) / H, -1, 1);
    const cx = q[0] / q[3], cy = q[1] / q[3], cz = q[2] / q[3];
    const d = [mat[0] * cx + mat[4] * cy + mat[8] * cz, mat[1] * cx + mat[5] * cy + mat[9] * cz, mat[2] * cx + mat[6] * cy + mat[10] * cz];
    return { o, d: scl(d, 1 / len(d)) };
  };
  const project = p => {      // 世界の点 → 画素。カメラの後ろなら null
    const t = sub(p, o);
    const cx = mat[0] * t[0] + mat[1] * t[1] + mat[2] * t[2], cy = mat[4] * t[0] + mat[5] * t[1] + mat[6] * t[2], cz = mat[8] * t[0] + mat[9] * t[1] + mat[10] * t[2];
    const c = mul4v(proj, cx, cy, cz, 1);
    if (c[3] <= 1e-6) return null;
    return { u: (c[0] / c[3] + 1) / 2 * W - 0.5, v: (1 - c[1] / c[3]) / 2 * H - 0.5, depth: -cz };
  };
  return { rayOf, project, o, W, H, proj, mat };
}

// ------------------------------------------------------------ 多視点の3D化
const rayDist = (p, r) => { const w = sub(p, r.o); return len(sub(w, scl(r.d, dot(w, r.d)))); };
function lsPoint(obs) {
  const A = [0, 0, 0, 0, 0, 0, 0, 0, 0], b = [0, 0, 0];
  for (const { o, d } of obs) {
    const m = [1 - d[0] * d[0], -d[0] * d[1], -d[0] * d[2], -d[1] * d[0], 1 - d[1] * d[1], -d[1] * d[2], -d[2] * d[0], -d[2] * d[1], 1 - d[2] * d[2]];
    for (let k = 0; k < 9; k++) A[k] += m[k];
    b[0] += m[0] * o[0] + m[1] * o[1] + m[2] * o[2]; b[1] += m[3] * o[0] + m[4] * o[1] + m[5] * o[2]; b[2] += m[6] * o[0] + m[7] * o[1] + m[8] * o[2];
  }
  const [a, b1, c, d, e, f, g, h, i] = A;
  const det = a * (e * i - f * h) - b1 * (d * i - f * g) + c * (d * h - e * g);
  if (Math.abs(det) < 1e-12) return null;
  const inv = [e * i - f * h, c * h - b1 * i, b1 * f - c * e, f * g - d * i, a * i - c * g, c * d - a * f, d * h - e * g, b1 * g - a * h, a * e - b1 * d];
  return [0, 1, 2].map(r => (inv[r * 3] * b[0] + inv[r * 3 + 1] * b[1] + inv[r * 3 + 2] * b[2]) / det);
}
// 点 p が視線 r からどれだけ角度でずれているか（rad）。視線の後ろなら π
const angErr = (p, r) => { const w = sub(p, r.o), L = len(w); if (L < 1e-9) return Math.PI; const c = dot(w, r.d) / L; return c <= 0 ? Math.PI : Math.acos(Math.min(1, c)); };
const spread = use => { let m = 0; for (let i = 0; i < use.length; i++) for (let j = i + 1; j < use.length; j++) m = Math.max(m, Math.acos(Math.min(1, Math.abs(dot(use[i].d, use[j].d))))); return m; };
// 複数の視線 {o:[x,y,z], d:[x,y,z]（単位）} が指す点。
// 2本ずつの交点のうち、角度のずれ inlierDeg 度以内で合う視線が最も多いものを選び（総当たりの RANSAC）、合う視線だけで最小二乗にする。
// 合う視線が min(3, 本数) 本に満たない、開きが minAngle 度未満、または点が視線の後ろにあれば null
export function triangulateMany(obs, minAngle = 3, inlierDeg = 2) {
  if (obs.length < 2) return null;
  const thr = inlierDeg * Math.PI / 180, need = Math.min(3, obs.length);
  let best = null;
  for (let i = 0; i < obs.length; i++) for (let j = i + 1; j < obs.length; j++) {
    if (Math.abs(dot(obs[i].d, obs[j].d)) > 0.99996) continue;   // ほぼ平行（0.5° 未満）
    const p = lsPoint([obs[i], obs[j]]);
    if (!p || angErr(p, obs[i]) > thr || angErr(p, obs[j]) > thr) continue;
    let cnt = 0, sum = 0;
    for (const r of obs) { const e = angErr(p, r); if (e <= thr) { cnt++; sum += e; } }
    if (!best || cnt > best.cnt || (cnt === best.cnt && sum < best.sum)) best = { p, cnt, sum };
  }
  if (!best || best.cnt < need) return null;
  let use = obs.filter(r => angErr(best.p, r) <= thr), p = lsPoint(use) || best.p;
  if (use.some(r => angErr(p, r) > thr)) { use = use.filter(r => angErr(p, r) <= thr); if (use.length < need) return null; p = lsPoint(use) || p; }
  const maxAng = spread(use);
  if (maxAng < minAngle * Math.PI / 180) return null;
  let rss = 0, ass = 0, depth = 0;
  for (const r of use) {
    const w = sub(p, r.o);
    if (dot(w, r.d) <= 0) return null;
    const q = rayDist(p, r), a = angErr(p, r); rss += q * q; ass += a * a; depth += len(w);
  }
  return { p, rms: Math.sqrt(rss / use.length), angRms: Math.sqrt(ass / use.length), n: use.length, angle: maxAng * 180 / Math.PI, depth: depth / use.length };
}

// ------------------------------------------------------------ 距離（離隔帯までの参考値）
// 線分 p1–q1 と線分 p2–q2 の最短距離（点は p=q の線分として渡す）
export function segSegDist(p1, q1, p2, q2) {
  const d1 = sub(q1, p1), d2 = sub(q2, p2), r = sub(p1, p2), a = dot(d1, d1), e = dot(d2, d2), f = dot(d2, r), EPS = 1e-12;
  let s, t;
  if (a <= EPS && e <= EPS) return len(r);
  if (a <= EPS) { s = 0; t = clamp(f / e, 0, 1); }
  else {
    const c = dot(d1, r);
    if (e <= EPS) { t = 0; s = clamp(-c / a, 0, 1); }
    else {
      const b = dot(d1, d2), den = a * e - b * b;
      s = den > EPS ? clamp((b * f - c * e) / den, 0, 1) : 0;
      t = (b * s + f) / e;
      if (t < 0) { t = 0; s = clamp(-c / a, 0, 1); } else if (t > 1) { t = 1; s = clamp((b - c) / a, 0, 1); }
    }
  }
  return len(sub(add(p1, scl(d1, s)), add(p2, scl(d2, t))));
}

// 追跡の形（線分 a–b と、その周りの半径）。物の大きさと奥行きの不確かさを半径に足して保守側にする。
// 縦長の物（がいし・ブッシングなど）は鉛直の線分、横長の物（架空線など）は水平の線分にする
export function trackShape(t, r = 0) {
  const p = t.est.p, { h, w, dir } = t.ext, u = t.unc;
  if (h >= w || !dir) return { a: [p[0], p[1] - h, p[2]], b: [p[0], p[1] + h, p[2]], r: r + w + u };
  return { a: [p[0] - dir[0] * w, p[1], p[2] - dir[2] * w], b: [p[0] + dir[0] * w, p[1], p[2] + dir[2] * w], r: r + h + u };
}

// ------------------------------------------------------------ 検出の追跡
// 同じ種類で、前の位置（3D が出ていれば今のコマへの投影、無ければ前の視線を仮の奥行きで投影）に近い枠を同じ物とみなす。
// 視点が動くたびに視線を足し、3視点以上・開き 3° 以上で3Dにする。3D になった物は見えなくなっても残す
export class Tracker {
  constructor(opts = {}) {
    this.opts = { keepMs: 4000, minMove: 0.15, maxObs: 40, minObs: 3, sigma: 0.012, assumeDepth: 10, maxUnc: 10, ...opts };
    this.tracks = []; this.nextId = 1;
  }
  reset() { this.tracks = []; this.nextId = 1; }
  // dets: decode() の枠（frame の W×H の座標）。frame: makeFrame() の戻り値。now: ミリ秒。戻り値: dets と同じ並びの追跡番号
  update(dets, frame, now) {
    const { assumeDepth, keepMs } = this.opts, pairs = [];
    this.tracks.forEach((t, ti) => {
      let pred = null;
      if (t.est) pred = frame.project(t.est.p);
      else if (t.obs.length) { const r = t.obs[t.obs.length - 1]; pred = frame.project(add(r.o, scl(r.d, assumeDepth))); }
      dets.forEach((d, di) => {
        if (d.cls !== t.cls) return;
        const cx = (d.x1 + d.x2) / 2, cy = (d.y1 + d.y2) / 2, gate = Math.max(d.x2 - d.x1, d.y2 - d.y1, 24) * 0.75;
        let s = 0;
        if (pred) { const dist = Math.hypot(cx - pred.u, cy - pred.v); if (dist < gate) s = 1 - dist / gate; }
        if (now - t.lastSeen < 1000) { const v = iou(t.box, d); if (v > 0.15) s = Math.max(s, v); }
        if (s > 0) pairs.push([s, ti, di]);
      });
    });
    pairs.sort((a, b) => b[0] - a[0]);
    const ids = new Array(dets.length).fill(0), usedT = new Set();
    for (const [, ti, di] of pairs) {
      if (usedT.has(ti) || ids[di]) continue;
      usedT.add(ti); ids[di] = this.tracks[ti].id; this.observe(this.tracks[ti], dets[di], frame, now);
    }
    dets.forEach((d, di) => {
      if (ids[di]) return;
      const t = { id: this.nextId++, cls: d.cls, box: d, obs: [], est: null, unc: Infinity, ext: { h: 0, w: 0, dir: null }, hits: 0, firstSeen: now, lastSeen: now, score: d.score };
      this.tracks.push(t); ids[di] = t.id; this.observe(t, d, frame, now);
    });
    this.tracks = this.tracks.filter(t => t.est || now - t.lastSeen < keepMs);
    return ids;
  }
  observe(t, d, frame, now) {
    const o = this.opts, cx = (d.x1 + d.x2) / 2, cy = (d.y1 + d.y2) / 2, r = frame.rayOf(cx, cy);
    t.box = d; t.lastSeen = now; t.hits++; t.score = d.score;
    const last = t.obs[t.obs.length - 1];
    if (!last || len(sub(last.o, r.o)) > o.minMove) {   // 前に足した場所から minMove 以上動いたときだけ足す
      t.obs.push(r);
      if (t.obs.length > o.maxObs) t.obs.splice(1 + (t.hits % (t.obs.length - 2)), 1);   // 最初と最後の視線は残す
    }
    if (t.obs.length >= o.minObs) {
      const est = triangulateMany(t.obs);
      // 奥行きの不確かさの目安: 奥行き × 角度のぶれ ÷ sin(開き)。ぶれは実測の 1.5 倍か sigma の大きい方（保守側）
      if (est) { t.est = est; t.unc = Math.min(o.maxUnc, est.depth * Math.max(o.sigma, 1.5 * est.angRms) / Math.sin(est.angle * Math.PI / 180) + est.rms); }
    }
    if (t.est) {   // 枠の大きさを推定した奥行きで m に直す（なめらかにする）
      const D = len(sub(t.est.p, r.o)), at = (u, v) => { const q = frame.rayOf(u, v); return add(q.o, scl(q.d, D)); };
      const left = at(d.x1, cy), right = at(d.x2, cy), h = len(sub(at(cx, d.y1), at(cx, d.y2))) / 2, w = len(sub(left, right)) / 2;
      const k = t.ext.h || t.ext.w ? 0.3 : 1;
      t.ext.h += k * (h - t.ext.h); t.ext.w += k * (w - t.ext.w);
      const hz = [right[0] - left[0], 0, right[2] - left[2]], n = len(hz);
      if (n > 1e-6) t.ext.dir = scl(hz, 1 / n);
    }
  }
}
