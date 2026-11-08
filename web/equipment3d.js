// 機器の 3D 形状。寸法はサーバの /api/equipment（synth/equipment.py）から受け取り、図面と同じ値で形を作る。
// 写実ではなく「丁寧な模式」: 鉄構の格子、ひだのある碍管、タンク形 GCB、パンタ型断路器、変圧器の放熱器。
import * as THREE from './vendor/three/three.module.js';

const MAT = {
  steel: new THREE.MeshStandardMaterial({ color: 0x93a0b0, metalness: 0.45, roughness: 0.55 }),
  steelDark: new THREE.MeshStandardMaterial({ color: 0x5d6878, metalness: 0.45, roughness: 0.6 }),
  porcelain: new THREE.MeshStandardMaterial({ color: 0xece6d6, roughness: 0.35 }),
  porcelainBrown: new THREE.MeshStandardMaterial({ color: 0x7a4f3c, roughness: 0.4 }),
  tank: new THREE.MeshStandardMaterial({ color: 0xb4bec9, metalness: 0.3, roughness: 0.5 }),
  concrete: new THREE.MeshStandardMaterial({ color: 0x8c8a84, roughness: 0.95 }),
  cabinet: new THREE.MeshStandardMaterial({ color: 0x6f7b88, roughness: 0.6 }),
  load: new THREE.MeshStandardMaterial({ color: 0x7b8899, roughness: 0.6 }),
};
// 大きな箱にだけ輪郭線を引く（形が読みやすくなる。小さい部品まで引くと重くうるさい）
const EDGE = new THREE.LineBasicMaterial({ color: 0xd6ecff, transparent: true, opacity: 0.32 });
const LATTICE = new THREE.LineBasicMaterial({ color: 0x93a0b0 });
const PH = { R: -1, S: 0, T: 1 };

function box(g, w, d, h, mat, x, y, z) { const geo = new THREE.BoxGeometry(w, d, h); const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); g.add(m);
  if (w * d * h > 1.5 && mat !== MAT.concrete) { const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo), EDGE); e.position.copy(m.position); g.add(e); }
  return m; }
function cylZ(g, r, h, mat, x, y, z0, seg = 14) { const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, seg), mat); m.rotation.x = Math.PI / 2; m.position.set(x, y, z0 + h / 2); g.add(m); return m; }
function cylAlong(g, a, b, r, mat, seg = 12) { const va = new THREE.Vector3(...a), vb = new THREE.Vector3(...b); const len = va.distanceTo(vb); const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, len, seg), mat); m.position.copy(va.clone().add(vb).multiplyScalar(0.5)); m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), vb.clone().sub(va).normalize()); g.add(m); return m; }

// 碍管: 芯の円柱に、ひだ（薄い円盤）を重ねる
function porcelain(g, r, h, x, y, z0, mat = MAT.porcelain) {
  cylZ(g, r * 0.6, h, mat, x, y, z0, 12);
  const n = Math.max(3, Math.round(h / 0.22));
  const shed = new THREE.CylinderGeometry(r, r * 0.85, 0.06, 14);
  for (let i = 0; i < n; i++) { const m = new THREE.Mesh(shed, mat); m.rotation.x = Math.PI / 2; m.position.set(x, y, z0 + (i + 0.5) * h / n); g.add(m); }
}

// 格子柱: 4 本の縦材と斜材（線）で描く
function latticeColumn(g, x, y, h, w) {
  const hw = w / 2;
  for (const [dx, dy] of [[-hw, -hw], [hw, -hw], [-hw, hw], [hw, hw]]) box(g, 0.08, 0.08, h, MAT.steel, x + dx, y + dy, h / 2);
  const pts = []; const n = Math.max(1, Math.floor(h / 1.2));
  for (let i = 0; i < n; i++) { const z0 = i * h / n, z1 = (i + 1) * h / n; const s = i % 2 ? 1 : -1;
    pts.push(new THREE.Vector3(x - hw * s, y - hw, z0), new THREE.Vector3(x + hw * s, y - hw, z1), new THREE.Vector3(x - hw * s, y + hw, z0), new THREE.Vector3(x + hw * s, y + hw, z1),
             new THREE.Vector3(x - hw, y - hw * s, z0), new THREE.Vector3(x - hw, y + hw * s, z1), new THREE.Vector3(x + hw, y - hw * s, z0), new THREE.Vector3(x + hw, y + hw * s, z1)); }
  g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), LATTICE));
  box(g, 1.2, 1.2, 0.4, MAT.concrete, x, y, 0.2);
}
function latticeBeam(g, a, b, d) {
  const va = new THREE.Vector3(...a), vb = new THREE.Vector3(...b); const dir = vb.clone().sub(va); const len = dir.length(); dir.normalize();
  const side = new THREE.Vector3(-dir.y, dir.x, 0); const hd = d / 2;
  for (const [sy, sz] of [[-hd, -hd], [hd, -hd], [-hd, hd], [hd, hd]]) { const o = side.clone().multiplyScalar(sy); cylAlong(g, [va.x + o.x, va.y + o.y, va.z + sz], [vb.x + o.x, vb.y + o.y, vb.z + sz], 0.04, MAT.steel, 6); }
  const pts = []; const n = Math.max(1, Math.floor(len / 1.2));
  for (let i = 0; i < n; i++) { const p0 = va.clone().add(dir.clone().multiplyScalar(i * len / n)), p1 = va.clone().add(dir.clone().multiplyScalar((i + 1) * len / n)); const s = i % 2 ? 1 : -1;
    for (const sg of [-hd, hd]) { const o = side.clone().multiplyScalar(sg); pts.push(new THREE.Vector3(p0.x + o.x, p0.y + o.y, p0.z - hd * s), new THREE.Vector3(p1.x + o.x, p1.y + o.y, p1.z + hd * s)); } }
  g.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), LATTICE));
}

export function buildEquipment(site, dims) {
  const g = new THREE.Group();
  const nodes = Object.fromEntries(site.topology.nodes.map(n => [n.id, n]));
  const T = dims.transformer;
  const byId = {};   // 機器 ID → Group（状態で色味を変えるため）

  for (const it of site.layout.items) {
    const n = nodes[it.id]; if (!n || !it.at) continue;
    const [x, y] = it.at; const kv = n.voltage_kv || 220; const E = dims.equip[String(kv)]; const sp = E.phase_sp;
    const eg = new THREE.Group(); byId[it.id] = eg; g.add(eg);
    if (n.kind === 'disconnector') {
      const panto = kv === 220 && it.id.endsWith('-BLS');
      const alongX = it.id.startsWith('220-SEC');
      const e = panto ? E.ds_panto : (alongX && E.ds_sec) ? E.ds_sec : E.ds;   // セクション断路器は高い架台（H 形）
      for (const ph of ['R', 'S', 'T']) {
        let cx = x + PH[ph] * sp, cy = y; if (panto) { cy = y - PH[ph] * sp; } else if (alongX) { cx = x; cy = y - PH[ph] * sp; }
        if (panto) {
          box(eg, e.base, e.base, 0.3, MAT.concrete, cx, cy, 0.15); box(eg, e.base * 0.5, e.base * 0.5, e.column - 0.3, MAT.steel, cx, cy, 0.3 + (e.column - 0.3) / 2);
          porcelain(eg, e.ins_d / 2 + 0.08, e.insulator, cx, cy, e.column);
          const top = e.column + e.insulator; box(eg, e.arm_w, 0.5, e.head, MAT.steelDark, cx, cy, top + e.head / 2);
          const busZ = 10.5; const zt = top + e.head; const w = e.arm_w / 2;   // パンタ（閉）: 菱形 2 つ
          const pts = [];
          for (const s of [-1, 1]) pts.push(new THREE.Vector3(cx, cy + s * w, zt), new THREE.Vector3(cx, cy - s * w * 0.3, (zt + busZ) / 2), new THREE.Vector3(cx, cy - s * w * 0.3, (zt + busZ) / 2), new THREE.Vector3(cx, cy + s * w * 0.2, busZ - 0.3), new THREE.Vector3(cx, cy + s * w * 0.9, (zt + busZ) / 2), new THREE.Vector3(cx, cy + s * w, zt));
          eg.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0xc9ced4 })));
          continue;
        }
        // 2 柱（垂直一点切）または 3 柱（二点切）。架台は電流方向に長い
        const posts = e.type === 'double_break' ? [-e.span / 2, 0, e.span / 2] : [-e.span / 2, e.span / 2];
        const fw = e.frame_w, fl = e.frame;
        if (alongX) { box(eg, fl, fw, 0.25, MAT.steel, cx, cy, e.column - 0.125); } else { box(eg, fw, fl, 0.25, MAT.steel, cx, cy, e.column - 0.125); }
        for (const d of [-fl / 2 + 0.2, fl / 2 - 0.2]) { const px = alongX ? cx + d : cx, py = alongX ? cy : cy + d; box(eg, 0.25, 0.25, e.column - 0.25, MAT.steel, px, py, (e.column - 0.25) / 2); box(eg, 0.7, 0.7, 0.3, MAT.concrete, px, py, 0.15); }
        for (const d of posts) { const px = alongX ? cx + d : cx, py = alongX ? cy : cy + d; porcelain(eg, e.ins_d / 2 + 0.07, e.insulator, px, py, e.column); }
        const top = e.column + e.insulator; const a = alongX ? [cx - e.span / 2, cy, top + 0.15] : [cx, cy - e.span / 2, top + 0.15], b = alongX ? [cx + e.span / 2, cy, top + 0.15] : [cx, cy + e.span / 2, top + 0.15];
        cylAlong(eg, a, b, 0.05, MAT.steelDark, 8);
      }
    } else if (n.kind === 'breaker') {
      const e = E.cb;
      for (const ph of ['R', 'S', 'T']) {
        const cx = x + PH[ph] * sp;
        box(eg, e.base + 0.4, e.tank_len + 0.4, 0.25, MAT.concrete, cx, y, 0.125);
        for (const d of [-e.tank_len / 2 + 0.4, e.tank_len / 2 - 0.4]) box(eg, 0.25, 0.25, e.frame - 0.25, MAT.steel, cx, y + d, 0.25 + (e.frame - 0.25) / 2);
        const zt = e.frame + e.tank_d / 2;
        const tank = new THREE.Mesh(new THREE.CapsuleGeometry(e.tank_d / 2, e.tank_len - e.tank_d, 4, 16), MAT.tank); tank.position.set(cx, y, zt); eg.add(tank);   // Y 軸方向
        for (const d of [-e.bushing_pitch / 2, e.bushing_pitch / 2]) {
          cylZ(eg, e.ct_housing.d / 2, e.ct_housing.h, MAT.tank, cx, y + d, e.frame + e.tank_d - 0.05);
          porcelain(eg, e.bushing_d / 2 + 0.08, e.bushing_h - e.ct_housing.h, cx, y + d, e.frame + e.tank_d + e.ct_housing.h);
          cylZ(eg, 0.12, 0.2, MAT.steelDark, cx, y + d, e.frame + e.tank_d + e.bushing_h);
        }
      }
      const [cw, cd, ch] = e.cabinet; box(eg, cw, cd, ch, MAT.cabinet, x + sp + e.tank_d / 2 + cw / 2 + 0.1, y, 0.25 + ch / 2);
    } else if (n.kind === 'transformer') {
      const [tx, ty, tz] = T.tank; const [fx, fy] = T.found; const [bx, by] = T.bund;
      box(eg, fx, fy, 0.4, MAT.concrete, x, y, 0.2);
      box(eg, tx, ty, tz, MAT.tank, x, y, 0.4 + tz / 2);
      const nR = T.radiator_n, rl = T.radiator_len, rd = T.radiator_depth;
      for (const side of [-1, 1]) { for (let i = 0; i < nR; i++) { const yy = y - rl / 2 + rl * i / (nR - 1); box(eg, rd, 0.08, tz * 0.8, MAT.tank, x + side * (tx / 2 + rd / 2), yy, 0.4 + tz / 2); }
        box(eg, 0.15, rl, 0.25, MAT.tank, x + side * (tx / 2 + rd), y, 0.4 + tz * 0.9); }
      const c = T.conservator; const cons = new THREE.Mesh(new THREE.CylinderGeometry(c.d / 2, c.d / 2, c.len, 16), MAT.tank); cons.rotation.z = Math.PI / 2; cons.position.set(x, y + ty / 2 - c.d / 2 - 0.2, c.z); eg.add(cons);
      for (const key of ['hv', 'lv']) { const B = T[key]; const pitch = key === 'hv' ? T.hv_pitch : T.lv_pitch; for (const ph of ['R', 'S', 'T']) { const px = x + PH[ph] * pitch; box(eg, 0.8, 0.8, 0.5, MAT.tank, px, y + B.y, 0.4 + tz + 0.25); porcelain(eg, B.d / 2 + 0.1, B.top_z - 0.4 - tz - 0.5, px, y + B.y, 0.4 + tz + 0.5, MAT.porcelainBrown); } }
      // 油流出防止堰（低い壁）
      for (const [w, d, px, py] of [[bx, 0.2, x, y - by / 2], [bx, 0.2, x, y + by / 2], [0.2, by, x - bx / 2, y], [0.2, by, x + bx / 2, y]]) box(eg, w, d, 0.5, MAT.concrete, px, py, 0.25);
    } else if (n.kind === 'load') {
      const key = it.id.includes('SC') ? 'SC' : 'SR'; const [sx, sy, sz] = dims.loads[key].size;
      box(eg, sx, sy, 0.3, MAT.concrete, x, y, 0.15); box(eg, sx * 0.9, sy * 0.9, sz, MAT.load, x, y, 0.3 + sz / 2);
      if (key === 'SC') for (let i = 0; i < 4; i++) box(eg, sx * 0.95, sy * 0.95, 0.06, MAT.steel, x, y, 0.3 + sz * (i + 1) / 5);
    } else if (n.kind === 'earthing') {
      box(eg, 0.4, 0.4, 1.2, MAT.steel, x, y, 0.6); porcelain(eg, 0.12, 0.6, x, y, 1.2);
    }
  }
  // 鉄構・鉄塔・避雷器（structures）
  for (const st of site.layout.structures || []) {
    const sg = new THREE.Group(); g.add(sg);
    if (st.kind === 'gantry') {
      const cols = st.primitives.slice(0, -1), beam = st.primitives[st.primitives.length - 1];
      for (const c of cols) latticeColumn(sg, c.a[0], c.a[1], c.b[2], dims.gantry.col_w);
      latticeBeam(sg, beam.a, beam.b, dims.gantry.beam_h);
    } else if (st.id.startsWith('220-TOWER')) {
      const a = st.primitives[0].a, h = st.primitives[0].b[2]; const tw = dims.tower_220;
      const m = new THREE.Mesh(new THREE.CylinderGeometry(tw.top_w / 2, tw.base_w / 2, h, 4, 1, true), new THREE.MeshBasicMaterial({ color: 0x93a0b0, wireframe: true })); m.rotation.x = Math.PI / 2; m.rotation.y = Math.PI / 4; m.position.set(a[0], a[1], h / 2); sg.add(m);
      for (let i = 1; i < h / 3; i++) { const z = i * 3, w = tw.base_w / 2 + (tw.top_w / 2 - tw.base_w / 2) * z / h; const r = new THREE.Mesh(new THREE.RingGeometry(w * 0.98, w, 4), new THREE.MeshBasicMaterial({ color: 0x93a0b0, side: THREE.DoubleSide })); r.rotation.z = Math.PI / 4; r.position.set(a[0], a[1], z); sg.add(r); }
    } else if (st.kind === 'arrester') {
      for (const pr of st.primitives) { const kv = pr.b[2] > 2.5 ? 220 : 66; const e = dims.equip[String(kv)].la; box(sg, e.base, e.base, 0.3, MAT.concrete, pr.a[0], pr.a[1], 0.15); box(sg, 0.2, 0.2, e.column - 0.3, MAT.steel, pr.a[0], pr.a[1], 0.3 + (e.column - 0.3) / 2); porcelain(sg, e.d / 2 + 0.06, e.porcelain, pr.a[0], pr.a[1], e.column, MAT.porcelainBrown); }
    } else if (st.kind === 'ground_wire') {
      for (const pr of st.primitives) cylAlong(sg, pr.a, pr.b, 0.03, MAT.steelDark, 6);
    }
  }
  return { group: g, byId };
}

// 導体をカプセル（細い円柱）で。状態で色を変えられるよう ID ごとにまとめる
export function buildConductors(site) {
  const g = new THREE.Group(); const byId = {};
  for (const it of site.layout.items) {
    if (!it.primitives.length) continue;
    const mat = new THREE.MeshStandardMaterial({ color: 0xff4d4d, emissive: 0x330000, roughness: 0.4, metalness: 0.6 });
    const eg = new THREE.Group(); byId[it.id] = { group: eg, mat };
    for (const p of it.primitives) cylAlong(eg, p.a, p.b, Math.max(p.r, 0.035), mat, 8);
    g.add(eg);
  }
  return { group: g, byId };
}
