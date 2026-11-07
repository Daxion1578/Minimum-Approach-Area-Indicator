// 初回の案内・進行バー・「3 分で一周」。index.html の既存のボタンを順に押すだけで、判定や計算には関わらない。
const $ = id => document.getElementById(id);
const KEY_SEEN = 'maai.onboarded', KEY_JSON = 'maai.json';
const ls = { get(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }, set(k,v){ try { localStorage.setItem(k,v); } catch(e){} } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function waitFor(pred, ms = 60000){ const t0 = Date.now(); for(;;){ const v = pred(); if (v) return v; if (Date.now()-t0 > ms) return null; await sleep(120); } }

// ---------------------------------------------------------------- 内部データの開閉
function setJson(on){ document.body.classList.toggle('json', on); $('btnJson').setAttribute('aria-pressed', on); ls.set(KEY_JSON, on ? '1' : '0'); window.dispatchEvent(new Event('resize')); }
$('btnJson').onclick = () => setJson(!document.body.classList.contains('json'));
if (ls.get(KEY_JSON) === '1') setJson(true);
new ResizeObserver(() => window.dispatchEvent(new Event('resize'))).observe($('view'));

// ---------------------------------------------------------------- 状態の見方（画面の表示だけを見る）
const stages = ['s0','s1','s2','s3'];
const cur = () => document.querySelector('.step.on')?.id || 's0';
const isDone = {
  s0: () => !!$('btnConfirmAll'),
  s1: () => !!$('stepsBox').querySelector('.bay'),
  s2: () => !!$('verdictBox').querySelector('.bay'),
  s3: () => !!$('approveBox').querySelector('.bay'),
};
let busy = false, tourOn = false;

function nextText(){
  const s = cur();
  if (s === 's0') return isDone.s0() ? '次: 確認済にして停止範囲へ' : ($('ingestFile').files[0] ? '次: 選んだ図面を取り込む' : '次: サンプル図面を取り込む');
  if (s === 's1') return isDone.s1() ? '次: 重機へ' : '次: 停止範囲を作る';
  if (s === 's2') return isDone.s2() ? '次: 計画確定へ' : '次: 一番小さいクレーンを選んで採用';
  return isDone.s3() ? '書き出し済み。リンクから開ける' : '次: 承認して書き出す';
}
function refresh(){
  const s = cur();
  document.querySelectorAll('#prog [data-goto]').forEach(b => {
    b.classList.toggle('on', b.dataset.goto === s);
    b.classList.toggle('done', isDone[b.dataset.goto]());
    b.setAttribute('aria-current', b.dataset.goto === s ? 'step' : 'false');
    const i = b.querySelector('i'), n = stages.indexOf(b.dataset.goto)+1; i.textContent = isDone[b.dataset.goto]() && b.dataset.goto !== s ? '✓' : n;
  });
  $('nextLabel').textContent = nextText();
  $('btnNext').disabled = busy || (s === 's3' && isDone.s3());
  $('btnTour').disabled = busy && !tourOn;
}
document.querySelectorAll('#prog [data-goto]').forEach(b => b.onclick = () => { window.go(b.dataset.goto); });
const mo = new MutationObserver(refresh);
['ingestBox','stepsBox','verdictBox','approveBox'].forEach(id => mo.observe($(id), {childList:true, subtree:true}));
mo.observe(document.querySelector('#left'), {attributes:true, attributeFilter:['class'], subtree:true});
$('ingestFile').addEventListener('change', refresh);
$('btnSteps').addEventListener('click', () => { $('stepsBox').dataset.t = $('targetSel').value; });

// ---------------------------------------------------------------- 各段階の主操作（既存のボタンを押す）
async function siteReady(){
  if (window.MAAI_READY) await window.MAAI_READY.catch(() => null);
  return waitFor(() => $('siteSummary').rows.length && !$('hud').textContent.includes('読み込み中'), 120000);
}
async function loadSample(){
  const r = await fetch(new URL('./web/sample/SITE-01_sld.pdf', location.href).href);
  const dt = new DataTransfer(); dt.items.add(new File([await r.blob()], 'SITE-01_sld.pdf', {type:'application/pdf'}));
  $('ingestFile').files = dt.files;
}
async function ingest(){
  if ($('btnConfirmAll')) return true;
  if (!$('ingestFile').files[0]) await loadSample();
  $('ingestBox').innerHTML = '';
  $('btnIngest').click();
  return !!(await waitFor(() => $('btnConfirmAll') || $('ingestBox').querySelector('.warn'), 90000)) && !!$('btnConfirmAll');
}
async function confirmAndNext(){ if (!(await ingest())) return false; $('btnConfirmAll').click(); window.go('s1'); return true; }
async function makeSteps(){
  if (isDone.s1() && $('stepsBox').dataset.t === $('targetSel').value) { window.go('s2'); return true; }
  $('stepsBox').innerHTML = '';
  $('btnSteps').click();
  if (!(await waitFor(() => $('stepsBox').querySelector('.bay'), 30000))) return false;
  window.go('s2'); return true;
}
async function pickCrane(){
  if (!isDone.s2()) {
    $('selectBox').innerHTML = ''; $('verdictBox').innerHTML = '';
    $('btnSelect').click();
    await waitFor(() => $('selectBox').querySelector('.big, .warn'), 60000);
    if (!$('btnAdoptSel')) return false;             // 置けない／失敗。選定の結果を画面に残して止まる
    $('btnAdoptSel').click();
    if (!(await waitFor(() => $('verdictBox').querySelector('.bay'), 30000))) return false;
  }
  window.go('s3'); return true;
}
async function approve(){
  $('approveBox').innerHTML = '';
  $('btnApprove').click();
  return !!(await waitFor(() => $('approveBox').querySelector('.bay, .warn'), 60000)) && !!$('approveBox').querySelector('.bay');
}
const actions = { s0: confirmAndNext, s1: makeSteps, s2: pickCrane, s3: approve };

$('btnNext').onclick = async () => {
  if (busy) return; busy = true; refresh();
  try { await siteReady(); await actions[cur()](); } finally { busy = false; refresh(); }
};

// ---------------------------------------------------------------- 初回の案内
const W = document.createElement('div');
W.id = 'welcome'; W.setAttribute('role','dialog'); W.setAttribute('aria-modal','true'); W.setAttribute('aria-labelledby','welcomeH');
W.innerHTML = `<div class="card">
  <h2 id="welcomeH">変電所の機器を取り替える日に、どこを止めれば足りるか、残った充電部に近づかずに吊れる一番小さいクレーンはどれかを、図面から計算して出す道具です。</h2>
  <ol><li><b>1</b>図面を読む（単線結線図の PDF）</li><li><b>2</b>停止範囲を出す（切る開閉器と、停電・充電の色分け）</li><li><b>3</b>クレーンを選んで承認する（離隔を計算で確かめ、書き出す）</li></ol>
  <div class="btns"><button class="act" id="wStart">サンプルで始める</button><button class="sub" id="wOwn">自分の図面を読み込む</button></div>
  <div class="bar" id="wBar"><i></i></div><p class="prog" id="wProg" aria-live="polite"></p>
  <p class="fine">データはすべて合成です。</p></div>`;
document.body.appendChild(W);
let wBusy = false;
function showWelcome(){ W.classList.add('on'); $('wStart').focus(); updateWelcome(); }
function hideWelcome(){ W.classList.remove('on'); ls.set(KEY_SEEN, '1'); }
async function updateWelcome(){
  if (!window.MAAI_BROWSER || wBusy) return;
  const b = $('wStart'); b.disabled = true; $('wBar').classList.add('on');
  const t = $('wProg'); t.textContent = '計算部品を読み込み中（初回 10〜20 秒）… ' + (window.MAAI_BOOT_TEXT || '');
  await siteReady();
  if (!wBusy) { b.disabled = false; $('wBar').classList.remove('on'); t.textContent = ''; }
}
window.addEventListener('maai-boot', e => { if (W.classList.contains('on') && !wBusy && $('wStart').disabled) $('wProg').textContent = '計算部品を読み込み中（初回 10〜20 秒）… ' + e.detail; });
$('wStart').onclick = async () => {
  wBusy = true; $('wStart').disabled = true; $('wOwn').disabled = true; $('wBar').classList.add('on');
  const say = t => $('wProg').textContent = t;
  try {
    say('サイトを読み込み中…'); await siteReady();
    say('サンプルの単線結線図を読んでいる…'); if (!(await ingest())) throw new Error('図面を取り込めなかった。取込タブで確かめてください');
    say('質問の無い開閉器を確認済にして、停止範囲へ進む…'); await sleep(400);
    $('btnConfirmAll').click(); window.go('s1'); hideWelcome();
  } catch (e) { say(String(e.message || e)); $('wOwn').disabled = false; $('wStart').disabled = false; $('wBar').classList.remove('on'); }
  finally { wBusy = false; refresh(); }
};
$('wOwn').onclick = () => { hideWelcome(); window.go('s0'); $('ingestFile').focus(); $('ingestFile').click(); };
W.addEventListener('keydown', e => { if (e.key === 'Escape' && !wBusy) hideWelcome(); });
$('btnHelp').onclick = showWelcome;
if (ls.get(KEY_SEEN) !== '1') showWelcome();

// ---------------------------------------------------------------- 3 分で一周
const cap = $('tourCap'); let stop = false;
const nap = ms => new Promise(r => { const t0 = Date.now(); const id = setInterval(() => { if (stop || Date.now()-t0 >= ms) { clearInterval(id); r(); } }, 100); });
const say = (t, sub) => { cap.innerHTML = t + (sub ? `<small>${sub}</small>` : ''); cap.classList.add('on'); };
function halt(){ stop = true; }
async function tour(){
  tourOn = true; stop = false; busy = true; $('btnTour').textContent = '止める'; refresh();
  const stopper = e => { if (e.target.closest('#btnTour')) return; halt(); };
  document.addEventListener('pointerdown', stopper, true); document.addEventListener('keydown', stopper, true);
  try {
    hideWelcome();
    window.go('s0'); say('サイトを読み込んでいる…'); await siteReady(); if (stop) return;
    say('1 図面取込: 単線結線図の PDF を読んでいる…'); if (!(await ingest()) || stop) return;
    say('1 図面取込: 開閉器を拾い、番号で結んだ。質問の無いものを確認済にする', '接続は人が確認するまで「未確認」のまま。'); await nap(5500); if (stop) return;
    $('btnConfirmAll').click(); await nap(800);
    window.go('s1'); say('2 停止範囲: 66kV 遮断器を取り替える日。電気が流れ込む端すべてで、最初の断路器まで切る', '結線図の緑が停電、赤が充電。'); await nap(1500);
    $('stepsBox').innerHTML = ''; $('btnSteps').click(); await waitFor(() => $('stepsBox').querySelector('.bay'), 30000); if (stop) return;
    say('2 停止範囲: 切る機器と、停電にするための条件が出た', '押すと開閉器の入・切や、取り替える機器の選び直しもできる。'); await nap(6000); if (stop) return;
    window.go('s2'); say('3 重機: 届いて、吊れて、充電部の離隔を保てる一番小さいクレーンを探している…'); await nap(1200);
    $('selectBox').innerHTML = ''; $('verdictBox').innerHTML = ''; $('btnSelect').click(); await waitFor(() => $('selectBox').querySelector('.big, .warn'), 60000); if (stop) return;
    say('3 重機: 一番小さいクラスと据付位置が出た。離隔は engine の計算', '「一つ下のクラスが使えない理由」も出る。'); await nap(5000); if (stop) return;
    if ($('btnAdoptSel')) { $('btnAdoptSel').click(); await waitFor(() => $('verdictBox').querySelector('.bay'), 30000); }
    say('3 重機: この配置を採用した。最小離隔と必要離隔を並べて判定する'); await nap(5000); if (stop) return;
    window.go('s3'); say('4 計画確定: 条件を確かめる。承認時に engine がもう一度判定する'); await nap(4500); if (stop) return;
    if (await approve()) { say('4 計画確定: 承認して、停止範囲図（PDF）と計画を書き出した', '一周おわり。自分の図面は「1 図面取込」から。'); await nap(5000); }
  } finally {
    document.removeEventListener('pointerdown', stopper, true); document.removeEventListener('keydown', stopper, true);
    if (stop) { say('止めました。続きは「次へ」から'); setTimeout(() => cap.classList.remove('on'), 2500); } else setTimeout(() => cap.classList.remove('on'), 1000);
    tourOn = false; busy = false; $('btnTour').textContent = '3 分で一周'; refresh();
  }
}
$('btnTour').onclick = () => { if (tourOn) halt(); else tour(); };

refresh();
