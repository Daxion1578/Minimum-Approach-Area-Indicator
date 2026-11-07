// 停止範囲の段（STEP 02）。殻（hud.js）に枠の中身を返すだけ。停止範囲・充電／停電の判定は engine/ の結果
// （window.maai の lastSteps / lastCounts / lastIntake）を読む。操作は既存の要素（#btnSteps, #btnIntakeUse, #showEnv,
// input[name=sldMode], 結線図の .mk）を押して動かす。
// 結線図（#sldView）は段にいる間ずっと出しておき、右上の小窓（.sld-mini、見るだけ）と全面（.sld-full、押せる）を切り替える。
//   小窓 = view3d が真（3D を見ている）、全面 = view3d が偽。view3d は index.html の #btnViewToggle の元の処理でだけ変える。
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const KIND = { breaker: '遮断器', disconnector: '断路器', transformer: '変圧器', bus: '母線', load: '調相設備' };
const DIR = { east: '東', west: '西', north: '北', south: '南' };
const hud = () => window.hud;
const inS1 = () => !!window.hud?.on && document.querySelector('.step.on')?.id === 's1';

let full = false;            // 今の結線図: 全面か小窓か（段の外では意味を持たない）
let usedIntake = null;       // 「この内容で入れる」を押した依頼文の応答（lastIntake と同じなら入れ済み）
addEventListener('maai-update', e => { if (e.detail?.kind === 'intake-used') usedIntake = window.maai?.lastIntake; });

// ---- 読むだけの小さな関数
const node = (m, id) => m.site?.topology.nodes.find(n => n.id === id);
const num = (m, id) => node(m, id)?.number || id;
function label(m, id) {            // 番号のあとに付ける説明（名前が ID と同じなら電圧・回線・種類から）
  const n = node(m, id); if (!n) return '';
  if (n.name && n.name !== n.id) return n.name;
  return [n.voltage_kv ? `${n.voltage_kv}kV` : '', n.bay || '', KIND[n.kind] || n.kind].filter(Boolean).join(' ');
}

// ---- 結線図の小窓／全面（表示の切り替えだけ）
function viewToggleOrig() { const b = $('btnViewToggle'); b?.onclick?.call(b); }   // 元の処理: view3d を反転して showSld(!view3d)
function apply(m, wantFull) {
  const v = $('sldView'); if (!v || !m) return;
  install(m);
  full = !!wantFull;
  if (m.view3d !== !full) viewToggleOrig();
  if (!v.classList.contains('on')) m.showSld(true);          // .on のときだけ refreshSld が SVG を取りに行く
  v.classList.add('on'); v.classList.toggle('sld-mini', !full); v.classList.toggle('sld-full', full);
  $('viewBtns').style.display = full ? 'none' : 'flex';      // 小窓のときは 3D の視点ボタンを出す
  $('hud').style.display = full ? 'none' : 'block';
  $('btnViewToggle').textContent = full ? '3D を見る' : '結線図を見る';
  if (full) requestAnimationFrame(scrollToTarget);           // 小窓で幅 100% にしていた分、対象の位置へ戻す
  hud()?.render();
}
function stow(m) {                                           // 段を出る: showSld(false) と同じ状態に
  const v = $('sldView'); if (!v) return;
  v.classList.remove('sld-mini', 'sld-full');
  if (v.classList.contains('on')) m?.showSld(false);
  $('viewBtns').style.display = 'flex'; $('hud').style.display = 'block';
}
function scrollToTarget() {
  const el = $('sldWrap')?.querySelector('.mk.tgt'), sc = $('sldScroll'); if (!el || !sc) return;
  sc.scrollTo({ left: el.offsetLeft - sc.clientWidth / 2, top: el.offsetTop - sc.clientHeight / 2 });
}

// ---- 一度だけ結ぶもの: 小窓の見出し・「3D に戻る」、小窓を押すと全面、#btnViewToggle の横取り、3D で機器を押す
let installed = false;
function install(m) {
  if (installed || !$('sldView')) return; installed = true;
  const v = $('sldView');
  v.insertAdjacentHTML('beforeend', `<div id="sldMiniCap"><span>単線結線図 · 押すと大きく</span><kbd>TAB</kbd></div>`
    + `<button class="sub" id="sldClose" title="結線図を小窓に戻して 3D を見る">← 3D に戻る<kbd>TAB</kbd></button>`);
  $('sldClose').onclick = () => apply(window.maai, false);
  v.addEventListener('click', e => {                         // 小窓は見るだけ。押すと全面
    if (!v.classList.contains('sld-mini') || !inS1()) return;
    e.stopPropagation(); e.preventDefault(); apply(window.maai, true);
  }, true);
  document.addEventListener('click', e => {                  // record.py と onboarding が押す: HUD の s1 では全面⇄小窓
    if (!e.target.closest?.('#btnViewToggle') || !inS1()) return;
    e.stopImmediatePropagation(); e.preventDefault(); apply(window.maai, !full);
  }, true);
  document.querySelectorAll('input[name=sldMode]').forEach(r => r.addEventListener('change', () => hud()?.render()));
  installPick(m);
}

// 3D の機器を押す = 結線図の同じ機器（.mk）を押す（取り替える機器に選ぶ／開閉器を入・切は結線図と同じ処理）
function installPick(m) {
  const dom = m?.renderer?.domElement; if (!dom) return;
  let down = null;
  dom.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
  dom.addEventListener('pointerup', e => {
    if (!down || e.button !== 0 || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4 || !inS1() || full) return;
    const M = window.maai, r = dom.getBoundingClientRect(), marks = $('sldWrap')?.querySelectorAll('.mk[data-id]');
    if (!marks?.length || !M.site) return;
    const ids = new Set([...marks].map(x => x.dataset.id));
    let best = null, bd = 24;                                  // 画面上で 24px 以内の一番近い機器
    for (const it of M.site.layout.items) {
      if (!it.at || !ids.has(it.id)) continue;
      const p = new M.THREE.Vector3(it.at[0], it.at[1], it.at[2] || 0).project(M.camera);
      if (p.z > 1) continue;
      const d = Math.hypot(r.left + (p.x + 1) / 2 * r.width - e.clientX, r.top + (1 - p.y) / 2 * r.height - e.clientY);
      if (d < bd) { bd = d; best = it.id; }
    }
    // .click() だと小窓の「押すと全面」に捕まるので、.mk の処理を直接呼ぶ
    if (best) { const mk = $('sldWrap').querySelector(`.mk[data-id="${CSS.escape(best)}"]`); mk?.onclick?.call(mk); }
  });
}

// ---- 枠の中身
export default {
  id: 's1', caption: 'STEP 02', title: '停止範囲',

  goals(m) {
    const st = m.lastSteps, t = st?.targets?.[0];
    return [
      { text: `取り替える機器を選ぶ${t ? ` <b>${esc(num(m, t))}</b>` : ''}`, done: !!st, now: !st },
      { text: '赤（充電）と緑（停電）を確かめる', now: !!st },
    ];
  },

  side(m) {
    const j = m.lastIntake, c = j?.checked;
    if (!c) {
      return `<div class="s1in" data-tone="act"><div class="hd"><span class="ttl">依頼文</span></div>
        <div class="lead">${j ? `読み取りに失敗: ${esc(j.detail || '')}` : '工事の依頼文から、取り替える機器・止められない設備・資材置場・重さを読み取れる'}</div>
        <button class="sub" data-act="intake">依頼文を読む</button></div>`;
    }
    const e = j.extracted || {}, L = id => esc(c.labels?.[id] || m.nameOf?.(id) || id);
    const list = a => a?.length ? a.map(L).join('、') : '—';
    const lay = e.laydown?.dist_m != null ? `${DIR[e.laydown.dir] || esc(e.laydown.dir)}へ <b class="n">${esc(e.laydown.dist_m)}</b> m`
      : c.laydown_xy ? `<b class="n">${c.laydown_xy.join(', ')}</b>` : '—';
    const used = usedIntake === j;
    return `<div class="s1in" data-tone="claude">
      <div class="hd"><span class="ttl">依頼文から読み取った</span><span class="src">${e.source === 'claude' ? 'CLAUDE' : '規則'}</span></div>
      <div class="g2">
        <div><span>取り替え</span><b>${list(c.targets)}</b></div>
        <div><span>止められない</span><b>${list(c.unstoppable)}</b></div>
        <div><span>資材置場</span><b>${lay}</b></div>
        <div><span>重さ</span><b>${c.weight_t != null ? `<b class="n">${esc(c.weight_t)}</b> t` : '—'}</b></div>
      </div>
      ${c.problems?.length ? `<div class="warn1">${esc(c.problems[0])}${c.problems.length > 1 ? `（ほか ${c.problems.length - 1}）` : ''}</div>` : ''}
      ${used ? `<div class="okline">入れた。停止範囲を確かめ、重機へ</div>`
        : `<button class="sub" data-act="intakeUse"${c.ok ? '' : ' disabled'}>この内容で入れる</button>`}
    </div>`;
  },

  answer(m) {
    const st = m.lastSteps;
    if (!st) return `<div class="ans" data-verdict="none"><div class="lead">結線図で取り替える機器を選ぶと、止める範囲が決まって 3D の赤と緑が切り替わる</div><button class="act" data-act="steps">停止範囲を作る</button></div>`;
    const v = st.ok ? 'ok' : 'ng', ops = st.ops || [], MAX = 8;
    const tags = ops.slice(0, MAX).map(o => `<span class="tag">${esc(o.number || o.id)}</span>`).join('')
      + (ops.length > MAX ? `<span class="tag more">ほか ${ops.length - MAX}</span>` : '');
    const cs = st.conditions || [];
    return `<div class="ans s1ans" data-verdict="${v}">
      <div class="row1"><span class="v ${v}">${st.ok ? '停電にできる' : '停電にできない'}</span><span class="nops">切る開閉器 <b class="n">${ops.length}</b></span></div>
      ${st.ok ? '' : `<div class="lead">${esc((st.problems || []).join('。') || '理由は引き出しで確かめる')}</div>`}
      ${ops.length ? `<div class="tags">${tags}</div>` : ''}
      ${cs.length ? `<div class="cond">条件: ${esc(cs[0])}${cs.length > 1 ? `（ほか ${cs.length - 1}）` : ''}</div>` : ''}
    </div>`;
  },

  bar(m) {
    const c = m.lastCounts, env = !!$('showEnv')?.checked;
    const n = v => `<span class="n">${c ? v : '—'}</span>`;
    return `<div class="tile s1cnt live" title="充電している機器・区間の数（engine の判定）"><i></i>${n(c?.live)}<small>充電</small></div>`
      + `<div class="tile s1cnt dead" title="停電している機器・区間の数（engine の判定）"><i></i>${n(c?.dead)}<small>停電</small></div>`
      + `<span class="sep"></span>`
      + `<button class="tile" data-act="env" aria-pressed="${env}" title="近づけない範囲（包絡）を 3D に出す・消す"><span class="envmk"></span><small>近づけない範囲</small></button>`;
  },

  modes() {
    return `<button class="mode" data-mode="target"><span>取り替える機器を選ぶ</span><kbd>Q</kbd></button>
      <button class="mode" data-mode="toggle"><span>開閉器を入・切</span><kbd>W</kbd></button>`;
  },
  nextLabel() { return '次へ: 重機 →'; },
  onNext() { window.go('s2'); },
  nextDisabled(m) { return !m.lastSteps; },

  hints() {
    const click = hud()?.getMode() === 'target' ? '機器を選ぶ' : '開閉器を入・切';
    return [{ key: '左クリック', text: click }, { key: 'ドラッグ', text: '見回す' }, { key: 'TAB', text: full ? '3D に戻る' : '結線図を大きく' }];
  },

  // 3D 上のカード: 取り替える機器（layout.items の at）
  card(m) {
    const st = m.lastSteps, t = st?.targets?.[0]; if (!t || !m.site) return null;
    const it = m.site.layout.items.find(i => i.id === t && i.at) || m.site.layout.items.find(i => i.at && i.id.includes(t)); if (!it) return null;
    // away: 画面の右（カメラの右向き）の点。殻はその反対の左側を先に試すので、右上の結線図の小窓と重なりにくい
    const right = new m.THREE.Vector3().setFromMatrixColumn(m.camera.matrixWorld, 0).multiplyScalar(5);
    return { x: it.at[0], y: it.at[1], z: it.at[2] || 0, away: [it.at[0] + right.x, it.at[1] + right.y, (it.at[2] || 0) + right.z], html: `<div class="s1card">
      <div class="head"><span class="n num">${esc(num(m, t))}</span><span class="nm">${esc(label(m, t))}</span></div>
      <div class="st ${st.ok ? 'ok' : 'ng'}">取り替え対象 · ${st.ok ? '停電' : '停電にできない'}</div>
    </div>` };
  },

  bind(root, m) { root.querySelectorAll('[data-act]').forEach(b => { b.onclick = () => act(b.dataset, m); }); },

  onKey(e, m) {
    if (e.key === 'Tab' && !e.shiftKey) { apply(m, !full); return true; }
    const k = e.key.toLowerCase();
    if (k === 'q') { hud().setMode('target'); return true; }
    if (k === 'w') { hud().setMode('toggle'); return true; }
    return false;
  },
  expandSld(on, m) { if (inS1()) apply(m, !!on); return inS1(); },
  onEnter(m) { apply(m, false); },
  onLeave(m) { full = false; stow(m); },
};

// ---- ボタンの動作: 既存の要素を押すか、殻の API を呼ぶだけ
function act(d, m) {
  if (d.act === 'steps') $('btnSteps').click();
  else if (d.act === 'intakeUse') $('btnIntakeUse')?.click();
  else if (d.act === 'env') { const cb = $('showEnv'); cb.checked = !cb.checked; cb.dispatchEvent(new Event('change')); hud().render(); }
  else if (d.act === 'intake') {
    hud().openDrawer(); const t = $('reqText');
    t?.scrollIntoView({ block: 'center' }); t?.focus();
  }
}
