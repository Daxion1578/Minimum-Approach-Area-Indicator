// 図面を読む段（STEP 0）。殻（hud.js）に枠の中身を返すだけ。値は window.maai の lastIngest / lastDraft / site を読み、
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

// 単線結線図で作った機器一覧と、装置図の平面の機器番号の一致（/api/ingest/layout の応答の match）。両方を読んだときだけ出す
const sldCount = j => new Set([...(j.candidate?.switches || []).map(s => s.number), ...(j.candidate?.transformers || []).map(t => t.number),
  ...(j.candidate?.loads || []).map(l => l.name)]).size;
const list = a => a.slice(0, 10).map(n => `<span class="no">${esc(n)}</span>`).join('、') + (a.length > 10 ? ` ほか ${a.length - 10}` : '');
function matchBlock(j, d) {
  const mt = d?.match; if (!j || !mt) return '';
  if (mt.sld_source === 'truth' || mt.sld !== sldCount(j))   // 装置図を先に読んだ: その照合は今の単線図とではない
    return `<div class="sect match old"><div class="dim">機器の一致: 装置図を読み直すと、読んだ単線図と照合する</div></div>`;
  const k = mt.only_sld.length + mt.only_plan.length;
  const head = `機器の一致: 単線図 <b class="n">${mt.sld}</b> 台 ／ 平面図 <b class="n">${mt.plan}</b> 台`;
  if (!k) return `<div class="sect match ok" data-match="ok"><div class="mh">${head} — 一致</div></div>`;
  const side = [mt.only_sld.length ? `<div class="ml"><span class="k">単線図だけ</span>${list(mt.only_sld)}</div>` : '',
    mt.only_plan.length ? `<div class="ml"><span class="k">平面図だけ</span>${list(mt.only_plan)}</div>` : ''];
  return `<div class="sect match ng" data-match="ng" title="平面図は装置図の平面（1/400）。一般平面図には機器番号が無い">
    <div class="mh">機器の不一致 <b class="n">${k}</b> 件</div><div class="md">単線図 <b class="n">${mt.sld}</b> 台 ／ 平面図 <b class="n">${mt.plan}</b> 台</div>${side.join('')}
    <div class="mn">図面どうしが合っていない。この 3D で続ける前に、どちらの図面が正しいか確かめる</div></div>`;
}
const mismatch = (j, d) => /data-match="ng"/.test(matchBlock(j, d));

export default {
  id: 's0', caption: 'STEP 0', title: '図面を読む', short: '図面',

  // 目標は 1 行（今やること）だけ
  goals(m) {
    const j = m.lastIngest;
    if (busyIngest()) return [{ text: '結線図を読んでいる…', now: true }];
    if (!j) return [{ text: '結線図を入れる（サンプルでよい）', now: true }];
    if (!/確認済 [1-9]/.test($('ingestCount')?.textContent || '')) return [{ text: '読めた結果を確かめる', now: true }];
    return [{ text: '次へ: 対象を選ぶ', now: true }];
  },

  side() { return ''; },

  answer(m) {
    const j = m.lastIngest, d = m.lastDraft, parts = [];
    const qn = j ? (j.annotation?.questions || []).length : 0;
    if (busyIngest()) parts.push(`<div class="lead">結線図を読んでいる…</div>`);
    else if (!j) parts.push(`<div class="lead">結線図を入れると、3D に電気のつながりが乗る</div>`);
    const w = warnOf('ingestBox'); if (w) parts.push(`<div class="warn">${esc(w)}</div>`);
    if (j) {
      const ev = j.eval && !j.eval.error ? j.eval : null, sw = j.candidate?.switches?.length ?? 0;
      const read = ev ? `<span class="n big">${ev.numbers.found}</span><span class="of">/ <span class="n">${ev.numbers.drawn}</span></span>` : `<span class="n big">${sw}</span><span class="of">個</span>`;
      const cnt = $('ingestCount')?.textContent || '';
      parts.push(`<div class="stats"><div><span class="lbl">${ev ? '読めた番号' : '拾えた開閉器'}</span><div class="num">${read}</div></div>
          <div class="${qn ? 'q' : ''}"><span class="lbl">確かめてほしいこと</span><div class="num"><span class="n big">${qn}</span><span class="of">件</span></div></div></div>
        <div class="btnrow"><button class="${/確認済 [1-9]/.test(cnt) ? 'sub' : 'act'}" data-act="confirm"${$('btnConfirmAll') ? '' : ' disabled'}>質問の無いものを確認済に</button>${cnt ? `<span class="n cnt">${esc(cnt)}</span>` : ''}</div>
        ${qn ? `<button class="sub link" data-act="detail" data-to="ingestBox">質問を見る（詳しく）</button>` : ''}`);
    }
    const lw = warnOf('layoutBox');
    if (busyLayout()) parts.push(`<div class="sect"><div class="dim">装置図を読んでいる…</div></div>`);
    else if (lw) parts.push(`<div class="sect"><div class="warn">${esc(lw)}</div></div>`);
    if (d && !busyLayout()) parts.push(matchBlock(j, d));
    if (d && !busyLayout()) {
      const e = d.eval || {}, dq = (d.questions || []).length, ub = $('btnUseDraft'), sw = busySwitch(), dr = isDraft(m);
      parts.push(`<div class="sect small"><div class="kv"><span>装置図 機器 <b class="n">${e.apparatus_matched ?? '—'} / ${e.apparatus_total ?? '—'}</b></span><span${dq ? ' class="qtxt"' : ''}>要確認 <b class="n">${dq}</b></span></div>
        <div class="btnrow">${dr ? '<span class="using">この 3D で続けている（承認前）</span>' : `<button class="sub" data-act="use"${ub?.disabled || sw ? ' disabled' : ''}>${sw ? '切り替えている…' : esc(ub?.textContent || 'この 3D で続ける')}</button>`}
          ${dr ? `<button class="sub" data-act="truth"${sw ? ' disabled' : ''}>合成データに戻す</button>` : ''}</div></div>`);
    }
    const um = $('useMsg')?.querySelector('.warn')?.textContent; if (um) parts.push(`<div class="warn">${esc(um)}</div>`);
    return `<div class="ans s0" data-verdict="${j ? (qn || mismatch(j, d) ? 'cond' : 'ok') : 'none'}">${parts.join('')}</div>`;
  },

  // 主役はサンプルの結線図のタイル 1 つ。ほかは小さく右に寄せる
  bar(m) {
    const bi = busyIngest(), bl = busyLayout(), j = m.lastIngest;
    const hero = `<button class="tile s0t hero${j ? ' done' : ''}" data-act="sld-sample"${bi ? ' disabled' : ''} title="合成変電所の単線結線図 PDF を取り込む">`
      + `<span class="ic sld"></span><span class="tx"><span class="lb">${bi ? '読んでいる…' : j ? 'サンプルの結線図（読めた）' : 'サンプルの結線図を読む'}</span>`
      + `<small>SITE-01 · 合成の単線結線図</small></span></button>`;
    const t = (act, label, o = {}) => `<button class="tile s0t mini" data-act="${act}"${o.busy ? ' disabled' : ''} title="${esc(o.title)}"><span class="lb">${o.busy ? '読んでいる…' : label}</span></button>`;
    return hero + `<span class="minis">`
      + t('sld-file', '結線図 PDF', { busy: bi, title: '手元の単線結線図 PDF を選んで取り込む' })
      + t('lay-sample', 'サンプル装置図', { busy: bl, title: '合成変電所の装置図（平面・断面）から 3D の下書きを起こす' })
      + t('lay-file', '装置図 PDF', { busy: bl, title: '手元の装置図 PDF から 3D の下書きを起こす' }) + `</span>`;
  },

  modes() { return ''; },
  nextLabel() { return '次へ: 対象を選ぶ →'; },
  onNext() { window.go('s1'); },
  nextDisabled() { return false; },
  hints() { return [{ key: 'ドラッグ', text: '見回す' }, { key: 'ホイール', text: '拡大' }]; },
  card() { return null; },
  bind(root) { root.querySelectorAll('#hudAnswer [data-act], #hudBar [data-act]').forEach(b => { b.onclick = () => act(b.dataset); }); },
  onKey() { return false; },
  onEnter() { install(); },
  onLeave() {},
};
