// 対象を選ぶ段（STEP 02）。殻（hud.js）に枠の中身を返すだけ。停止範囲・充電／停電の判定は engine/ の結果
// （window.maai の lastSteps / lastCounts）を読む。操作は既存の要素（#btnSteps, input[name=sldMode], 結線図の .mk,
// #btnViewToggle, #reqText）を押して動かす。
// 表示は 2 つだけ: 結線図の全面（.sld-full、既定。押して選ぶ）と 3D（結線図をしまう）。TAB・「3D で見る」・#btnViewToggle で切り替え。
//   全面 = view3d が偽、3D = view3d が真。view3d は index.html の #btnViewToggle の元の処理でだけ変える。
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const KIND = { breaker: '遮断器', disconnector: '断路器', transformer: '変圧器', bus: '母線', load: '調相設備' };
const hud = () => window.hud;
const inS1 = () => !!window.hud?.on && document.querySelector('.step.on')?.id === 's1';

let full = true;             // 今の表示: 結線図の全面か 3D か（段の外では意味を持たない）

// ---- 読むだけの小さな関数
const node = (m, id) => m.site?.topology.nodes.find(n => n.id === id);
const num = (m, id) => node(m, id)?.number || id;
function label(m, id) {            // 番号のあとに付ける説明（名前が ID と同じなら電圧・回線・種類から）
  const n = node(m, id); if (!n) return '';
  if (n.name && n.name !== n.id) return n.name;
  return [n.voltage_kv ? `${n.voltage_kv}kV` : '', n.bay || '', KIND[n.kind] || n.kind].filter(Boolean).join(' ');
}

// ---- 全面⇄3D（表示の切り替えだけ）
function viewToggleOrig() { const b = $('btnViewToggle'); b?.onclick?.call(b); }   // 元の処理: view3d を反転して showSld(!view3d)
function apply(m, wantFull) {
  const v = $('sldView'); if (!v || !m) return;
  install(m);
  const was = full; full = !!wantFull;
  if (m.view3d !== !full) viewToggleOrig();
  if (full !== v.classList.contains('on')) m.showSld(full);   // .on のときだけ refreshSld が SVG を取りに行く
  v.classList.remove('sld-mini'); v.classList.toggle('sld-full', full);
  if (full) requestAnimationFrame(scrollToTarget);
  else if (was && m.lastSteps) $('vTarget')?.onclick?.();   // 結線図から 3D へ: 取り替える機器に寄る
  hud()?.render();
}
function stow(m) {                                           // 段を出る: showSld(false) と同じ状態に
  const v = $('sldView'); if (!v) return;
  v.classList.remove('sld-mini', 'sld-full');
  if (v.classList.contains('on')) m?.showSld(false);
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
// 結線図の中身が描き直されたとき（初回の読み込み）: まだ動かしていなければ機器の所へ
function watchSld() {
  const w = $('sldWrap'), sc = $('sldScroll'); if (!w || !sc) return;
  new MutationObserver(() => {
    if (inS1() && full && !w.querySelector('.mk.tgt') && sc.scrollTop === 0 && sc.scrollLeft === 0) requestAnimationFrame(scrollToTarget);
  }).observe(w, { childList: true });
}

// ---- 一度だけ結ぶもの: #btnViewToggle の横取り、モードの変化、3D で機器を押す
let installed = false;
function install(m) {
  if (installed || !$('sldView')) return; installed = true;
  document.addEventListener('click', e => {                  // record.py と onboarding が押す: HUD の s1 では全面⇄3D
    if (!e.target.closest?.('#btnViewToggle') || !inS1()) return;
    e.stopImmediatePropagation(); e.preventDefault(); apply(window.maai, !full);
  }, true);
  document.querySelectorAll('input[name=sldMode]').forEach(r => r.addEventListener('change', () => hud()?.render()));
  watchSld();
  installPick(m);
}

// 3D の機器を押す = 結線図の同じ機器（.mk）を押す（結線図をしまっても .mk は残っている）
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
    if (best) { const mk = $('sldWrap').querySelector(`.mk[data-id="${CSS.escape(best)}"]`); mk?.onclick?.call(mk); }
  });
}

// ---- 枠の中身
export default {
  id: 's1', caption: 'STEP 1', title: '対象を選ぶ', short: '対象',

  goals(m) {
    const t = m.lastSteps?.targets?.[0];
    return [{ text: `単線図で、取り替える機器を押す${t ? ` <b>${esc(num(m, t))}</b>` : ''}`, done: !!t, now: !t }];
  },

  // 小さな道具: 押したときの動作の切替（全面のときだけ）と「依頼文から入れる」（任意）
  side() {
    const mode = hud()?.getMode();
    const sw = full ? `<div class="s1sw" role="group" aria-label="結線図を押したとき">
        <span>押すと</span>
        <button data-act="mode" data-v="target" aria-pressed="${mode === 'target'}">取り替える機器に選ぶ<kbd>Q</kbd></button>
        <button data-act="mode" data-v="toggle" aria-pressed="${mode === 'toggle'}">開閉器を入・切<kbd>W</kbd></button>
      </div>` : '';
    return `<div class="s1tools">${sw}<button class="sub s1req" data-act="intake" title="工事の依頼文から対象を読み取る（任意。引き出しが開く）">依頼文から入れる</button></div>`;
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

  // 右下: 全面⇄3D の切替だけ（data-mode を付けないので殻のモード切替には入らない）
  modes() {
    return `<button class="mode s1view" data-act="view"><span>${full ? '3D で見る' : '単線図に戻る'}</span><kbd>TAB</kbd></button>`;
  },
  nextLabel() { return '次へ: 置場と重さ →'; },
  onNext() { window.go('s2'); },
  nextDisabled(m) { return !m.lastSteps; },

  hints() {
    return full ? [] : [{ key: '左クリック', text: hud()?.getMode() === 'target' ? '機器を選ぶ' : '開閉器を入・切' }, { key: 'ドラッグ', text: '見回す' }, { key: 'TAB', text: '単線図に戻る' }];
  },

  // 3D 上のカード: 取り替える機器（layout.items の at）。全面の結線図の間は殻が隠す
  card(m) {
    const st = m.lastSteps, t = st?.targets?.[0]; if (!t || !m.site) return null;
    const it = m.site.layout.items.find(i => i.id === t && i.at) || m.site.layout.items.find(i => i.at && i.id.includes(t)); if (!it) return null;
    return { x: it.at[0], y: it.at[1], z: it.at[2] || 0, html: `<div class="s1card">
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
  onEnter(m) {                                               // 入ったら: 押すと「取り替える機器に選ぶ」、結線図を全面
    const r = document.querySelector('input[name=sldMode][value="target"]');
    if (r && !r.checked) { r.checked = true; r.dispatchEvent(new Event('change', { bubbles: true })); }
    document.body.dataset.mode = 'target';
    apply(m, true);
  },
  onLeave(m) { full = true; stow(m); },
};

// ---- ボタンの動作: 既存の要素を押すか、殻の API を呼ぶだけ
function act(d, m) {
  if (d.act === 'view') apply(m, !full);
  else if (d.act === 'mode') hud().setMode(d.v);
  else if (d.act === 'intake') {
    hud().openDrawer(); const t = $('reqText');
    t?.scrollIntoView({ block: 'center' }); t?.focus();
  }
}
