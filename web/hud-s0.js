// 図面取込の段（STEP 01）。殻（hud.js）に枠の中身を返すだけ。値は window.maai の lastIngest / lastDraft / site を読み、
// 既存のボタン（#ingestFile → #btnIngest、#btnLayoutSample、#layoutFile、#btnConfirmAll、#btnUseDraft、#btnUseTruth）を押して動かす。
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const hud = () => window.hud;
const isDraft = m => m.site?.layout_source === 'drawing-draft';

// 読んでいる途中か（index.html が箱に書く文言で見る。応答が来れば箱が書き換わる）
let fetching = false;      // サンプルの PDF を取ってきている間（#btnIngest を押す前）
const busyIngest = () => fetching || !!$('ingestBox')?.textContent.includes('番号で結んでいる');
const busyLayout = () => !!$('layoutBox')?.textContent.includes('装置図を読んでいる');
const busySwitch = () => !!$('useMsg')?.textContent.includes('切り替えている');
const warnOf = id => $(id)?.querySelector(':scope > .warn')?.textContent || '';

function siteLine(m) {
  if (!m.site) return '';
  const ns = m.site.topology?.nodes || [], n = k => ns.filter(x => x.kind === k).length;
  return `<div class="site"><span class="n id">${esc(m.site.site_id)}</span><span>遮断器 <b class="n">${n('breaker')}</b></span><span>断路器 <b class="n">${n('disconnector')}</b></span><span>変圧器 <b class="n">${n('transformer')}</b></span></div>`;
}

// 結線図の取込（onboarding.js の loadSample と同じ手順）
async function sampleSld() {
  fetching = true; hud()?.render();
  try {
  const r = await fetch(new URL('./web/sample/SITE-01_sld.pdf', location.href).href);
  const dt = new DataTransfer(); dt.items.add(new File([await r.blob()], 'SITE-01_sld.pdf', { type: 'application/pdf' }));
  $('ingestFile').files = dt.files;
  } finally { fetching = false; }
  $('btnIngest').click();
}
let pickedFromHud = false;   // 「結線図 PDF を選ぶ」で選んだときだけ、選んだら続けて取り込む

function act(d) {
  if (d.act === 'sld-sample') sampleSld().catch(e => console.warn('[hud-s0] sample', e));
  else if (d.act === 'sld-file') { pickedFromHud = true; $('ingestFile').click(); }
  else if (d.act === 'lay-sample') $('btnLayoutSample').click();
  else if (d.act === 'lay-file') $('layoutFile').click();
  else if (d.act === 'confirm') $('btnConfirmAll')?.click();
  else if (d.act === 'use') $('btnUseDraft').click();
  else if (d.act === 'truth') $('btnUseTruth').click();
  else if (d.act === 'detail') { hud().openDrawer(); $(d.to || 'ingestBox')?.scrollIntoView({ block: 'start' }); }
  hud()?.render();
}

// 箱の中身が変わったら描き直す（取込中の表示・確認済の数・失敗の文言には maai-update が出ないため）
let installed = false;
function install() {
  if (installed) return; installed = true;
  const mo = new MutationObserver(() => { if (document.querySelector('.step.on')?.id === 's0') hud()?.render(); });
  for (const id of ['ingestBox', 'layoutBox', 'useMsg']) { const el = $(id); if (el) mo.observe(el, { childList: true, subtree: true, characterData: true }); }
  $('ingestFile')?.addEventListener('change', () => { if (pickedFromHud && $('ingestFile').files[0]) $('btnIngest').click(); pickedFromHud = false; });
}

export default {
  id: 's0', caption: 'STEP 01', title: '図面を読む',

  goals(m) {
    const g = [
      { text: '単線結線図の PDF を入れる', done: !!m.lastIngest },
      { text: '装置図（平面・断面）を入れる', done: !!m.lastDraft },
      { text: 'この 3D で続ける', done: isDraft(m) },
    ];
    const first = g.find(x => !x.done); if (first) first.now = true;
    return g;
  },

  side() { return ''; },

  answer(m) {
    const j = m.lastIngest, d = m.lastDraft, parts = [];
    const qn = j ? (j.annotation?.questions || []).length : 0;
    if (busyIngest()) parts.push(`<div class="lead">結線図を読んでいる…</div>`);
    else if (!j) parts.push(`<div class="lead">図面を入れると、構内の形と電気のつながりが一緒に見える</div>`);
    if (!j) parts.push(siteLine(m));
    const w = warnOf('ingestBox'); if (w) parts.push(`<div class="warn">${esc(w)}</div>`);
    if (j) {
      const ev = j.eval && !j.eval.error ? j.eval : null, sw = j.candidate?.switches?.length ?? 0;
      const read = ev ? `<span class="n big">${ev.numbers.found}</span><span class="of">/ <span class="n">${ev.numbers.drawn}</span></span>` : `<span class="n big">${sw}</span><span class="of">個</span>`;
      const src = j.annotation?.source === 'claude' ? '<span class="src claude">Claude</span>' : '<span class="src">規則（Claude 未使用）</span>';
      const cnt = $('ingestCount')?.textContent || '';
      parts.push(`<div class="cap">SINGLE-LINE DIAGRAM</div>
        <div class="stats"><div><span class="lbl">${ev ? '読めた番号' : '拾えた開閉器'}</span><div class="num">${read}</div></div>
          <div class="${qn ? 'q' : ''}"><span class="lbl">確かめてほしいこと</span><div class="num"><span class="n big">${qn}</span><span class="of">件</span></div></div></div>
        <div class="dim">意味づけ ${src}${ev?.numbers.missing?.length ? ` · 見つからない番号 <span class="n">${ev.numbers.missing.length}</span>` : ''}</div>
        <div class="btnrow"><button class="${/確認済 [1-9]/.test(cnt) ? 'sub' : 'act'}" data-act="confirm"${$('btnConfirmAll') ? '' : ' disabled'}>質問の無いものを確認済に</button>${cnt ? `<span class="n cnt">${esc(cnt)}</span>` : ''}</div>
        ${qn ? `<button class="sub link" data-act="detail" data-to="ingestBox">質問と開閉器の一覧を引き出しで見る</button>` : ''}`);
    }
    const lw = warnOf('layoutBox');
    if (busyLayout()) parts.push(`<div class="sect"><div class="lead">装置図を読んでいる…</div></div>`);
    else if (lw) parts.push(`<div class="sect"><div class="warn">${esc(lw)}</div></div>`);
    if (d && !busyLayout()) {
      const e = d.eval || {}, dq = (d.questions || []).length, ub = $('btnUseDraft'), sw = busySwitch(), dr = isDraft(m);
      parts.push(`<div class="sect"><div class="cap">LAYOUT DRAFT</div>
        <div class="kv"><span>機器の一致 <b class="n">${e.apparatus_matched ?? '—'} / ${e.apparatus_total ?? '—'}</b></span><span${dq ? ' class="qtxt"' : ''}>要確認 <b class="n">${dq}</b></span></div>
        <div class="btnrow">${dr ? '<span class="using">この 3D で続けている（図面から起こした配置・承認前）</span>' : `<button class="act" data-act="use"${ub?.disabled || sw ? ' disabled' : ''}>${sw ? '切り替えている…' : esc(ub?.textContent || 'この 3D で続ける')}</button>`}
          <button class="sub" data-act="truth"${sw || !dr ? ' disabled' : ''}>合成データに戻す</button></div></div>`);
    }
    const um = $('useMsg')?.querySelector('.warn')?.textContent; if (um) parts.push(`<div class="warn">${esc(um)}</div>`);
    return `<div class="ans s0" data-verdict="${j ? (qn ? 'cond' : 'ok') : 'none'}">${parts.join('')}</div>`;
  },

  bar(m) {
    const bi = busyIngest(), bl = busyLayout(), j = m.lastIngest;
    const t = (act, label, sub, o = {}) => `<button class="tile s0t${o.primary ? ' primary' : ''}" data-act="${act}"${o.busy ? ' disabled' : ''} title="${esc(o.title)}">`
      + `<span class="ic ${o.ic}"></span><span class="lb">${o.busy ? '読んでいる…' : label}</span><small>${sub}</small></button>`;
    return t('sld-sample', 'サンプルの結線図', 'SITE-01', { ic: 'sld', primary: !j, busy: bi, title: '合成変電所の単線結線図 PDF を取り込む' })
      + t('sld-file', '結線図 PDF<br>を選ぶ', 'ベクター PDF', { ic: 'file', busy: bi, title: '手元の単線結線図 PDF を選んで取り込む' })
      + `<span class="sep"></span>`
      + t('lay-sample', 'サンプル装置図', '平面・断面', { ic: 'lay', primary: !!j && !m.lastDraft, busy: bl, title: '合成変電所の装置図から 3D の下書きを起こす' })
      + t('lay-file', '装置図 PDF', '平面・断面', { ic: 'file', busy: bl, title: '手元の装置図 PDF から 3D の下書きを起こす' });
  },

  modes() { return ''; },
  nextLabel() { return '次へ: 停止範囲 →'; },
  onNext() { window.go('s1'); },
  nextDisabled() { return false; },
  hints() { return [{ key: 'ドラッグ', text: '見回す' }, { key: 'ホイール', text: '拡大' }]; },
  card() { return null; },
  bind(root) { root.querySelectorAll('#hudAnswer [data-act], #hudBar [data-act]').forEach(b => { b.onclick = () => act(b.dataset); }); },
  onKey() { return false; },
  onEnter() { install(); },
  onLeave() {},
};
