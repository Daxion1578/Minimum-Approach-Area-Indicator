// 重機の段（STEP 03）。殻（hud.js）に枠の中身を返すだけで、判定・距離・配置の値は engine/ の結果
// （window.maai の lastSelect / lastClearance / lastCrane / zoneSets）を読む。既存のボタン（#btnSelect, #btnAdoptSel, #zoneBox .zbtn）を押して動かす。
// ほかの段の見本: goals / answer / bar / modes / hints / card / bind / onKey / onMode を一通り使っている。
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const f = (v, d = 2) => (v == null || isNaN(v)) ? '—' : (+v).toFixed(d);
const tone = v => v === 'ng' ? 'ng' : v === 'conditional' ? 'cond' : v === 'ok' ? 'ok' : 'none';
const KIND = { breaker: '遮断器', disconnector: '断路器', transformer: '変圧器', bus: '母線', load: '調相設備' };
const PART = { boom: 'ブーム', rope: 'ワイヤ', load: '吊り荷', carrier: '車体' };   // engine/crane.py の part 名

// ---- 読むだけの小さな関数
function pick(m) {                       // 吊る物（選定の pick_id、無ければ引き出しの選択）
  const id = m.lastSelect?.pick_id || $('pickSel')?.value, n = m.site?.topology.nodes.find(x => x.id === id);
  return n ? { number: n.number || n.id, kind: KIND[n.kind] || n.kind } : null;
}
const weight = m => m.lastSelect?.weight_t ?? ($('pickT')?.value === '' ? null : +$('pickT').value);
const haveSet = () => $('setX')?.value !== '' && $('setY')?.value !== '';
const shownZone = m => (m.zoneSets || []).findIndex(z => z.cells === m.zoneCells);   // 今地面に塗っている範囲
const hud = () => window.hud;

// ---- 枠の中身
export default {
  id: 's2', caption: 'STEP 03', title: '重機の配置',

  goals(m) {
    const p = pick(m), w = weight(m);
    const g = [
      { text: p ? `吊る物 <b>${esc(p.number)}</b> ${esc(p.kind)}${w != null ? ` <b>${f(w, 1)} t</b>` : ''}` : '吊る物を選ぶ', done: !!m.lastSelect?.chosen },
      { text: '資材置場を置く', done: haveSet() },
      { text: '緑のマスにクレーンを据える', done: !!m.lastClearance },
    ];
    const first = g.find(x => !x.done); if (first) first.now = true;
    return g;
  },

  side() { return ''; },   // 補助カードは無し。情報は 3D 上のカードに出す

  answer(m) {
    const c = m.lastClearance, s = m.lastSelect;
    if (c) {                                            // 置いたあと: 判定と離隔
      const w = c.worst, v = tone(c.verdict);
      const msg = v === 'ok' ? '充電部に近づかずに吊れる' : v === 'cond' ? '条件を守れば吊れる' : '充電部に近づきすぎる';
      const scale = w ? Math.max(w.distance_m, w.required_m) * 1.25 : 1;
      return `<div class="ans" data-verdict="${v}">
        <div class="row1"><span class="v ${v}">${esc(c.verdict_ja)}</span><div class="capw"><span class="cap">CLEARANCE</span><span>${msg}</span></div></div>
        ${w ? `<div class="dist"><span class="lbl">最小離隔</span><span class="n lg">${f(w.distance_m)}</span><span class="unit">m</span><span class="need">必要 <span class="n">${f(w.required_m)}</span> m</span></div>
        <div class="gauge"><i style="width:${(w.distance_m / scale * 100).toFixed(1)}%"></i><b style="left:${(w.required_m / scale * 100).toFixed(1)}%"></b></div>
        <div class="near">最寄り ${esc(w.conductor_id)}（${esc(w.phase)} 相 ${esc(w.voltage_kv)}kV）· ${esc(PART[w.crane_part] || w.crane_part)}${w.slew_deg != null ? ` · 旋回 ${w.slew_deg > 0 ? '+' : ''}${f(w.slew_deg, 0)}°` : ''}</div>` : ''}
        ${c.conditions?.length ? `<div class="cond">条件: ${esc(c.conditions[0])}${c.conditions.length > 1 ? `（ほか ${c.conditions.length - 1}）` : ''}</div>` : ''}
        ${s?.by_weight?.note ? `<div class="dim">${esc(s.by_weight.note)}</div>` : ''}
      </div>`;
    }
    if (s?.chosen) {                                    // 選定の直後: 採用は人が押す
      const ch = s.chosen, v = tone(ch.verdict), cr = ch.crane;
      return `<div class="ans" data-verdict="${v}">
        <div class="row1"><span class="v ${v}">${esc(ch.verdict_ja)}</span><div class="capw"><span class="cap">SELECTED</span><span><b class="n">${esc(ch.class)}</b> 級で置ける（一番小さい級）</span></div></div>
        <div class="kv"><span>据付 <span class="n">${f(cr.base[0], 0)}, ${f(cr.base[1], 0)}</span></span><span>ブーム <span class="n">${f(cr.boom_len_m, 1)}</span> m</span><span>最小離隔 <span class="n">${f(ch.min_distance_m)}</span> m／必要 <span class="n">${f(ch.required_m)}</span> m</span></div>
        ${s.by_weight?.note ? `<div class="dim">${esc(s.by_weight.note)}</div>` : ''}
        <button class="act" data-act="adopt">この配置を採用</button>
      </div>`;
    }
    if (s) {                                            // 選定したが置けない
      return `<div class="ans" data-verdict="ng"><div class="lead">${esc((s.problems || []).join('。') || s.detail || '置ける位置が見つからない')}</div>
        ${s.with_outage?.note ? `<div class="dim">${esc(s.with_outage.note)}</div>` : ''}<button class="sub" data-act="detail">引き出しで確かめる</button></div>`;
    }
    return `<div class="ans" data-verdict="none"><div class="lead">置き場所と重さを入れると、クレーンの配置が決まる</div><button class="act" data-act="select">一番小さいクレーンを選ぶ</button></div>`;
  },

  bar(m) {
    const sets = m.zoneSets || [], shown = shownZone(m);
    const tiles = sets.map((z, i) => `<button class="tile" data-act="zone" data-i="${i}" aria-pressed="${i === shown}" title="${esc(z.name)} の据えてよい範囲を地面に塗る">
      <span class="n">${esc(z.class)}</span><small>置けるマス <b class="n">${z.cells.filter(x => x.ok).length}</b></small></button>`).join('');
    return `<button class="tile primary" data-act="select" title="重さと 2 点から、離隔を保てる一番小さい級と据付位置を計算で選ぶ">一番小さい<br>クレーンを選ぶ</button>`
      + tiles + `<span class="sep"></span>`
      + `<button class="tile" data-act="setby" aria-pressed="${!!$('setByClick')?.checked}" title="入にして 3D の地面を押すと、資材置場をそこに置く"><span class="mark"></span><small>資材置場</small></button>`;
  },

  modes() {
    return `<button class="mode" data-mode="select"><span>選ぶ</span><kbd>Q</kbd></button>
      <button class="mode" data-mode="move"><span>動かす</span><kbd>M</kbd></button>
      <button class="mode" data-mode="rotate"><span>回す</span><kbd>R</kbd></button>`;
  },
  nextLabel() { return 'この配置で確定 →'; },
  onNext() { window.go('s3'); },
  nextDisabled(m) { return !m.lastClearance; },

  hints(m) {
    const click = hud()?.getMode() === 'rotate' ? 'その向きへ回す' : $('setByClick')?.checked ? '資材置場を置く' : m.zoneCells ? '緑のマスに置く' : 'クレーンを置く';
    return [{ key: '左クリック', text: click }, { key: 'ドラッグ', text: '見回す' }, { key: 'R', text: '回す（Shift で逆）' }];
  },

  // 3D 上のカード: 今のクレーン（ベースの上 6 m）。ブームの先を away に渡して、カードがブームを隠さないようにする
  card(m) {
    const c = m.lastCrane; if (!c || !m.lastClearance) return null;
    const mode = hud()?.getMode(), elev = c.boom_elev2_deg != null ? `${f(c.boom_elev_deg, 0)}–${f(c.boom_elev2_deg, 0)}°` : `${f(c.boom_elev_deg, 0)}°`;
    const h = c.heading_deg * Math.PI / 180, e = c.boom_elev_deg * Math.PI / 180, L = c.boom_len_m;
    const tip = [c.base[0] + L * Math.cos(e) * Math.cos(h), c.base[1] + L * Math.cos(e) * Math.sin(h), L * Math.sin(e)];
    return { x: c.base[0], y: c.base[1], z: 6, away: tip, html: `<div class="crane">
      <div class="head"><span class="n cls">${esc(c.class || '25t')}</span><span class="nm">移動式クレーン</span><span class="ex">${esc(m.lastClearance.crane?.spec || '例示値')}</span></div>
      <div class="g4"><div>ブーム<b class="n">${f(c.boom_len_m, 1)}<small> m</small></b></div><div>起伏<b class="n">${elev}</b></div><div>向き<b class="n">${f(c.heading_deg, 0)}°</b></div><div>据付<b class="n">${f(c.base[0], 0)}, ${f(c.base[1], 0)}</b></div></div>
      <div class="btns"><button data-act="mode" data-mode="move" aria-pressed="${mode === 'move'}"><kbd>M</kbd>動かす</button><button data-act="mode" data-mode="rotate" aria-pressed="${mode === 'rotate'}"><kbd>R</kbd>回す</button><button data-act="detail">詳しく</button></div>
    </div>` };
  },

  // root（#hudRoot または #hudCard）の中の data-act ボタンに結ぶ。描画のたびに呼ばれる
  bind(root, m) { root.querySelectorAll('[data-act]').forEach(b => { b.onclick = () => act(b.dataset, m); }); },

  onKey(e, m) {
    const k = e.key.toLowerCase();
    if (k === 'q') { hud().setMode('select'); return true; }
    if (k === 'm') { hud().setMode('move'); return true; }
    if (k === 'r') { if (m.lastClearance) hud().rotate(e.shiftKey ? -5 : 5); else hud().setMode('rotate'); return true; }
    return false;
  },
  onMode(name) { if (name === 'select') { hud().openDrawer(); const s = $('pickSel'); s?.scrollIntoView({ block: 'center' }); s?.focus(); } },
  onEnter(m) { installRotateByClick(m); },
  onLeave() {},
};

// ---- ボタンの動作: 既存の要素を押すか、殻の API を呼ぶだけ
function act(d, m) {
  if (d.act === 'select') $('btnSelect').click();
  else if (d.act === 'adopt') $('btnAdoptSel')?.click();
  else if (d.act === 'zone') { const b = document.querySelector(`#zoneBox .zbtn[data-z="${d.i}"]`); if (b) b.click(); else if (m.zoneSets?.[+d.i]) m.drawZone(m.zoneSets[+d.i].cells); }
  else if (d.act === 'setby') { const cb = $('setByClick'); cb.checked = !cb.checked; hud().render(); }
  else if (d.act === 'mode') hud().setMode(d.mode);
  else if (d.act === 'detail') { hud().openDrawer(); const box = $('manualBox'); if (box) box.open = true; ($('verdictBox') || box)?.scrollIntoView({ block: 'start' }); }
}

// ---- 「回す」の切り替え中は、地面を押すとその向きへ回す（index.html の「押した所へ移す」は捕捉段階で止める。
//      軌道カメラの pointerup も止まるので、その drag を手で解いておく）
let installed = false, down = null;
function installRotateByClick(m) {
  if (installed || !m?.renderer) return; installed = true;
  const dom = m.renderer.domElement;
  dom.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; }, true);
  dom.addEventListener('pointerup', e => {
    if (!down || e.button !== 0 || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4) return;
    if (document.querySelector('.step.on')?.id !== 's2' || hud().getMode() !== 'rotate' || $('setByClick').checked) return;
    const hit = groundPoint(m, e); if (!hit) return;
    e.stopImmediatePropagation(); m.controls.drag = null;
    const base = m.craneFromForm().base, deg = Math.atan2(hit.y - base[1], hit.x - base[0]) * 180 / Math.PI;
    $('chead').value = Math.round(((deg % 360) + 360) % 360 * 10) / 10; m.evaluateClearance();
  }, true);
}
function groundPoint(m, e) {
  const T = m.THREE, r = m.renderer.domElement.getBoundingClientRect();
  const nd = new T.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const ray = new T.Raycaster(); ray.setFromCamera(nd, m.camera); const hit = new T.Vector3();
  return ray.ray.intersectPlane(new T.Plane(new T.Vector3(0, 0, 1), 0), hit) ? hit : null;
}
