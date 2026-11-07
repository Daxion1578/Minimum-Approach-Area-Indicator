// 計画確定の段（STEP 04）。殻（hud.js）に枠の中身を返すだけ。値は window.maai の lastSteps / lastCrane / lastClearance /
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
const reason = () => $('planSummary')?.textContent.trim() || '';

export default {
  id: 's3', caption: 'STEP 04', title: '計画の確定',

  goals(m) {
    const g = [
      { text: '条件を確かめる', done: !blocked(m) },
      { text: approver() && !blocked(m) ? `承認者の符号 <b>${esc(approver())}</b>` : '承認者の符号を入れる', done: !blocked(m) && !!approver() },
      { text: '承認して書き出す', done: !!approved(m) },
    ];
    const first = g.find(x => !x.done); if (first) first.now = true;
    return g;
  },

  // 承認者（名前でなく符号）。値は bind で #approver から入れる（HTML に値を入れない: 打っている途中に書き直さないため）
  side(m) {
    if (blocked(m) || approved(m)) return '';
    return `<div class="s3ap" data-tone="act"><label for="hudApprover" class="cap">APPROVER</label>
      <div class="lbl">承認者（名前でなく符号）</div><input id="hudApprover" type="text" autocomplete="off" spellcheck="false">
      <div class="dim">承認時に engine がもう一度判定する</div></div>`;
  },

  answer(m) {
    const st = m.lastSteps, cr = m.lastCrane, c = m.lastClearance, a = approved(m);
    if (!st || !cr || !c) {
      return `<div class="ans s3" data-verdict="none"><div class="lead">停止範囲と重機を済ませてから</div>
        ${reason() && !reason().startsWith('停止範囲と重機を済ませてから') ? `<div class="dim">${esc(reason())}</div>` : ''}
        <div class="btnrow">${!st ? '<button class="sub" data-act="go" data-to="s1">停止範囲へ</button>' : ''}${!cr || !c ? '<button class="sub" data-act="go" data-to="s2">重機へ</button>' : ''}</div></div>`;
    }
    const v = tone(c.verdict), w = c.worst, cs = m.planConditions?.() || [];
    const head = a
      ? `<div class="row1"><span class="v ok">承認済み</span><div class="capw"><span class="cap">APPROVED</span><span>計画と停止範囲図を書き出した</span></div></div>
         <div class="hash"><span class="lbl">承認ハッシュ</span><span class="n">${esc(a.approval_hash)}</span></div>
         ${a.drawing_error ? `<div class="warn">図面: ${esc(a.drawing_error)}</div>` : ''}`
      : v === 'ng'
        ? `<div class="row1"><span class="v ng">承認できない</span><div class="capw"><span class="cap">PLAN</span><span>離隔が不可の計画は承認できない</span></div></div><div class="dim">${esc(reason())}</div>`
        : `<div class="row1"><span class="v ${v}">${esc(c.verdict_ja)}</span><div class="capw"><span class="cap">PLAN</span><span>${v === 'cond' ? '条件つきで承認できる' : '承認できる'}</span></div></div>`;
    const err = !a && m.lastApprove && !m.lastApprove.approval_hash && m.lastApprove.detail ? `<div class="warn">承認できない: ${esc(m.lastApprove.detail)}</div>` : '';
    const eo = m.extraOutage;
    return `<div class="ans s3" data-verdict="${a ? 'ok' : v}">${head}${err}
      <dl class="facts">
        <dt>対象</dt><dd>${esc(st.targets.map(m.nameOf).join('、'))}</dd>
        <dt>切る機器</dt><dd><b class="n">${st.ops.length}</b>${eo ? ` · 追加停止 ${esc(eo.names)}` : ''}</dd>
        <dt>クレーン</dt><dd>${esc(cr.class ? m.clsName(cr.class) : '例示の 25t 級')}</dd>
        <dt>離隔</dt><dd><span class="vt ${v}">${esc(c.verdict_ja)}</span>${w ? ` 最小 <b class="n">${f(w.distance_m)}</b> m／必要 <b class="n">${f(w.required_m)}</b> m` : ''}</dd>
      </dl>
      ${cs.length ? `<div class="conds"><div class="cap">CONDITIONS · ${cs.length}</div><ol>${cs.map(x => `<li>${esc(x)}</li>`).join('')}</ol><div class="dim">書き出しにも入る</div></div>` : ''}
      ${a ? `<div class="files">${a.files.map(fl => `<a href="/api/sites/${encodeURIComponent(m.site.site_id)}/approved/${encodeURIComponent(a.name)}/${encodeURIComponent(fl)}" target="_blank" rel="noopener">${esc(fl)}</a>`).join('')}</div>` : ''}
    </div>`;
  },

  bar(m) {
    const a = approved(m); if (!a) return '';
    return a.files.map(fl => {
      const ext = (fl.split('.').pop() || '').toUpperCase();
      return `<a class="tile s3f" href="/api/sites/${encodeURIComponent(m.site.site_id)}/approved/${encodeURIComponent(a.name)}/${encodeURIComponent(fl)}" target="_blank" rel="noopener" title="${esc(fl)} を開く"><span class="n">${esc(ext)}</span><small>${esc(fl.replace(/\.[^.]+$/, ''))}</small></a>`;
    }).join('');
  },

  modes() { return ''; },
  nextLabel(m) { return approved(m) ? '書き出し済み' : busy ? '書き出している…' : '承認して書き出す'; },
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
