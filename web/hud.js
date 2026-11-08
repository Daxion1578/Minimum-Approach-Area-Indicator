// HUD の殻（案2「3D を全面に、操作を浮かべる」）。段ごとの中身は hud-s0〜s3.js の provider が返し、殻は枠に置くだけ。
// 計算はしない（engine/ の結果を window.maai から読む）。幅 699px 以下では何もしない（今までの 1 列の表示のまま）。
//
// provider（default export）の形は HUD-CONTRACT の通り:
//   id, caption, title, goals(m), side(m), answer(m), bar(m), modes(m), nextLabel(m), onNext(m), nextDisabled(m),
//   hints(m), card(m), bind(root, m), onKey(e, m), onEnter(m), onLeave(m)
// 任意: onMode(name, m)（切り替えが変わったとき）、expandSld(on, m)（s1 の結線図の全面／小窓）。
// card(m) は {x,y,z,html} に加えて away:[x,y,z]（カードで隠したくない 3D の点）を返してよい。
// 板の色: answer() の先頭要素の data-verdict="ok|cond|ng|none" → #hudAnswer の右辺。side() の先頭要素の data-tone="claude|act|ok|cond|ng" → #hudSide の上辺。
import s0 from './hud-s0.js';
import s1 from './hud-s1.js';
import s2 from './hud-s2.js';
import s3 from './hud-s3.js';

const P = { s0, s1, s2, s3 }, ORDER = ['s0', 's1', 's2', 's3'];
const $ = id => document.getElementById(id);
const m = () => window.maai;
const curId = () => document.querySelector('.step.on')?.id || 's0';
const cur = () => P[curId()] || s0;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
function safe(where, fn, fallback) { try { return fn(); } catch (e) { console.warn('[hud] ' + where, e); return fallback; } }

let on = false, root = null, drawer = null, stage = null;
const modes = { s2: 'move' };          // 段ごとの切り替え（s1 は既存の input[name=sldMode] を正とする）
const prevHtml = new WeakMap();          // 前回と同じ HTML なら書き直さない（押している途中のボタンを壊さない）
function setHtml(el, html) { if (prevHtml.get(el) === html) return false; prevHtml.set(el, html); el.innerHTML = html; return true; }

// ------------------------------------------------------------ 枠を作る・既存の要素を移す
const moved = [];
function move(el, to) { if (!el) return; moved.push([el, el.parentNode, el.nextSibling]); to.appendChild(el); }
function restore() { for (const [el, parent, next] of moved.reverse()) parent.insertBefore(el, next); moved.length = 0; }

function build() {
  root = document.createElement('div'); root.id = 'hudRoot';
  root.innerHTML = `
    <div id="hudTitle"><div class="k"></div><div class="t"></div><div class="seg"></div></div>
    <div id="hudLeft"><div id="hudGoals"><div class="k">目標</div><div class="list"></div></div><div id="hudSide" class="plate" hidden></div></div>
    <div id="hudTop"></div>
    <div id="hudRight"><div id="hudAnswer" class="plate" hidden></div><div id="hudLegend"></div><button class="sub" id="hudDetail" aria-pressed="false">詳しく</button></div>
    <div id="hudCam"></div>
    <div id="hudHints"></div>
    <div id="hudBar"></div>
    <div id="hudModes"><div class="modes"></div><button id="hudNext">次へ</button></div>
    <svg id="hudCardLine" aria-hidden="true"><line x1="0" y1="0" x2="0" y2="0"/><rect width="8" height="8"/></svg>
    <div id="hudCard" class="plate"></div>`;
  document.body.appendChild(root);
  drawer = document.createElement('aside'); drawer.id = 'hudDrawer'; drawer.setAttribute('aria-label', '詳しく');
  drawer.innerHTML = `<div class="dhead"><b></b><span>根拠と入力</span><button class="sub" id="hudDrawerClose">閉じる<kbd>Esc</kbd></button></div><div class="dbody"></div>`;
  document.body.appendChild(drawer);
  // 殻が持つボタン（段の provider は data-act などで自分のボタンを bind する）
  root.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.closest('#hudTitle') && b.dataset.goto) return window.go(b.dataset.goto);
    if (b.id === 'hudDetail') return toggleDrawer();
    if (b.classList.contains('mode') && b.dataset.mode) return setMode(b.dataset.mode);
  });
  $('hudDrawerClose').onclick = closeDrawer;
  $('wOwn')?.addEventListener('click', openDrawer);   // 初回の案内「自分の図面を読み込む」→ 取込の入力が見えるように
  $('btnJson')?.addEventListener('click', () => { if (document.body.classList.contains('json')) openDrawer(); });   // 内部データは引き出しの下に出る
  drawer.addEventListener('focusin', () => { if (on && !document.body.classList.contains('drawer-open')) openDrawer(); });   // Tab で中に入ったら開く
}

function mount() {
  if (on) return;
  if (!root) build();
  move($('left'), drawer.querySelector('.dbody'));
  move($('right'), drawer.querySelector('.dbody'));
  move($('viewBtns'), $('hudCam'));
  move(document.querySelector('header .hbtns'), $('hudTop'));
  move($('btnTour'), $('hudTop'));
  document.body.classList.add('hud'); on = true;
  stage = null; enter(curId()); render();
}
function unmount() {
  if (!on) return;
  document.body.classList.remove('hud', 'drawer-open'); restore(); on = false;
  delete document.body.dataset.stage; delete document.body.dataset.mode;
}

// ------------------------------------------------------------ 段の出入り
function enter(id) {
  if (id === stage) return;
  const prev = P[stage]; stage = id;
  if (prev) safe('onLeave', () => prev.onLeave?.(m()));
  document.body.dataset.stage = id; document.body.dataset.mode = getMode();
  safe('onEnter', () => P[id]?.onEnter?.(m()));
}

// ------------------------------------------------------------ 描き直し（枠ごとに try/catch。一つが失敗しても他は描く）
let pend = false;
function schedule() { if (pend || !on) return; pend = true; requestAnimationFrame(() => { pend = false; render(); }); }

function render() {
  if (!on) return;
  const M = m(); if (!M) return;
  const p = cur(), open = document.body.classList.contains('drawer-open');
  // 見出しと 4 本の横棒（済は進行バーの .done と同じ判断。onboarding.js が付ける）
  safe('title', () => {
    $('hudTitle').querySelector('.k').textContent = `MAAI · ${p.caption}`;
    $('hudTitle').querySelector('.t').textContent = p.title;
    const done = id => !!document.querySelector(`#prog [data-goto="${id}"].done`);
    setHtml($('hudTitle').querySelector('.seg'), ORDER.map(id =>
      `<button data-goto="${id}" class="${id === p.id ? 'now' : done(id) ? 'done' : ''}" title="${esc(P[id].short || P[id].title)}" aria-label="${esc(P[id].short || P[id].title)}"></button>`).join(''));
    drawer.querySelector('.dhead b').textContent = p.title;
  });
  safe('goals', () => {
    const gs = p.goals(M) || [];
    setHtml($('hudGoals').querySelector('.list'), gs.map(g => `<div class="goal${g.done ? ' done' : ''}${g.now ? ' now' : ''}">${g.text}</div>`).join(''));
    $('hudGoals').hidden = !gs.length;
  });
  safe('side', () => {
    const el = $('hudSide'), h = p.side(M) || '';
    setHtml(el, h); el.hidden = !h; el.dataset.tone = el.firstElementChild?.dataset.tone || '';
  });
  safe('answer', () => {
    const el = $('hudAnswer'), h = p.answer(M) || '';
    setHtml(el, h); el.hidden = !h; el.dataset.verdict = el.firstElementChild?.dataset.verdict || 'none';
  });
  safe('legend', () => setHtml($('hudLegend'), legendHtml(M)));
  safe('detail', () => { const b = $('hudDetail'); b.setAttribute('aria-pressed', String(open)); b.innerHTML = open ? '引き出しを閉じる<kbd>Esc</kbd>' : '詳しく'; });
  safe('bar', () => setHtml($('hudBar'), p.bar(M) || ''));
  safe('modes', () => {
    const el = $('hudModes').querySelector('.modes'); setHtml(el, p.modes(M) || '');
    const mode = getMode(); el.querySelectorAll('.mode').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.mode === mode)));
  });
  safe('next', () => {
    const b = $('hudNext'); b.textContent = p.nextLabel(M); b.disabled = !!p.nextDisabled?.(M);
    b.onclick = () => safe('onNext', () => p.onNext(M));
  });
  safe('hints', () => setHtml($('hudHints'), (p.hints(M) || []).map(h => `<span>${h.key ? `<kbd>${esc(h.key)}</kbd>` : ''}${h.text}</span>`).join('')));
  safe('bind', () => p.bind?.(root, M));
}

// 充電／停電の数（index.html の paint() が lastCounts に残す）と 3D の元
function legendHtml(M) {
  const c = M.lastCounts; if (!c) return '';
  const draft = M.site?.layout_source === 'drawing-draft';
  return `<span><i style="background:var(--live)"></i>充電 <b class="n">${c.live}</b></span><span><i style="background:var(--deadg)"></i>停電 <b class="n">${c.dead}</b></span>`
    + (c.invalid ? `<span style="color:var(--invalid)"><i style="background:var(--invalid)"></i>充電部に接地 <b class="n">${c.invalid}</b></span>` : '')
    + `<span class="dim">近づけない範囲 <span class="n">${c.env}</span> 本 · 3D の元: ${draft ? '<span style="color:var(--deadu)">図面から起こした配置（承認前）</span>' : '合成データ'}</span>`;
}

// ------------------------------------------------------------ 3D 上のカード: 毎フレーム provider.card(m) の 3D 座標を画面座標へ
let lastCard = '';
function hideCard() { $('hudCard').classList.remove('on'); $('hudCardLine').classList.remove('on'); }
function placeCard() {
  const M = m(), card = $('hudCard'), svg = $('hudCardLine');
  const c = M && safe('card', () => cur().card?.(M), null);
  if (!c || document.querySelector('#sldView.on:not(.sld-mini)')) return hideCard();
  if (c.html !== lastCard) { lastCard = c.html; card.innerHTML = c.html; safe('bind', () => cur().bind?.(card, M)); }
  const v = new M.THREE.Vector3(c.x, c.y, c.z ?? 0).project(M.camera);
  if (v.z > 1 || Math.abs(v.x) > 1.3 || Math.abs(v.y) > 1.3) return hideCard();   // 後ろ・画面外
  const r = M.renderer.domElement.getBoundingClientRect();
  const sx = r.left + (v.x + 1) / 2 * r.width, sy = r.top + (1 - v.y) / 2 * r.height;
  const W = innerWidth, H = innerHeight, w = card.offsetWidth || 340, h = card.offsetHeight || 120, gap = 36;
  // 空いている所（左の目標・右の答え・下のバーを避ける）に置く。候補は点の上（左右）→ 点の下（左右）の順。
  // c.away（3D 座標。クレーンならブームの先）があれば、その画面上の点と反対の側を先に試す（対象を隠さない）
  const free = { l: document.body.classList.contains('drawer-open') ? 440 : 380, r: W - 400, t: 60, b: H - 150 };
  let leftFirst = false;
  if (c.away) { const a = new M.THREE.Vector3(...c.away).project(M.camera); leftFirst = (a.x + 1) / 2 * r.width + r.left > sx; }
  const L = sx - gap - w, R = sx + gap, U = sy - gap - h, D = sy + gap;
  const cands = leftFirst ? [[L, U], [R, U], [L, D], [R, D]] : [[R, U], [L, U], [R, D], [L, D]];
  let [x, y] = cands.find(([px, py]) => px >= free.l && px + w <= free.r && py >= free.t && py + h <= free.b) || cands[0];
  x = Math.min(Math.max(x, free.l), Math.max(free.l, free.r - w)); y = Math.min(Math.max(y, free.t), Math.max(free.t, free.b - h));
  card.style.transform = `translate(${x.toFixed(0)}px,${y.toFixed(0)}px)`; card.classList.add('on');
  // 線は対象の点からカードの一番近い所へ。点には小さな菱形
  const ex = Math.max(x, Math.min(sx, x + w)), ey = Math.max(y, Math.min(sy, y + h));
  const line = svg.querySelector('line'), rect = svg.querySelector('rect');
  line.setAttribute('x1', sx); line.setAttribute('y1', sy); line.setAttribute('x2', ex); line.setAttribute('y2', ey);
  rect.setAttribute('transform', `translate(${sx} ${sy}) rotate(45) translate(-4 -4)`); svg.classList.add('on');
}
(function loop() { requestAnimationFrame(loop); if (on) safe('card', placeCard); })();

// ------------------------------------------------------------ 引き出し・切り替え・公開 API
function openDrawer() { if (!on) return; document.body.classList.add('drawer-open'); render(); }
function closeDrawer() { document.body.classList.remove('drawer-open'); render(); }
function toggleDrawer() { document.body.classList.contains('drawer-open') ? closeDrawer() : openDrawer(); }
function getMode() {
  const id = curId();
  if (id === 's1') return document.querySelector('input[name=sldMode]:checked')?.value || 'toggle';
  return modes[id] || 'move';
}
function setMode(name) {
  const id = curId();
  if (id === 's1') { const r = document.querySelector(`input[name=sldMode][value="${name}"]`); if (r && !r.checked) { r.checked = true; r.dispatchEvent(new Event('change', { bubbles: true })); } }
  modes[id] = name; document.body.dataset.mode = name;
  safe('onMode', () => P[id]?.onMode?.(name, m()));
  render();
}
function expandSld(onOff) { return safe('expandSld', () => P.s1.expandSld?.(onOff, m())); }
// 今表示中の範囲（maai.zoneCells）の ok なます目の i 番目にクレーンを移す（録画スクリプトが使う）
function placeAtCell(i) {
  if (curId() === 's2' && P.s2.placeAtCell) return P.s2.placeAtCell(i, m());   // s2 の段: その位置で級も選び直す（select_at）
  const M = m(), cell = (M.zoneCells || []).filter(c => c.ok)[i]; if (!cell) return null;
  M.craneToForm(cell.crane); return M.evaluateClearance();
}
function rotate(deg) {
  if (curId() === 's2' && P.s2.rotate && m().lastCrane) return P.s2.rotate(deg, m());   // s2 の段: 向きを変えて級も選び直す（select_at）
  const el = $('chead'); el.value = Math.round((((+el.value + deg) % 360) + 360) % 360 * 10) / 10;
  return m().evaluateClearance();
}
window.hud = { openDrawer, closeDrawer, toggleDrawer, render, setMode, getMode, expandSld, placeAtCell, rotate, get on() { return on; } };

// ------------------------------------------------------------ キーは殻が 1 か所で受ける（入力欄にいるときは渡さない）
document.addEventListener('keydown', e => {
  if (!on) return;
  if (e.key === 'Escape') {            // Esc だけは入力欄の中からも効く
    if (document.body.classList.contains('drawer-open')) { closeDrawer(); document.activeElement?.blur?.(); e.preventDefault(); return; }
    if (curId() === 's1' && P.s1.expandSld) { expandSld(false); return; }
  }
  if (e.target?.matches?.('input,textarea,select,[contenteditable]')) return;
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  if (safe('onKey', () => cur().onKey?.(e, m()), false)) e.preventDefault();
});

// ------------------------------------------------------------ 起動: 幅 700px 以上のときだけ。段の移動と結果の更新で描き直す
addEventListener('maai-go', () => { if (!on) return; enter(curId()); schedule(); });
addEventListener('maai-update', schedule);
const mq = matchMedia('(min-width:700px)');
mq.addEventListener('change', e => e.matches ? mount() : unmount());
if (mq.matches) mount();
