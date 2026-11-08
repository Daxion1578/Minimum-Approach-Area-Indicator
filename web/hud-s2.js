// 置場と重さの段（STEP 03）。殻（hud.js）に枠の中身を返すだけで、判定・距離・配置・級の値は engine/ の結果
// （window.maai の lastSelect / lastClearance / lastCrane / zoneSets と POST /api/sites/{site}/select_at）を読む。
// 流れ: 段に入ると真上の視点 → 入れるもの 2 つ（1 資材置場 = 地面を押して箱、2 重さ = 入力ボックス）
//   → そろったら自動で #btnSelect → 自分で押した結果が出たら自動で #btnAdoptSel（重さ・置場を変えたら 0.6 秒待って選び直し）
//   → クレーンを押すと選択（3D 上のカードに「動かす」「回す」）→ 動かす: 地面を押した位置へ select_at、回す: heading ±5° で select_at。
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const f = (v, d = 2) => (v == null || isNaN(v)) ? '—' : (+v).toFixed(d);
const tone = v => v === 'ng' ? 'ng' : v === 'conditional' ? 'cond' : v === 'ok' ? 'ok' : 'none';
const hud = () => window.hud;
const inS2 = () => !!window.hud?.on && document.querySelector('.step.on')?.id === 's2';

// ---- 段の中の状態（表示と操作のためだけ。値は engine の結果）
let sel = false;           // クレーンを押して選んでいる（3D 上のカードを出す）
let armed = false;         // 「動かす」: 次に地面を押した位置へ移す
let busy = '';             // 計算中の一言（select / select_at）
let notice = null;         // 動かせなかった理由など {text}
let mine = false;          // 自分で押した #btnSelect の結果を待っている（その結果だけ自動で採用する）
let adopting = false;      // 自動で採用して、判定が返るのを待っている
let topNext = false;       // 採用のあとの「クレーンへ寄る」を真上の視点に替える
let weightFocus = false;   // 重さの欄にいる（枠が書き直されたらフォーカスを戻す）
let timer = 0, lastKey = '';

// ---- 読むだけの小さな関数
const haveSet = () => $('setX')?.value !== '' && $('setY')?.value !== '';
const setXY = () => haveSet() ? [+$('setX').value, +$('setY').value] : null;
const weightVal = () => $('pickT')?.value === '' ? null : +$('pickT').value;
const pickId = m => $('pickSel')?.value || m.lastSelect?.pick_id;
const pickAt = m => m.site?.layout.items.find(i => i.id === pickId(m))?.at || null;
const placed = m => !!(m.lastCrane && m.lastClearance);
const shownZone = m => (m.zoneSets || []).findIndex(z => z.cells === m.zoneCells);
const verdictOk = m => ['ok', 'conditional'].includes(m.lastClearance?.verdict);

// ---- 枠の中身
export default {
  id: 's2', caption: 'STEP 2', title: '置場と重さ', short: '置場と重さ',

  goals(m) {   // 今やることの 1 行だけ
    const t = !haveSet() ? '地面を押して資材置場を置く'
      : weightVal() == null ? '吊る物の重さを入れる'
      : !placed(m) ? 'クレーンを自動で置いている'
      : verdictOk(m) ? 'よければ次へ（クレーンは押すと動かせる）' : 'クレーンを押して動かす・回す';
    return [{ text: t, now: true }];
  },

  // 入れるもの 2 つ（大きく）。中身は置場の座標と例示値の注記だけ（重さの値は bind で入れる: 打っている途中に書き直さない）
  side(m) {
    const s = setXY(), w = weightVal(), note = $('pickNote')?.textContent || '';
    const cur = !s ? 1 : w == null ? 2 : 0;
    return `<div class="s2in" data-tone="act">
      <div class="inp${cur === 1 ? ' now' : ''}${s ? ' done' : ''}">
        <div class="hd"><span class="no">1</span><b>資材置場</b>${s ? `<span class="st n">${f(s[0], 0)}, ${f(s[1], 0)}</span>` : ''}</div>
        <div class="how">${s ? '地面を押すと置き直す' : '地面を押して置く'}</div>
      </div>
      <div class="inp${cur === 2 ? ' now' : ''}${w != null ? ' done' : ''}">
        <div class="hd"><span class="no">2</span><b>重さ</b></div>
        <label class="wbox"><input id="s2W" type="number" step="0.1" min="0" inputmode="decimal" aria-label="吊る物の重さ（t）"><span>t</span></label>
        ${note ? `<div class="how">${esc(note)}</div>` : ''}
      </div>
      ${placed(m) || m.zoneCells ? `<div class="s2leg">
        <div><i class="sw g"></i>緑 ＝ 据えてよい所（3 m 角）</div>
        <div><i class="sw x"></i>灰 ＝ 置けない所</div>
        <div><i class="sw y"></i>黄 ＝ 一番近い充電部と距離</div>
      </div>` : ''}
    </div>`;
  },

  // 結果の板: 級と可否と最小離隔だけ
  answer(m) {
    const c = m.lastClearance, cr = m.lastCrane;
    const extra = busy ? `<div class="dim">${esc(busy)}</div>` : notice ? `<div class="warn">${esc(notice.text)}</div>` : '';
    if (c && cr) {
      const v = tone(c.verdict), w = c.worst, cls = esc(cr.class || '');
      return `<div class="ans" data-verdict="${v}">
        <div class="row1"><span class="v ${v}">${esc(c.verdict_ja)}</span><span class="lead2"><b class="n">${cls}</b> 級<span class="ex">（例示値）</span>${v === 'ng' ? 'では近すぎる' : 'で置ける'}</span></div>
        ${w ? `<div class="dist"><span class="lbl">最小離隔</span><span class="n lg">${f(w.distance_m)}</span><span class="unit">m</span><span class="need">必要 <span class="n">${f(w.required_m)}</span> m</span></div>` : ''}
        ${extra}</div>`;
    }
    const s = m.lastSelect;
    if (busy) return `<div class="ans" data-verdict="none"><div class="lead">${esc(busy)}</div></div>`;
    if (s && !s.chosen) return `<div class="ans" data-verdict="ng"><div class="lead">${esc((s.problems || []).join('。') || s.detail || '置ける位置が見つからない')}</div></div>`;
    if (!haveSet() || weightVal() == null) return '';
    return `<div class="ans" data-verdict="none"><div class="lead">置場と重さがそろった</div><button class="act" data-act="select">一番小さいクレーンを選ぶ</button></div>`;
  },

  bar(m) {   // 予備の「選ぶ」と級ごとの緑の範囲（小さく）。置場を置くまでは出さない
    if (!placed(m) && !m.lastSelect) return '';
    const sets = m.zoneSets || [], shown = shownZone(m);
    return `<button class="tile primary" data-act="select" title="重さと置場から、離隔を保てる一番小さい級と据付位置を計算で選び直す">一番小さい<br>クレーンを選ぶ</button>`
      + sets.map((z, i) => `<button class="tile" data-act="zone" data-i="${i}" aria-pressed="${i === shown}" title="${esc(z.name)} の据えてよい範囲を地面に塗る">
        <span class="n">${esc(z.class)}</span><small>置けるマス <b class="n">${z.cells.filter(x => x.ok).length}</b></small></button>`).join('');
  },

  modes() { return ''; },
  nextLabel() { return '次へ: 確認して承認'; },
  onNext() { window.go('s3'); },
  nextDisabled(m) { return !verdictOk(m) || !!busy; },

  hints(m) {
    if (armed) return [{ key: '左クリック', text: 'そこへクレーンを移す' }, { key: 'Esc', text: 'やめる' }];
    if (!placed(m)) return [{ key: '左クリック', text: '資材置場を置く' }, { key: 'ドラッグ', text: '見回す' }];
    return [{ key: '左クリック', text: 'クレーンを押して選ぶ' }, { key: 'ドラッグ', text: '見回す' }, { key: 'R', text: '回す（Shift で逆）' }];
  },

  // 3D 上のカード: クレーンを押したときだけ。ブームの先を away に渡して、カードがブームを隠さないようにする
  card(m) {
    const c = m.lastCrane; if (!sel || !c || !m.lastClearance) return null;
    return { x: c.base[0], y: c.base[1], z: 6, away: tipOf(c), html: `<div class="crane">
      <div class="head"><span class="n cls">${esc(c.class || '')}</span><span class="nm">クレーン</span><span class="ex">向き <span class="n">${f(c.heading_deg, 0)}°</span></span></div>
      <div class="btns"><button data-act="arm" aria-pressed="${armed}">動かす</button><button data-act="rot" data-d="5" title="左回りに 5°（R）">↺ 5°</button><button data-act="rot" data-d="-5" title="右回りに 5°（Shift+R）">↻ 5°</button><button data-act="unsel" class="x" title="閉じる（Esc）" aria-label="閉じる">×</button></div>
      ${armed ? '<div class="how">地面を押すと、その位置で級を選び直して移す</div>' : ''}
    </div>` };
  },

  bind(root, m) {
    root.querySelectorAll('[data-act]').forEach(b => { b.onclick = () => act(b.dataset, m); });
    drawBox(m);   // 引き出しで吊る機器を替えると置場が消える（pickChanged）。描き直しのたびに箱を合わせる（変わらなければ何もしない）
    const inp = root.querySelector('#s2W'); if (!inp) return;
    if (!inp.dataset.bound) {
      inp.dataset.bound = '1';
      inp.addEventListener('focus', () => { weightFocus = true; });
      inp.addEventListener('blur', () => { weightFocus = false; });
      inp.addEventListener('input', () => { $('pickT').value = inp.value; schedule(m); hud()?.render(); });
      if (weightFocus) { inp.value = $('pickT').value; inp.focus(); }   // 打っている途中に枠が書き直された
    }
    if (document.activeElement !== inp) {
      const v = $('pickT')?.value || (m.lastSelect?.weight_t != null ? String(m.lastSelect.weight_t) : '');
      if (inp.value !== v) inp.value = v;
      if ($('pickT').value === '' && v !== '') $('pickT').value = v;
    }
  },

  onKey(e, m) {
    const k = e.key.toLowerCase();
    if (k === 'r' && placed(m)) { rotateBy(e.shiftKey ? -5 : 5, m); return true; }
    if (k === 'm' && placed(m)) { sel = true; armed = !armed; hud().render(); return true; }
    if (k === 'escape' && (sel || armed)) { sel = false; armed = false; hud().render(); return true; }
    return false;
  },
  onEnter(m) {
    install(m); wrapVCrane(); sel = false; armed = false; notice = null;
    topView(m); drawBox(m); startDist();
    if (!m.lastSelect && !placed(m)) schedule(m);   // 依頼文などで置場と重さが入っていれば、そのまま選ぶ
  },
  onLeave() { sel = false; armed = false; clearTimeout(timer); },

  // 録画スクリプトが window.hud.placeAtCell(i) / rotate(deg) で使う（殻が s2 の段ではここへ回す）
  placeAtCell(i, m) {
    const cell = (m.zoneCells || []).filter(c => c.ok)[i]; if (!cell) return null;
    return moveTo([cell.x, cell.y], m);
  },
  rotate(deg, m) { return rotateBy(deg, m); },
};

// ---- ボタンの動作
function act(d, m) {
  if (d.act === 'select') runSelect(m, true);
  else if (d.act === 'zone') { const b = document.querySelector(`#zoneBox .zbtn[data-z="${d.i}"]`); if (b) b.click(); else if (m.zoneSets?.[+d.i]) m.drawZone(m.zoneSets[+d.i].cells); }
  else if (d.act === 'arm') { armed = !armed; hud().render(); }
  else if (d.act === 'rot') rotateBy(+d.d, m);
  else if (d.act === 'unsel') { sel = false; armed = false; hud().render(); }
}

// ---- 自動の選定と採用: 置場と重さがそろったら 0.6 秒待って #btnSelect、自分で押した結果が出たら #btnAdoptSel
const keyOf = m => `${pickId(m)}|${weightVal()}|${setXY()?.join(',')}`;
function schedule(m) {
  clearTimeout(timer);
  timer = setTimeout(() => {
    if (!inS2() || !haveSet() || !(weightVal() > 0)) return;
    if (keyOf(m) === lastKey) return;
    if (busy) { schedule(m); return; }   // 計算中は終わってから
    runSelect(m, false);
  }, 600);
}
function runSelect(m, force) {
  if (busy && !force) return;
  lastKey = keyOf(m); mine = true; busy = 'クレーンを選んでいる…'; notice = null; sel = false; armed = false;
  hud().render(); $('btnSelect').click();
}
addEventListener('maai-update', e => {
  const k = e.detail?.kind, m = window.maai;
  if (k === 'select' && mine) {
    mine = false; busy = '';
    // index.html は emit('select') のあとで #btnAdoptSel の onclick を結ぶので、押すのは次の番で
    if (m.lastSelect?.chosen && $('btnAdoptSel')) { busy = 'クレーンを置いている…'; adopting = true; topNext = true; setTimeout(() => $('btnAdoptSel')?.click(), 0); }
    else if (keyOf(m) !== lastKey) schedule(m);
  }
  if (k === 'clearance' && adopting) {
    adopting = false; busy = '';
    setTimeout(() => { topNext = false; }, 3000);
    if (keyOf(m) !== lastKey) schedule(m);   // 計算中に重さ・置場が変わった
  }
  if (k === 'steps' || k === 'reset') { lastKey = ''; sel = false; armed = false; notice = null; }
  if (m) drawBox(m);
  if (k === 'clearance') startDist();
});

// ---- 一番近い充電部までの距離の札（3D の上、最寄りの線の真ん中）。値は engine の lastClearance.worst をそのまま出す
let distEl = null, distLoop = 0;
function distTick() {
  const m = window.maai, w = m?.lastClearance?.worst;
  if (!distEl) { distEl = document.createElement('div'); distEl.id = 's2Dist'; document.body.appendChild(distEl); }
  if (!inS2() || !w || !m.camera || !m.renderer) { distEl.style.display = 'none'; distLoop = 0; return; }
  const v = new m.THREE.Vector3((w.p_crane[0] + w.p_conductor[0]) / 2, (w.p_crane[1] + w.p_conductor[1]) / 2, (w.p_crane[2] + w.p_conductor[2]) / 2).project(m.camera);
  const r = m.renderer.domElement.getBoundingClientRect();
  if (v.z < -1 || v.z > 1) distEl.style.display = 'none';
  else {
    distEl.style.display = 'block';
    distEl.style.left = `${r.left + (v.x + 1) / 2 * r.width}px`; distEl.style.top = `${r.top + (1 - v.y) / 2 * r.height}px`;
    const txt = `最小 ${f(w.distance_m)} m`; if (distEl.textContent !== txt) distEl.textContent = txt;
    distEl.dataset.v = tone(m.lastClearance.verdict);
  }
  distLoop = requestAnimationFrame(distTick);
}
function startDist() { if (!distLoop) distLoop = requestAnimationFrame(distTick); }

// ---- 動かす・回す: その位置（向き）で一番小さい級を engine に選び直してもらう。ok でなければ理由を出して動かさない
async function selectAt(m, base, heading) {
  if (busy) return null;
  const body = { state: m.state, pick_id: pickId(m), base, weight_t: weightVal(), set_xy: setXY(), load: m.lastLoad };
  if (heading != null) body.heading_deg = heading;
  busy = heading != null ? '向きを変えて級を選び直している…' : 'その位置で級を選び直している…'; notice = null; hud().render();
  try {
    const r = await fetch(`/api/sites/${m.site.site_id}/select_at`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    const j = await r.json();
    if (!r.ok || !j.ok || !j.chosen) {
      const d = Array.isArray(j.detail) ? j.detail[0]?.msg : j.detail;
      busy = ''; notice = { text: (j.problems || [])[0] || d || `選び直せなかった（${r.status}）` }; hud().render(); return j;
    }
    m.craneToForm(j.chosen.crane);
    busy = '';
    const out = await m.evaluateClearance();
    hud().render(); return out;
  } catch (err) { busy = ''; notice = { text: `選び直せなかった: ${err.message || err}` }; hud().render(); return null; }
}
function moveTo(xy, m) { armed = false; return selectAt(m, [+xy[0], +xy[1]], null); }
function rotateBy(deg, m) {
  const c = m.lastCrane; if (!c) return null;
  const h = Math.round((((c.heading_deg + deg) % 360) + 360) % 360 * 10) / 10;
  return selectAt(m, [c.base[0], c.base[1]], h);
}

// ---- 地面を押す: 段の中では index.html の「押した所へ移す」を捕捉段階で止め、ここで振り分ける
//      （軌道カメラの pointerup も止まるので、その drag を手で解いておく）
let installed = false;
function install(m) {
  if (installed || !m?.renderer) return; installed = true;
  const dom = m.renderer.domElement; let down = null;
  dom.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; }, true);
  dom.addEventListener('pointerup', e => {
    if (!down || e.button !== 0 || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 4 || !inS2()) return;
    const M = window.maai, hit = groundPoint(M, e); if (!hit) return;
    e.stopImmediatePropagation(); M.controls.drag = null;
    onGround(M, hit, e);
  }, true);
}
function onGround(m, hit, e) {
  if (placed(m) && onCrane(m, e.clientX, e.clientY)) { sel = true; notice = null; hud().render(); return; }
  if (armed) { const cell = m.zoneCellAt(hit.x, hit.y); moveTo(cell ? [cell.x, cell.y] : [Math.round(hit.x * 10) / 10, Math.round(hit.y * 10) / 10], m); return; }
  if (sel) { sel = false; hud().render(); return; }   // 選んでいる間に外を押したら、選択を解くだけ
  $('setX').value = hit.x.toFixed(0); $('setY').value = hit.y.toFixed(0);   // 資材置場（置き直し）
  drawBox(m); schedule(m); hud().render();
}
// 押した点がクレーン（据付の点か、ブームの線）の近くか。画面上の距離で見る
function onCrane(m, sx, sy) {
  const c = m.lastCrane; if (!c) return false;
  const r = m.renderer.domElement.getBoundingClientRect();
  const P = p => { const v = new m.THREE.Vector3(...p).project(m.camera); return [r.left + (v.x + 1) / 2 * r.width, r.top + (1 - v.y) / 2 * r.height]; };
  const a = P([c.base[0], c.base[1], 2]), b = P(tipOf(c));
  const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy || 1, t = Math.max(0, Math.min(1, ((sx - a[0]) * dx + (sy - a[1]) * dy) / L2));
  return Math.hypot(sx - a[0], sy - a[1]) < 30 || Math.hypot(sx - (a[0] + t * dx), sy - (a[1] + t * dy)) < 14;
}
function tipOf(c) {
  const h = c.heading_deg * Math.PI / 180, e = c.boom_elev_deg * Math.PI / 180, L = c.boom_len_m;
  return [c.base[0] + L * Math.cos(e) * Math.cos(h), c.base[1] + L * Math.cos(e) * Math.sin(h), L * Math.sin(e)];
}
function groundPoint(m, e) {
  const T = m.THREE, r = m.renderer.domElement.getBoundingClientRect();
  const nd = new T.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  const ray = new T.Raycaster(); ray.setFromCamera(nd, m.camera); const hit = new T.Vector3();
  return ray.ray.intersectPlane(new T.Plane(new T.Vector3(0, 0, 1), 0), hit) ? hit : null;
}

// ---- 真上の視点（frameTo は phi を 0.45 に寄せるので使わず、controls を自前で動かす）
let camAnim = 0;
function topView(m, cx, cy, radius) {
  const c = m.controls; if (!c) return;
  const at = pickAt(m) || [c.target.x, c.target.y];
  const tx = cx ?? at[0], ty = cy ?? at[1], tr = radius ?? 70, tth = -Math.PI / 2, tph = 1.5;
  const t0 = c.target.clone(), r0 = c.radius, ph0 = c.phi;
  let th0 = c.theta; while (th0 - tth > Math.PI) th0 -= 2 * Math.PI; while (th0 - tth < -Math.PI) th0 += 2 * Math.PI;
  const id = ++camAnim, t0ms = performance.now(), dur = 450;   // 時間で進める（コマ数が少ない環境でも同じ長さ）
  (function tick() {
    if (id !== camAnim) return;
    const k = Math.min(1, (performance.now() - t0ms) / dur), e = 1 - Math.pow(1 - k, 3);
    c.target.set(t0.x + (tx - t0.x) * e, t0.y + (ty - t0.y) * e, 0); c.radius = r0 + (tr - r0) * e;
    c.theta = th0 + (tth - th0) * e; c.phi = ph0 + (tph - ph0) * e;
    if (k < 1) requestAnimationFrame(tick);
  })();
}
// 真上のまま、吊る点・置場・クレーンが入るように寄せる
function topAll(m) {
  const pts = [pickAt(m), setXY(), m.lastCrane?.base].filter(Boolean); if (!pts.length) return topView(m);
  const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]);
  const span = Math.max(Math.max(...xs) - Math.min(...xs), (Math.max(...ys) - Math.min(...ys)) * 1.4);
  topView(m, (Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2, Math.max(70, span * 1.8));
}
// 採用のあとの「クレーンへ寄る」（#vCrane、斜めの視点）を、自動で採用したときだけ真上の topAll に替える。人が押したときは今まで通り
let vcWrapped = false;
function wrapVCrane() {
  const b = $('vCrane'); if (vcWrapped || !b?.onclick) return; vcWrapped = true;
  const orig = b.onclick;
  b.onclick = function (...a) { if (topNext && inS2()) { topNext = false; return topAll(window.maai); } return orig.apply(this, a); };
}

// ---- 資材置場の箱（吊る物の大きさ lastLoad の w×d×h、半透明の紫と枠線、足もとに薄い四角）
let boxGroup = null, boxKey = '';
function drawBox(m) {
  const T = m?.THREE; if (!T || !m.scene) return;
  if (!boxGroup) { boxGroup = new T.Group(); boxGroup.name = 'hudS2Laydown'; m.scene.add(boxGroup); }
  const s = setXY(), L = m.lastLoad || { w: 2, d: 2, h: 2.5 }, key = s ? `${s}|${L.w}|${L.d}|${L.h}` : '';
  if (key === boxKey) return; boxKey = key;
  for (const o of [...boxGroup.children]) { boxGroup.remove(o); o.geometry?.dispose(); o.material?.dispose(); }
  if (!s) return;
  const g = new T.BoxGeometry(L.w, L.d, L.h);
  const box = new T.Mesh(g, new T.MeshBasicMaterial({ color: 0xb48cff, transparent: true, opacity: 0.35, depthWrite: false }));
  const edge = new T.LineSegments(new T.EdgesGeometry(g), new T.LineBasicMaterial({ color: 0xe2d0ff }));
  const pg = new T.PlaneGeometry(L.w + 4, L.d + 4);   // 足もとの置場（荷の周りに 2 m ずつ）。真上から見ても荷の印に隠れない大きさ
  const pad = new T.Mesh(pg, new T.MeshBasicMaterial({ color: 0xb48cff, transparent: true, opacity: 0.22, depthWrite: false }));
  const padEdge = new T.LineSegments(new T.EdgesGeometry(pg), new T.LineBasicMaterial({ color: 0xb48cff }));
  box.position.set(s[0], s[1], L.h / 2); edge.position.copy(box.position); pad.position.set(s[0], s[1], 0.06); padEdge.position.copy(pad.position);
  boxGroup.add(pad, padEdge, box, edge);
}
