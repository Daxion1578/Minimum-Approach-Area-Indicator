// web/lab/detector.js の計算を確かめる（実験ブランチ lab-camera-ar）。実行: node web/lab/tests/detector.test.mjs
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { CLASSES, INPUT, toTensorData, decode, makeFrame, triangulateMany, Tracker, segSegDist, trackShape, readOnnxNames, namesMatch } from '../detector.js';

const here = p => fileURLToPath(new URL(p, import.meta.url));
let n = 0;
const test = (name, fn) => { fn(); n++; console.log('ok', name); };
const near = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg}: ${a} と ${b} の差が ${tol} を超える`);

// 合成カメラ: 射影（WebXR と同じ列優先）と姿勢（カメラ→世界）。yaw は Y 軸回り、pitch は X 軸回り（上向きが正）
function perspective(fovyDeg, aspect, near = 0.1, far = 1000) {
  const f = 1 / Math.tan(fovyDeg * Math.PI / 360);
  return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) / (near - far), -1, 0, 0, 2 * far * near / (near - far), 0];
}
function pose(pos, yawDeg, pitchDeg) {
  const y = yawDeg * Math.PI / 180, p = pitchDeg * Math.PI / 180, cy = Math.cos(y), sy = Math.sin(y), cp = Math.cos(p), sp = Math.sin(p);
  // R = Ry(yaw)·Rx(pitch) の列
  const c0 = [cy, 0, -sy], c1 = [sy * sp, cp, cy * sp], c2 = [sy * cp, -sp, cy * cp];
  return [...c0, 0, ...c1, 0, ...c2, 0, ...pos, 1];
}
const W = 360, H = 640, PROJ = perspective(60, W / H);

test('探す語が lab/yoloworld/classes.txt と同じ順', () => {
  const txt = readFileSync(here('../../../lab/yoloworld/classes.txt'), 'utf8').split('\n').map(s => s.trim()).filter(s => s && !s.startsWith('#'));
  assert.deepEqual(CLASSES.map(c => c.en), txt);
});

test('前処理: 中央に置いて 0〜1、余白は灰色', () => {
  const rgba = new Uint8Array([255, 0, 0, 255, 0, 255, 0, 255]);   // 2×1
  const L = toTensorData(rgba, 2, 1, 4);
  assert.equal(L.dx, 1); assert.equal(L.dy, 1);
  const N = 16, at = (c, x, y) => L.data[c * N + y * 4 + x];
  assert.equal(at(0, 1, 1), 1); assert.equal(at(1, 1, 1), 0); assert.equal(at(1, 2, 1), 1);
  near(at(0, 0, 0), 114 / 255, 1e-6, '余白');
  assert.throws(() => toTensorData(new Uint8Array(4 * 700), 700, 1));
});

test('後処理: 両方の並びを読み、同じ種類の重なりだけ消す', () => {
  const nc = 3, N = 4, letter = { dx: 10, dy: 0 };
  const rows = [   // cx, cy, w, h, s0, s1, s2（入力 640 の座標）
    [110, 100, 40, 80, 0.9, 0.1, 0.0],
    [112, 102, 40, 80, 0.8, 0.0, 0.0],   // 1本目と重なる同じ種類 → 消える
    [112, 102, 40, 80, 0.0, 0.7, 0.0],   // 重なるが別の種類 → 残る
    [300, 300, 10, 10, 0.1, 0.1, 0.2],   // 閾値未満 → 出ない
  ];
  const chFirst = new Float32Array((4 + nc) * N), chLast = new Float32Array(N * (4 + nc));
  rows.forEach((r, i) => r.forEach((v, c) => { chFirst[c * N + i] = v; chLast[i * (4 + nc) + c] = v; }));
  for (const [out, dims] of [[chFirst, [1, 4 + nc, N]], [chLast, [1, N, 4 + nc]]]) {
    const b = decode(out, dims, nc, letter, 0.25, 0.5, 620, 640);
    assert.equal(b.length, 2);
    assert.equal(b[0].cls, 0); near(b[0].x1, 80, 1e-4, 'x1'); near(b[0].y2, 140, 1e-4, 'y2');
    assert.equal(b[1].cls, 1);
  }
});

test('画素⇔視線: 投影と視線が往復する', () => {
  const fr = makeFrame(PROJ, pose([1.2, 1.5, 2.0], 25, 12), W, H);
  for (const X of [[0, 5.6, -9], [3, 8, -20], [-2, 2, -6]]) {
    const q = fr.project(X); assert.ok(q);
    const r = fr.rayOf(q.u, q.v), w = [X[0] - r.o[0], X[1] - r.o[1], X[2] - r.o[2]];
    const s = w[0] * r.d[0] + w[1] * r.d[1] + w[2] * r.d[2];
    const off = Math.hypot(w[0] - s * r.d[0], w[1] - s * r.d[1], w[2] - s * r.d[2]);
    near(off, 0, 1e-6, '視線からのずれ');
  }
  assert.equal(fr.project([1.2, 1.5, 10]), null);   // 後ろ
});

test('多視点の3D化: 外れた視線を1本外す', () => {
  const X = [1, 6, -15], obs = [];
  for (let i = 0; i < 6; i++) {
    const o = [-2 + i * 0.8, 1.5, 0], d = [X[0] - o[0], X[1] - o[1], X[2] - o[2]], L = Math.hypot(...d);
    obs.push({ o, d: d.map(v => v / L) });
  }
  const e = triangulateMany(obs); near(e.p[0], 1, 1e-6, 'x'); near(e.p[1], 6, 1e-6, 'y'); near(e.p[2], -15, 1e-6, 'z');
  const bad = [...obs, { o: [0, 1.5, 0], d: [0.6, 0, -0.8] }];
  const e2 = triangulateMany(bad); assert.equal(e2.n, 6); near(e2.p[2], -15, 1e-6, '外れ値を外した z');
  assert.equal(triangulateMany(obs.slice(0, 1)), null);
  assert.equal(triangulateMany([obs[0], { o: [obs[0].o[0] + 0.01, 1.5, 0], d: obs[0].d }]), null);   // 開きが足りない
});

test('距離: 線分どうし・点と線分（総当たりと比べる）', () => {
  near(segSegDist([0, 0, 0], [0, 2, 0], [3, 1, 0], [3, 1, 4]), 3, 1e-9, '平行でない');
  near(segSegDist([0, 0, 0], [0, 0, 0], [0, 0, 5], [0, 0, 9]), 5, 1e-9, '点と線分の端');
  near(segSegDist([0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]), 1, 1e-9, '平行');
  let seed = 11; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 10;
  for (let k = 0; k < 200; k++) {
    const P = [0, 1, 2, 3].map(() => [rnd(), rnd(), rnd()]);
    if (k % 7 === 0) P[1] = [...P[0]];                                                        // 点と線分
    if (k % 11 === 0) P[3] = [P[2][0] + P[1][0] - P[0][0], P[2][1] + P[1][1] - P[0][1], P[2][2] + P[1][2] - P[0][2]];   // 平行
    let best = Infinity; const N = 120;
    for (let i = 0; i <= N; i++) for (let j = 0; j <= N; j++) {
      const s = i / N, t = j / N, a = P[0].map((v, c) => v + s * (P[1][c] - v)), b = P[2].map((v, c) => v + t * (P[3][c] - v));
      best = Math.min(best, Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]));
    }
    const d = segSegDist(P[0], P[1], P[2], P[3]);
    assert.ok(d <= best + 1e-9 && d >= best - 0.15, `例 ${k}: ${d} と総当たり ${best}`);
  }
});

test('ONNX の付帯情報から探す語を読む（重みの部分は読まずに飛ばす）', () => {
  const enc = new TextEncoder(), varint = n => { const o = []; do { let b = n % 128; n = Math.floor(n / 128); if (n) b |= 0x80; o.push(b); } while (n); return o; };
  const ld = (field, bytes) => [...varint(field * 8 + 2), ...varint(bytes.length), ...bytes];
  const entry = (k, v) => ld(14, [...ld(1, [...enc.encode(k)]), ...ld(2, [...enc.encode(v)])]);
  const names = `{${CLASSES.map((c, i) => `${i}: '${c.en}'`).join(', ')}}`;
  const graph = new Uint8Array(300000).fill(7);                                            // 大きな graph（7番）の代わり
  const buf = new Uint8Array([...varint(1 * 8), 9, ...ld(7, [...graph]), ...entry('author', 'Ultralytics'), ...entry('names', names)]);
  const got = readOnnxNames(buf);
  assert.ok(namesMatch(got));
  const swapped = [...got]; [swapped[0], swapped[10]] = [swapped[10], swapped[0]];
  assert.equal(namesMatch(swapped), false);                                                // 数が同じでも順番が違えば合わない
  assert.equal(readOnnxNames(new Uint8Array([0x0a, 0x05, 1])), null);                       // 壊れたもの
  assert.equal(readOnnxNames(new Uint8Array([...varint(8), 9])), null);                     // names が無い
});

// 歩きながら見る場面: 3つの物（がいし2つ、クレーンのブーム1つ）を、横へ 4 m 歩きつつ首を振って撮る
test('追跡: 歩くだけで3Dになり、番号が変わらない（急に向きを変えても）', () => {
  const objs = [
    { cls: 0, c: [0, 6, -15], h: 0.6, w: 0.15 },
    { cls: 0, c: [3, 6, -15], h: 0.6, w: 0.15 },
    { cls: 8, c: [-4, 4, -10], h: 0.4, w: 2.0 },
  ];
  let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5);
  const tr = new Tracker(); let now = 0; const idsSeen = objs.map(() => new Set());
  for (let i = 0; i <= 30; i++) {
    const x = -2 + i * 4 / 30, yaw = 8 * Math.sin(i / 3) + (i === 20 ? 14 : 0), fr = makeFrame(PROJ, pose([x, 1.5, 0], yaw, 14), W, H);
    const dets = [], which = [];
    objs.forEach((ob, k) => {
      const pts = [[0, -ob.h, 0], [0, ob.h, 0], [-ob.w, 0, 0], [ob.w, 0, 0]].map(dv => fr.project([ob.c[0] + dv[0], ob.c[1] + dv[1], ob.c[2] + dv[2]]));
      if (pts.some(q => !q)) return;
      const us = pts.map(q => q.u), vs = pts.map(q => q.v);
      const b = { x1: Math.min(...us) + rnd(), x2: Math.max(...us) + rnd(), y1: Math.min(...vs) + rnd(), y2: Math.max(...vs) + rnd(), score: 0.8, cls: ob.cls };
      if (b.x2 < 0 || b.x1 > W || b.y2 < 0 || b.y1 > H) return;
      dets.push(b); which.push(k);
    });
    now += 250;
    const ids = tr.update(dets, fr, now);
    ids.forEach((id, j) => idsSeen[which[j]].add(id));
  }
  idsSeen.forEach((s, k) => assert.equal(s.size, 1, `物 ${k} の番号が変わった: ${[...s]}`));
  assert.equal(tr.tracks.length, 3);
  for (const [k, ob] of objs.entries()) {
    const t = tr.tracks.find(tt => idsSeen[k].has(tt.id));
    assert.ok(t.est, `物 ${k} が3Dにならない`);
    const err = Math.hypot(t.est.p[0] - ob.c[0], t.est.p[1] - ob.c[1], t.est.p[2] - ob.c[2]);
    assert.ok(err < 0.5, `物 ${k} の位置の誤差 ${err.toFixed(2)} m`);
    assert.ok(err <= t.unc + 0.05, `物 ${k}: 誤差 ${err.toFixed(2)} m が見積もり ±${t.unc.toFixed(2)} m を超える`);
    const sh = trackShape(t, 4);
    if (ob.h >= ob.w) { near(sh.a[0], sh.b[0], 1e-9, '縦長は鉛直'); assert.ok(sh.r >= 4 + 0.1); }
    else near(sh.a[1], sh.b[1], 1e-9, '横長は水平');
    near(t.ext.h, ob.h, 0.15, `物 ${k} の高さの半分`);
  }
});

test('追跡: 遠くて基線が短い物は、奥行きが定まるまで3Dにしない', () => {
  const tr = new Tracker(); let now = 0;
  for (let i = 0; i <= 6; i++) {
    const fr = makeFrame(PROJ, pose([i * 0.42, 1.5, 0], 0, 8), W, H), q = fr.project([0, 8, -40]);   // 40 m 先を 2.5 m の基線で（開き 約3.5°）
    now += 250; tr.update([{ x1: q.u - 3, x2: q.u + 3, y1: q.v - 8, y2: q.v + 8, score: 0.8, cls: 0 }], fr, now);
  }
  const t = tr.tracks[0];
  assert.equal(t.est, null, '3D にしてはいけない');
  assert.ok(t.cand && t.cand.unc > tr.opts.maxUnc, `途中の値の不確かさ ${t.cand && t.cand.unc}`);
});

test('追跡: 動く物は、端末が止まって古い視線だけになると3Dを取り消し、見えなくなれば消す', () => {
  const tr = new Tracker(); let now = 0, last = null;
  const boom = { cls: 8, c: [-3, 5, -12], h: 0.3, w: 2 };
  const see = (fr, c) => { const q = fr.project(c); return { x1: q.u - 20, x2: q.u + 20, y1: q.v - 4, y2: q.v + 4, score: 0.8, cls: boom.cls }; };
  for (let i = 0; i <= 12; i++) { last = makeFrame(PROJ, pose([-1.5 + i * 0.25, 1.5, 0], -8, 12), W, H); now += 250; tr.update([see(last, boom.c)], last, now); }
  assert.ok(tr.tracks[0].est, '歩いている間は3Dになる');
  for (let i = 0; i < 30; i++) { now += 250; tr.update([see(last, [boom.c[0] + i * 0.1, boom.c[1], boom.c[2]])], last, now); }   // 端末は止まり、ブームが動く
  assert.equal(tr.tracks[0].est, null, '古い視線だけでは3Dを残さない');
  now += 5000; tr.update([], last, now);
  assert.equal(tr.tracks.length, 0, '見えなくなった動く物は消える');
});

console.log(`${n} 件 OK（入力 ${INPUT}）`);
