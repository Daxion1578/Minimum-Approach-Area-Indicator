// 対象を選ぶ段（STEP 1）。殻（hud.js）に枠の中身を返すだけ。停止範囲・充電／停電の判定は engine/ の結果
// （window.maai の lastSteps / lastCounts と、update() が #jEnerg に書く energization）を読む。
// 操作は既存の要素（#btnSteps, input[name=sldMode], 結線図の .mk, #btnViewToggle, #reqText）を押して動かす。
//
// 表示は 2 つ:
//   左右 2 分割（既定）: 左 = 単線結線図（#sldView.sld-split）、右 = 一般平面図（真上から見た 3D）。
//     3D の canvas は全面のまま。camera.setViewOffset で投影の中心を右半分の中央へずらし、注視点が右半分に来るようにする。
//   結線図を大きく（.sld-full）: 今までの全面の結線図。TAB・#btnViewToggle・window.hud.expandSld(true/false) で切り替え。
// どちらで押しても同じ処理: 平面図で機器を押す = 結線図の同じ機器の .mk を押す（.mk の onclick は index.html のまま）。
// 対応の表示: 片方で機器にマウスを乗せる／押すと、もう片方の同じ機器に目印（結線図は枠、平面図は輪と菱形）。機器の札で番号・名前・状態。
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const KIND = { breaker: '遮断器', disconnector: '断路器', earthing: '接地開閉器', transformer: '変圧器', bus: '母線', load: '調相設備' };
const SWITCH = new Set(['breaker', 'disconnector', 'earthing']);
const hud = () => window.hud;
const inS1 = () => !!window.hud?.on && document.querySelector('.step.on')?.id === 's1';

let full = false;              // 結線図を大きく（全面）か、左右 2 分割か（段の外では意味を持たない）
let hot = null, hotFrom = '';  // マウスを乗せている機器（どちら側で乗せたか: 'sld' | 'plan'）
let pinned = null;             // 最後に押した機器（札を出す）
let planFocus = 'site';        // 平面図の範囲: 'site' 構内全体 | 'target' 対象のまわり

// ---- 読むだけの小さな関数
const node = (m, id) => m.site?.topology.nodes.find(n => n.id === id);
const num = (m, id) => node(m, id)?.number || id;
function label(m, id) {            // 番号のあとに付ける説明（名前が ID と同じなら電圧・回線・種類から）
  const n = node(m, id); if (!n) return '';
  if (n.name && n.name !== n.id) return n.name;
  return [n.voltage_kv ? `${n.voltage_kv}kV` : '', n.bay || '', KIND[n.kind] || n.kind].filter(Boolean).join(' ');
}
const itemAt = (m, id) => m.site?.layout.items.find(i => i.id === id && i.at)?.at || null;
// 充電／停電: update() が #jEnerg に書いた engine の energization を読む（中身が変わったときだけ読み直す）
let energ = {}, energSrc = '';
function energOf(id) {
  const txt = $('jEnerg')?.textContent || '';
  if (txt !== energSrc) {
    energSrc = txt; energ = {};
    try { for (const c of JSON.parse(txt).components || []) { for (const n of c.nodes) energ[n] = c.state; for (const e of c.edges) energ[e] = c.state; } } catch { energ = {}; }
  }
  return energ[id] ?? energ[id + '.a'] ?? energ[id + '.hv'] ?? null;
}

// ---- 平面図（右半分）: 投影の中心を右半分へずらす
const splitOn = () => inS1() && !full && !!$('sldView')?.classList.contains('sld-split');
function applyOffset(m) {
  const cam = m?.camera, dom = m?.renderer?.domElement; if (!cam || !dom) return;
  const w = dom.clientWidth, h = dom.clientHeight;
  if (splitOn() && w && h) {
    const v = cam.view;
    if (!v || !v.enabled || v.fullWidth !== w || v.fullHeight !== h || v.offsetX !== -w / 4) cam.setViewOffset(w, h, -w / 4, 0, w, h);
  } else if (cam.view?.enabled && !inS1()) cam.clearViewOffset();
}
let siteBox = null;
function bbox(m) {
  if (siteBox?.site === m.site) return siteBox;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const it of m.site?.layout.items || []) for (const p of it.primitives || []) for (const q of [p.a, p.b]) {
    x0 = Math.min(x0, q[0]); x1 = Math.max(x1, q[0]); y0 = Math.min(y0, q[1]); y1 = Math.max(y1, q[1]);
  }
  return (siteBox = { site: m.site, x0, x1, y0, y1 });
}
// 真上（phi 1.5、北が上）。構内全体なら右半分に収まる距離、対象なら半径 55
function planView(m, animate = true) {
  const c = m?.controls, dom = m?.renderer?.domElement; if (!c || !dom || !m.site) return;
  const b = bbox(m); if (!isFinite(b.x0)) return;
  const t = planFocus === 'target' && m.lastSteps?.targets?.[0] ? itemAt(m, m.lastSteps.targets[0]) : null;
  const tanH = Math.tan((m.camera.fov / 2) * Math.PI / 180), H = dom.clientHeight || 900, Wh = (dom.clientWidth || 1440) / 2;
  // 上は答えの板、下は切替・次へに少し隠れるので、縦は 1.3 倍、横は 1.15 倍の余白を見込む
  const rFit = Math.max((b.y1 - b.y0) * 1.3 / (2 * tanH), (b.x1 - b.x0) * 1.15 / (2 * tanH * Wh / H));
  const tx = t ? t[0] : (b.x0 + b.x1) / 2, ty = t ? t[1] : (b.y0 + b.y1) / 2 - (b.y1 - b.y0) * 0.04, tr = t ? 55 : rFit;
  const tth = -Math.PI / 2, tph = 1.5;
  if (!animate) { c.target.set(tx, ty, 0); c.radius = tr; c.theta = tth; c.phi = tph; return; }
  const t0 = c.target.clone(), r0 = c.radius, ph0 = c.phi;
  let th0 = c.theta; while (th0 - tth > Math.PI) th0 -= 2 * Math.PI; while (th0 - tth < -Math.PI) th0 += 2 * Math.PI;
  let i = 0; const N = 18;
  (function tick() {
    i++; const k = i / N, e = 1 - Math.pow(1 - k, 3);
    c.target.set(t0.x + (tx - t0.x) * e, t0.y + (ty - t0.y) * e, 0); c.radius = r0 + (tr - r0) * e;
    c.theta = th0 + (tth - th0) * e; c.phi = ph0 + (tph - ph0) * e;
    if (i < N) requestAnimationFrame(tick);
  })();
}
// 3D の点 → 画面座標（後ろなら null）
function toScreen(m, at) {
  const r = m.renderer.domElement.getBoundingClientRect();
  const p = new m.THREE.Vector3(at[0], at[1], at[2] || 0).project(m.camera);
  if (p.z > 1) return null;
  return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height];
}
// 平面図で、画面の点から一番近い機器（結線図に .mk がある機器だけ。18px 以内）
function pickAt(m, x, y) {
  const marks = $('sldWrap')?.querySelectorAll('.mk[data-id]'); if (!marks?.length || !m.site) return null;
  const ids = new Set([...marks].map(e => e.dataset.id));
  let best = null, bd = 18;
  for (const it of m.site.layout.items) {
    if (!it.at || !ids.has(it.id)) continue;
    const s = toScreen(m, it.at); if (!s) continue;
    const d = Math.hypot(s[0] - x, s[1] - y);
    if (d < bd) { bd = d; best = it.id; }
  }
  return best;
}
const mkOf = id => id ? $('sldWrap')?.querySelector(`.mk[data-id="${CSS.escape(id)}"]`) : null;
// 結線図の .mk を押す（index.html の処理そのもの: 対象に選ぶ／開閉器を入・切）
function pressMk(id) { const mk = mkOf(id); if (!mk) return; pinned = id; mk.onclick?.call(mk); hud()?.render(); }

// ---- 札（機器の番号・名前・状態）
function tagHtml(m, id) {
  const n = node(m, id); if (!n) return '';
  const pos = SWITCH.has(n.kind) ? ((m.state?.switches?.[id] || 'closed') === 'open' ? '切' : '入') : '';
  const e = energOf(id), live = e === 'live', dead = !!e && !live && e !== 'invalid';
  const isT = m.lastSteps?.targets?.includes(id);
  return `<div class="hd"><b class="n">${esc(n.number || id)}</b><span>${esc(label(m, id))}</span></div>
    <div class="st">${pos ? `<span class="pos ${pos === '切' ? 'open' : 'closed'}">${pos}</span>` : `<span class="k">${esc(KIND[n.kind] || n.kind)}</span>`}${e ? `<span class="e ${live ? 'live' : dead ? 'dead' : 'inv'}">${live ? '充電' : dead ? '停電' : '充電部に接地'}</span>` : ''}${isT ? '<span class="t">取り替え対象</span>' : ''}</div>`;
}

// ---- 目印の重ね絵（固定位置。毎フレーム、結線図の .mk の位置と平面図の投影位置へ置く。描き直しは位置が変わったときだけ）
let ov = null;
function overlay() {
  if (ov) return ov;
  ov = document.createElement('div'); ov.id = 's1Link'; ov.setAttribute('aria-hidden', 'true');
  ov.innerHTML = `<div class="lk sld sel"></div><div class="lk sld hot"></div><div class="lk plan tgt"><i></i></div><div class="lk plan sel"><i></i></div><div class="lk plan hot"><i></i></div>
    <div class="lktag sld"></div><div class="lktag plan"></div>`;
  document.body.appendChild(ov);
  return ov;
}
function put(el, pt, dx = 0, dy = 0) {
  if (!pt) { el.classList.remove('on'); return; }
  const tr = `translate(${(pt[0] + dx).toFixed(0)}px,${(pt[1] + dy).toFixed(0)}px)`;
  if (el.style.transform !== tr) el.style.transform = tr; el.classList.add('on');
}
const tagKey = { sld: '', plan: '' };
function drawLinks() {
  const m = window.maai, o = overlay();
  const active = inS1() && !!m?.site && $('sldView')?.classList.contains('on') && !document.body.classList.contains('drawer-open');
  o.classList.toggle('on', active); if (!active) return;
  const sc = $('sldScroll').getBoundingClientRect(), sv = $('sldView').getBoundingClientRect(), plan = splitOn();
  const sel = pinned || m.lastSteps?.targets?.[0] || null, q = s => o.querySelector(s);
  const sldPt = id => {                                      // 結線図: .mk が見えている範囲にあるときだけ
    const mk = mkOf(id); if (!mk) return null;
    const r = mk.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
    return x > sc.left && x < sc.right && y > sc.top && y < sc.bottom ? [x, y] : null;
  };
  const planPt = id => {                                     // 平面図: 結線図より右にあるときだけ
    if (!plan || !id) return null; const at = itemAt(m, id); if (!at) return null;
    const s = toScreen(m, at); return s && s[0] > sv.right + 6 && s[0] < innerWidth && s[1] > 0 && s[1] < innerHeight ? s : null;
  };
  const h = hot && hot !== sel ? hot : null;
  const P = { hs: h && sldPt(h), hp: h && planPt(h), ss: sel && sldPt(sel), sp: sel && planPt(sel) };
  put(q('.lk.sld.hot'), P.hs); put(q('.lk.plan.hot'), P.hp); put(q('.lk.sld.sel'), P.ss); put(q('.lk.plan.sel'), P.sp);
  const tg = m.lastSteps?.targets?.[0];                       // 取り替える機器（結線図は .mk.tgt の青丸。平面図は青い輪）
  put(q('.lk.plan.tgt'), tg && tg !== sel ? planPt(tg) : null);
  // 札: 乗せている機器があればそれ、無ければ押した機器（まだ押していなければ取り替える機器）
  const tid = hot || sel;
  const pts = { sld: tid === h ? P.hs : P.ss, plan: tid === h ? P.hp : P.sp };
  for (const side of ['sld', 'plan']) {
    const el = q(`.lktag.${side}`), pt = tid ? pts[side] : null;
    if (!pt) { el.classList.remove('on'); continue; }
    const html = tagHtml(m, tid); if (tagKey[side] !== html) { tagKey[side] = html; el.innerHTML = html; }
    const w = el.offsetWidth || 180, lo = side === 'plan' ? sv.right + 8 : sv.left + 8, hi = (side === 'plan' ? innerWidth : sv.right) - w - 8;
    let x = pt[0] + 20; if (x > hi) x = pt[0] - 20 - w;
    put(el, [Math.max(lo, x), Math.max(sc.top + 4, pt[1] - 50)]);
  }
}
(function loop() { requestAnimationFrame(loop); try { applyOffset(window.maai); drawLinks(); } catch (e) { /* 次のフレームでやり直す */ } })();

// ---- 表示の切り替え（左右 2 分割 ⇄ 結線図を大きく）
function viewToggleOrig() { const b = $('btnViewToggle'); b?.onclick?.call(b); }   // 元の処理: view3d を反転して showSld(!view3d)
function apply(m, wantFull) {
  const v = $('sldView'); if (!v || !m) return;
  install(m);
  full = !!wantFull;
  if (m.view3d) viewToggleOrig();                              // どちらの表示でも結線図は出しておく（view3d は偽）
  if (!v.classList.contains('on')) m.showSld(true);            // .on のときだけ refreshSld が SVG を取りに行く
  // .sld-mini は殻（hud.css / hud.js）に「結線図が全面ではない」と伝えるために付ける（枠を隠させない）
  v.classList.toggle('sld-full', full); v.classList.toggle('sld-split', !full); v.classList.toggle('sld-mini', !full);
  applyOffset(m);
  requestAnimationFrame(() => { const id = pinned || m.lastSteps?.targets?.[0]; id ? revealMk(id, false) : scrollToTarget(); });
  hud()?.render();
}
function stow(m) {                                           // 段を出る: showSld(false) と同じ状態に
  const v = $('sldView'); if (!v) return;
  v.classList.remove('sld-mini', 'sld-full', 'sld-split');
  if (v.classList.contains('on')) m?.showSld(false);
  hot = null; pinned = null;
  if (m?.camera?.view?.enabled) m.camera.clearViewOffset();
}
function scrollToTarget() {
  const el = $('sldWrap')?.querySelector('.mk.tgt'), sc = $('sldScroll'); if (!sc) return;
  if (el) return sc.scrollTo({ left: el.offsetLeft - sc.clientWidth / 2, top: el.offsetTop - sc.clientHeight / 2 });
  // まだ選んでいない: 図の左上（表題欄）ではなく、機器が並ぶ所（押せる印の縦の中央値、左端）を見せる
  const ms = [...($('sldWrap')?.querySelectorAll('.mk') || [])]; if (!ms.length) return;
  const ys = ms.map(x => x.offsetTop).sort((a, b) => a - b), y = ys[Math.floor(ys.length / 2)];
  const x = Math.min(...ms.map(x => x.offsetLeft));
  sc.scrollTo({ left: Math.max(0, x - 120), top: Math.max(0, y - sc.clientHeight * 0.4) });
}
// 結線図の中の機器が見えていなければ、そこまでスクロールする（平面図で乗せて少し待ったとき・押したとき）
function revealMk(id, smooth = true) {
  const mk = mkOf(id), sc = $('sldScroll'); if (!mk || !sc) return;
  const r = mk.getBoundingClientRect(), s = sc.getBoundingClientRect(), pad = 60;
  if (r.left > s.left + pad && r.right < s.right - pad && r.top > s.top + pad && r.bottom < s.bottom - pad) return;
  sc.scrollTo({ left: mk.offsetLeft - sc.clientWidth / 2, top: mk.offsetTop - sc.clientHeight / 2, behavior: smooth ? 'smooth' : 'auto' });
}
// 結線図の中身が描き直されたとき（初回の読み込み）: まだ動かしていなければ機器の所へ
function watchSld() {
  const w = $('sldWrap'), sc = $('sldScroll'); if (!w || !sc) return;
  new MutationObserver(() => {
    if (inS1() && !w.querySelector('.mk.tgt') && sc.scrollTop === 0 && sc.scrollLeft === 0) requestAnimationFrame(scrollToTarget);
  }).observe(w, { childList: true });
}

// ---- 一度だけ結ぶもの: #btnViewToggle の横取り、モードの変化、結線図と平面図のマウス
let installed = false;
function install(m) {
  if (installed || !$('sldView')) return; installed = true;
  document.addEventListener('click', e => {                  // record.py と onboarding が押す: HUD の s1 では 2 分割⇄結線図を大きく
    if (!e.target.closest?.('#btnViewToggle') || !inS1()) return;
    e.stopImmediatePropagation(); e.preventDefault(); act({ act: 'view' }, window.maai);
  }, true);
  document.querySelectorAll('input[name=sldMode]').forEach(r => r.addEventListener('change', () => hud()?.render()));
  watchSld();
  // 結線図: 乗せた機器・押した機器を覚える（押したときの処理は .mk の onclick のまま）
  const w = $('sldWrap');
  w.addEventListener('mouseover', e => { const mk = e.target.closest?.('.mk[data-id]'); if (mk) { hot = mk.dataset.id; hotFrom = 'sld'; } });
  w.addEventListener('mouseout', e => { const mk = e.target.closest?.('.mk[data-id]'); if (mk && !mk.contains(e.relatedTarget) && hotFrom === 'sld') hot = null; });
  w.addEventListener('click', e => { const mk = e.target.closest?.('.mk[data-id]'); if (mk && inS1()) { pinned = mk.dataset.id; setTimeout(() => hud()?.render(), 0); } }, true);
  installPlan(m);
  addEventListener('resize', () => { if (splitOn()) { applyOffset(window.maai); planView(window.maai, false); } });
}

// 平面図: 乗せると結線図の同じ機器を光らせ、押すと結線図の同じ機器を押したのと同じ処理
function installPlan(m) {
  const dom = m?.renderer?.domElement; if (!dom) return;
  let down = null, dwell = 0;
  dom.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
  dom.addEventListener('pointermove', e => {
    if (!splitOn() || e.buttons) return;
    const id = pickAt(window.maai, e.clientX, e.clientY);
    dom.style.cursor = id ? 'pointer' : '';
    if (id === hot && hotFrom === 'plan') return;
    if (id) { hot = id; hotFrom = 'plan'; } else if (hotFrom === 'plan') hot = null;
    clearTimeout(dwell); if (id) dwell = setTimeout(() => { if (hot === id) revealMk(id); }, 350);
  });
  dom.addEventListener('pointerleave', () => { if (hotFrom === 'plan') hot = null; dom.style.cursor = ''; });
  dom.addEventListener('pointerup', e => {
    if (!down || e.button !== 0 || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4 || !splitOn()) return;
    const id = pickAt(window.maai, e.clientX, e.clientY);
    if (id) { pressMk(id); revealMk(id); }
  });
}

// ---- 枠の中身
export default {
  id: 's1', caption: 'STEP 1', title: '対象を選ぶ', short: '対象',

  goals(m) {
    const t = m.lastSteps?.targets?.[0];
    return [{ text: `結線図か平面図で、取り替える機器を押す${t ? ` <b>${esc(num(m, t))}</b>` : ''}`, done: !!t, now: !t }];
  },

  // 小さな道具: 押したときの動作の切替と「依頼文から入れる」（任意）
  side() {
    const mode = hud()?.getMode();
    return `<div class="s1tools"><div class="s1sw" role="group" aria-label="機器を押したとき">
        <span>押すと</span>
        <button data-act="mode" data-v="target" aria-pressed="${mode === 'target'}">取り替える機器に選ぶ<kbd>Q</kbd></button>
        <button data-act="mode" data-v="toggle" aria-pressed="${mode === 'toggle'}">開閉器を入・切<kbd>W</kbd></button>
      </div><button class="sub s1req" data-act="intake" title="工事の依頼文から対象を読み取る（任意。引き出しが開く）">依頼文から入れる</button></div>`;
  },

  answer(m) {
    const st = m.lastSteps; if (!st) return '';
    const ops = st.ops || [], MAX = 6, cs = st.conditions || [];
    if (!st.ok) return `<div class="ans s1ans" data-verdict="ng"><div class="row1"><span class="v ng">停止範囲を作れない</span></div>
      <div class="lead">${esc((st.problems || []).join('。') || '理由は「詳しく」で確かめる')}</div><div class="dim">別の機器を押すと選び直し</div></div>`;
    const tags = ops.slice(0, MAX).map(o => `<span class="tag">${esc(o.number || o.id)}</span>`).join('')
      + (ops.length > MAX ? `<span class="tag more">ほか ${ops.length - MAX}</span>` : '');
    return `<div class="ans s1ans" data-verdict="ok">
      <div class="row1"><span class="v ok">停止範囲ができた</span><span class="nops">切る開閉器 <b class="n">${ops.length}</b></span></div>
      ${ops.length ? `<div class="tags">${tags}</div>` : ''}
      ${cs.length ? `<div class="cond">条件: ${esc(cs[0])}${cs.length > 1 ? `（ほか ${cs.length - 1}）` : ''}</div>` : ''}
    </div>`;
  },

  bar() { return ''; },

  // 右下: 2 分割⇄結線図を大きく、平面図の範囲（data-mode を付けないので殻のモード切替には入らない）
  modes(m) {
    const pl = !full && m.lastSteps ? `<button class="mode s1view" data-act="plan"><span>${planFocus === 'site' ? '平面図: 対象に寄る' : '平面図: 構内全体'}</span><kbd>F</kbd></button>` : '';
    return pl + `<button class="mode s1view" data-act="view"><span>${full ? '平面図と並べる' : '結線図を大きく'}</span><kbd>TAB</kbd></button>`;
  },
  nextLabel() { return '次へ: 置場と重さ →'; },
  onNext() { window.go('s2'); },
  nextDisabled(m) { return !m.lastSteps; },

  hints() {
    return full ? [] : [{ key: '左クリック', text: hud()?.getMode() === 'target' ? '取り替える機器に選ぶ' : '開閉器を入・切' }, { key: 'ドラッグ', text: '見回す' }];
  },

  card() { return null; },   // 機器の札は s1 が自分で出す（結線図と平面図の両方）

  bind(root, m) { root.querySelectorAll('[data-act]').forEach(b => { b.onclick = () => act(b.dataset, m); }); },

  onKey(e, m) {
    if (e.key === 'Tab' && !e.shiftKey) { act({ act: 'view' }, m); return true; }
    const k = e.key.toLowerCase();
    if (k === 'q') { hud().setMode('target'); return true; }
    if (k === 'w') { hud().setMode('toggle'); return true; }
    if (k === 'f' && !full) { act({ act: 'plan' }, m); return true; }
    return false;
  },
  expandSld(on, m) { if (inS1()) { const was = full; apply(m, !!on); if (was && !on) planView(m, false); } return inS1(); },
  onEnter(m) {                                               // 入ったら: 押すと「取り替える機器に選ぶ」、左右 2 分割、平面図は構内全体
    const r = document.querySelector('input[name=sldMode][value="target"]');
    if (r && !r.checked) { r.checked = true; r.dispatchEvent(new Event('change', { bubbles: true })); }
    document.body.dataset.mode = 'target';
    planFocus = 'site';
    apply(m, false);
    planView(m);
  },
  onLeave(m) { full = false; stow(m); },
};

// ---- ボタンの動作: 既存の要素を押すか、殻の API を呼ぶだけ
function act(d, m) {
  if (d.act === 'view') { const was = full; apply(m, !full); if (was) planView(m, false); }
  else if (d.act === 'plan') { planFocus = planFocus === 'site' ? 'target' : 'site'; planView(m); hud()?.render(); }
  else if (d.act === 'mode') hud().setMode(d.v);
  else if (d.act === 'intake') {
    hud().openDrawer(); const t = $('reqText');
    t?.scrollIntoView({ block: 'center' }); t?.focus();
  }
}
