// 確認して承認する段（STEP 3）。殻（hud.js）に枠の中身を返すだけ。値は window.maai の lastSteps / lastCrane / lastClearance /
// lastApprove / planConditions() を読み、承認は既存の #btnApprove を押す。承認者は HUD 側の入力から #approver に書き写す。
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const f = (v, d = 2) => (v == null || isNaN(v)) ? '—' : (+v).toFixed(d);
const tone = v => v === 'ng' ? 'ng' : v === 'conditional' ? 'cond' : v === 'ok' ? 'ok' : 'none';
const hud = () => window.hud;

// 承認した時点の停止範囲と離隔を覚えておき、その後に作り直したら「承認済み」と見せない
let at = null, busy = false;
addEventListener('maai-update', e => {
  const k = e.detail?.kind, M = window.maai;
  if (k === 'approve') { busy = false; at = M?.lastApprove?.approval_hash ? { steps: M.lastSteps, clr: M.lastClearance, a: M.lastApprove } : null; }
});
const approved = m => (at && at.a === m.lastApprove && at.steps === m.lastSteps && at.clr === m.lastClearance) ? m.lastApprove : null;
const ready = m => !!(m.lastSteps && m.lastCrane && m.lastClearance);
const blocked = m => !ready(m) || m.lastClearance.verdict === 'ng';
const approver = () => ($('approver')?.value || '').trim();

const fileUrl = (m, a, fl) => `/api/sites/${encodeURIComponent(m.site.site_id)}/approved/${encodeURIComponent(a.name)}/${encodeURIComponent(fl)}`;
// 書き出した PDF の名前（step-N-sld.pdf は段ごとの停止範囲の単線図、plan-crane.pdf はクレーン配置の平面図）
function pdfTitle(fl, st) {
  if (fl === 'plan-crane.pdf') return { k: 'PLAN · 平面図', t: 'クレーンの配置' };
  const n = +(/^step-(\d+)-sld\.pdf$/.exec(fl)?.[1] ?? NaN);
  if (n === 0) return { k: 'STEP 0 · 単線図', t: '作業前（平常）' };
  const s = (st?.steps || []).find(x => x.n === n);
  return { k: `STEP ${isNaN(n) ? '' : n} · 単線図`, t: s ? s.title : '承認した状態' };
}

export default {
  id: 's3', caption: 'STEP 3', title: '確認して承認', short: '承認',

  // 目標は 1 行（今やること）だけ
  goals(m) {
    if (!ready(m)) return [{ text: !m.lastSteps ? '対象を選んで停止範囲を作る' : '置場と重さを入れてクレーンを置く', now: true }];
    if (m.lastClearance.verdict === 'ng') return [{ text: '離隔が不可。置場と重さに戻る', now: true }];
    if (approved(m)) return [{ text: 'ステップ図を開いて確かめる', now: true }];
    return [{ text: 'この配置で OK なら承認する', now: true }];
  },

  side() { return ''; },

  answer(m) {
    const st = m.lastSteps, cr = m.lastCrane, c = m.lastClearance, a = approved(m);
    if (!st || !cr || !c) {
      return `<div class="ans s3" data-verdict="none"><div class="lead">${!st ? '対象' : '置場と重さ'}を済ませてから</div>
        <div class="btnrow">${!st ? '<button class="sub" data-act="go" data-to="s1">対象へ</button>' : ''}${!cr || !c ? '<button class="sub" data-act="go" data-to="s2">置場と重さへ</button>' : ''}</div></div>`;
    }
    const v = tone(c.verdict), w = c.worst, cs = m.planConditions?.() || [], eo = m.extraOutage;
    const head = a
      ? `<div class="row1"><span class="v ok">承認済み</span><span class="sub1">計画とステップ図を書き出した</span></div>
         ${a.drawing_error ? `<div class="warn">図面: ${esc(a.drawing_error)}</div>` : ''}`
      : v === 'ng'
        ? `<div class="row1"><span class="v ng">承認できない</span><span class="sub1">離隔が不可</span></div>`
        : `<div class="cap">この配置で承認する</div>`;
    const err = !a && m.lastApprove && !m.lastApprove.approval_hash && m.lastApprove.detail ? `<div class="warn">承認できない: ${esc(m.lastApprove.detail)}</div>` : '';
    const rows = `<dl class="facts">
        <dt>対象</dt><dd>${esc(st.targets.map(m.nameOf).join('、'))}</dd>
        <dt>切る開閉器</dt><dd><b class="n">${st.ops.length}</b>${eo ? ` <span class="dim">＋追加停止 ${esc(eo.names)}</span>` : ''}</dd>
        <dt>クレーン</dt><dd>${esc(cr.class ? m.clsName(cr.class) : '例示の 25t 級')}</dd>
        <dt>離隔</dt><dd><span class="vt ${v}">${esc(c.verdict_ja)}</span>${w ? ` <span class="dim">最小 <b class="n">${f(w.distance_m)}</b> m／必要 <b class="n">${f(w.required_m)}</b> m</span>` : ''}</dd>
      </dl>`;
    const conds = cs.length ? `<div class="conds${a ? ' folded' : ''}"><div class="cap">条件 · ${cs.length}</div><ol>${cs.map(x => `<li>${esc(x)}</li>`).join('')}</ol></div>` : '';
    const tail = a ? `<div class="hash"><span class="lbl">承認ハッシュ</span><span class="n">${esc(a.approval_hash)}</span></div>` : '';
    return `<div class="ans s3" data-verdict="${a ? 'ok' : v}">${head}${err}${rows}${a ? '' : conds}${tail}</div>`;
  },

  // 承認後: PDF（ステップ図・クレーン配置図）は大きなタイル、JSON は小さく
  bar(m) {
    const a = approved(m); if (!a) return '';
    const pdf = a.files.filter(fl => /\.pdf$/i.test(fl)), other = a.files.filter(fl => !/\.pdf$/i.test(fl));
    return `<div class="s3out"><div class="hd"><b>ステップ図ができた</b><span>押すと PDF を開く</span></div><div class="pdfs">`
      + pdf.map(fl => { const t = pdfTitle(fl, m.lastSteps);
        return `<a class="tile s3f${fl === 'plan-crane.pdf' ? ' plan' : ''}" href="${fileUrl(m, a, fl)}" target="_blank" rel="noopener" title="${esc(fl)} を開く">`
          + `<span class="ic"></span><span class="k">${esc(t.k)}</span><span class="t">${esc(t.t)}</span><small>${esc(fl)}</small></a>`; }).join('')
      + `</div>${other.length ? `<div class="json">${other.map(fl => `<a href="${fileUrl(m, a, fl)}" target="_blank" rel="noopener">${esc(fl)}</a>`).join('')}</div>` : ''}</div>`;
  },

  // 承認者の欄（小さく、承認ボタンの上）。値は bind で #approver から入れる（打っている途中に書き直さないため）
  modes(m) {
    if (blocked(m) || approved(m)) return '';
    return `<label class="s3ap"><span>承認者</span><input id="hudApprover" type="text" autocomplete="off" spellcheck="false" title="名前でなく符号"></label>`;
  },
  nextLabel(m) { return approved(m) ? '承認済み' : busy ? '書き出している…' : 'この配置で OK（承認）'; },
  onNext(m) { if (this.nextDisabled(m)) return; busy = true; hud()?.render(); $('btnApprove').click(); },
  nextDisabled(m) { return blocked(m) || !!approved(m) || busy || !approver(); },
  hints() { return []; },
  card() { return null; },

  bind(root, m) {
    root.querySelectorAll('#hudAnswer [data-act="go"]').forEach(b => { b.onclick = () => window.go(b.dataset.to); });
    const inp = root.querySelector('#hudApprover');
    if (inp) {
      if (document.activeElement !== inp) inp.value = $('approver')?.value || '';
      inp.oninput = () => { $('approver').value = inp.value; hud()?.render(); };
      inp.onkeydown = e => { if (e.key === 'Enter' && !this.nextDisabled(m)) this.onNext(m); };
    }
  },
  onKey() { return false; },
  onEnter() {},
  onLeave() {},
};
