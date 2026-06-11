"""The `9xf app` page — design direction: NIGHT CONSOLE.

A flight-data-recorder for a machine that works while you sleep. Industrial
instrument-panel aesthetic: phosphor amber on near-black ink, all-monospace,
hairline rules, draftsman corner ticks, segmented (never smooth) progress, a
live UTC clock, and the signature element — the PULSE strip, a seismograph of
every iteration (amber tick up = validated, red drop = failed, blinking cursor
= alive right now).

Constraints honored: one self-contained file, no external fonts/assets (fully
offline), prefers-reduced-motion respected, :focus-visible styles, and color is
never the only signal (every state also carries a glyph or word).
"""

APP_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>9XF · NIGHT CONSOLE</title>
<style>
:root{
  --ink:#07090d; --panel:#0b0e14; --panel2:#0d1118; --well:#05070a;
  --line:#1a212c; --line2:#2a3442;
  --amber:#ffb000; --amber2:#cf8e00; --amber-dim:#6e5200;
  --green:#3ddc7a; --red:#ff5257; --blue:#6ab0ff;
  --txt:#d8dfe9; --dim:#8a97a8; --faint:#525e6e;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
}
*{box-sizing:border-box;margin:0}
html,body{height:100%}
body{
  background:var(--ink) radial-gradient(circle,#10151d 1px,transparent 1px);
  background-size:26px 26px;
  color:var(--txt);font:13px/1.55 var(--mono);display:flex;overflow:hidden;
  font-variant-numeric:tabular-nums;
}
::selection{background:var(--amber);color:#000}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-thumb{background:var(--line2)}
::-webkit-scrollbar-track{background:transparent}
:focus-visible{outline:1px solid var(--amber);outline-offset:2px}

/* ---------- primitives ---------- */
.lbl{font-size:9.5px;letter-spacing:.18em;color:var(--faint);text-transform:uppercase}
button{
  font:inherit;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;
  cursor:pointer;color:var(--txt);background:var(--panel2);
  border:1px solid var(--line2);border-radius:0;padding:7px 14px;
}
button:hover{border-color:var(--amber2);color:var(--amber)}
button.primary{background:var(--amber);border-color:var(--amber);color:#000;font-weight:700}
button.primary:hover{background:#ffc23d;color:#000}
button.danger:hover{border-color:var(--red);color:var(--red)}
input,textarea,select{
  font:inherit;font-size:12.5px;background:var(--well);color:var(--txt);
  border:1px solid var(--line2);border-radius:0;padding:8px 10px;width:100%;
}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--amber2)}
textarea{resize:vertical;min-height:72px}
/* draftsman corner ticks — the panel signature */
.frame{position:relative;border:1px solid var(--line);background:var(--panel)}
.frame::before,.frame::after{
  content:"";position:absolute;width:8px;height:8px;pointer-events:none;
  border:0 solid var(--amber-dim);
}
.frame::before{top:-1px;left:-1px;border-top-width:1px;border-left-width:1px}
.frame::after{bottom:-1px;right:-1px;border-bottom-width:1px;border-right-width:1px}

@keyframes blink{0%,55%{opacity:1}56%,100%{opacity:0}}
.cursor{animation:blink 1.1s steps(1) infinite}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

/* ---------- sidebar ---------- */
#side{width:280px;min-width:280px;background:var(--panel);border-right:1px solid var(--line);
  display:flex;flex-direction:column}
#brand{padding:18px 16px 14px;border-bottom:1px solid var(--line)}
#brand .word{font-size:19px;font-weight:700;letter-spacing:.08em;color:var(--txt)}
#brand .word b{color:var(--amber)}
#brand .tag{font-size:9px;letter-spacing:.26em;color:var(--faint);margin-top:3px}
#newBtn{margin:14px;display:block;width:calc(100% - 28px)}
.raillabel{padding:4px 16px 8px;font-size:9.5px;letter-spacing:.18em;color:var(--faint)}
#runlist{flex:1;overflow-y:auto}
.runitem{display:flex;gap:10px;align-items:flex-start;padding:10px 14px;cursor:pointer;
  border-left:2px solid transparent}
.runitem:hover{background:var(--panel2)}
.runitem.active{background:var(--panel2);border-left-color:var(--amber)}
.led{width:8px;height:8px;margin-top:5px;background:var(--faint);flex:none}
.led.running{background:var(--green);box-shadow:0 0 8px rgba(61,220,122,.7)}
.led.finished{background:var(--amber);box-shadow:0 0 7px rgba(255,176,0,.55)}
.led.failed{background:var(--red)}
.led.stale{background:var(--amber2)}
.runitem .g{font-size:12px;color:var(--txt);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;max-width:212px}
.runitem .s{font-size:10px;letter-spacing:.08em;color:var(--faint);margin-top:3px;text-transform:uppercase}
#railfoot{border-top:1px solid var(--line);padding:10px 16px;display:flex;
  justify-content:space-between;font-size:10px;letter-spacing:.12em;color:var(--faint)}
#clock{color:var(--dim)}

/* ---------- header: readouts + pulse ---------- */
#main{flex:1;display:flex;flex-direction:column;min-width:0}
#top{border-bottom:1px solid var(--line);background:var(--panel)}
#readouts{display:flex;align-items:stretch}
.cell{padding:12px 16px;border-right:1px solid var(--line);min-width:0}
.cell .val{margin-top:4px;font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cell.goal{flex:1}
.cell.iter .val{font-size:24px;line-height:1.1;color:var(--amber);font-weight:700;letter-spacing:.04em}
.cell.iter .cap{color:var(--faint);font-size:12px;font-weight:400}
.segs{display:flex;gap:3px;margin-top:7px;flex-wrap:wrap;max-width:220px}
.seg{width:9px;height:9px;background:var(--line2)}
.seg.done{background:var(--amber)}
.seg.cur{background:var(--amber-dim);box-shadow:inset 0 0 0 1px var(--amber)}
.seg.def{background:var(--red);opacity:.55}
.statusword{font-size:12.5px;letter-spacing:.14em;text-transform:uppercase}
.statusword.running{color:var(--green)}
.statusword.finished{color:var(--amber)}
.statusword.failed{color:var(--red)}
.statusword.stale{color:var(--amber2)}
.statusword.stopped,.statusword.never{color:var(--dim)}
.cell.actions{display:flex;align-items:center;gap:8px;border-right:0}
#pulsewrap{padding:6px 16px 9px;border-top:1px solid var(--line);background:var(--well)}
#pulsewrap .lbl{display:block;margin-bottom:2px}
#pulse{display:block;width:100%}

/* ---------- panes ---------- */
#panes{flex:1;display:flex;min-height:0}
.panehead{padding:9px 16px;border-bottom:1px solid var(--line);font-size:9.5px;
  letter-spacing:.18em;color:var(--faint);text-transform:uppercase;display:flex;
  justify-content:space-between;align-items:center;gap:8px;background:var(--panel)}
#chatwrap{flex:1.08;display:flex;flex-direction:column;min-width:0}
#chat{flex:1;overflow-y:auto;padding:18px 22px;scroll-behavior:smooth}
#statusbar{display:none;border-top:1px solid var(--line);background:var(--panel);
  padding:9px 16px;font-size:11.5px;color:var(--dim);align-items:center;gap:10px}
#statusbar .cursor{color:var(--amber);font-weight:700}
#statusbar b{color:var(--txt);letter-spacing:.1em}

/* ---------- transcript records ---------- */
.rec{border:1px solid var(--line);border-left:2px solid var(--line2);
  background:var(--panel);margin:0 auto 12px;max-width:820px}
.rec.ok{border-left-color:var(--green)}
.rec.bad{border-left-color:var(--red)}
.rec.clickable{cursor:pointer}
.rec.clickable:hover{background:var(--panel2)}
.rec.selected{border-color:var(--amber2);border-left-color:var(--amber)}
.rechead{display:flex;align-items:center;gap:10px;padding:7px 12px;
  border-bottom:1px solid var(--line);font-size:10px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--dim);flex-wrap:wrap}
.recno{color:var(--amber);font-weight:700}
.recmode{color:var(--blue)}
.flag{padding:1px 6px;border:1px solid var(--line2);color:var(--dim);font-size:9px}
.flag.warn{border-color:var(--amber2);color:var(--amber)}
.flag.bad{border-color:var(--red);color:var(--red)}
.flag.good{border-color:var(--green);color:var(--green)}
.verdict{margin-left:auto;font-weight:700;letter-spacing:.12em}
.verdict.ok{color:var(--green)}
.verdict.bad{color:var(--red)}
.recline{display:flex;gap:12px;padding:8px 12px 0}
.recline:last-child{padding-bottom:10px}
.recline .lbl{flex:none;width:38px;padding-top:2px}
.recline .txt{font-size:12.5px;word-break:break-word;min-width:0}
.recline.plan .txt{color:var(--txt)}
.recline.execl .txt{color:var(--dim)}
.files{display:flex;flex-wrap:wrap;gap:6px;padding:8px 12px 0 62px}
.file{font-size:10.5px;border:1px solid var(--line2);padding:1px 7px;color:var(--blue)}
.errblock{margin:8px 12px 0 62px;border-left:2px solid var(--red);padding:4px 10px;
  font-size:11px;color:var(--red);word-break:break-word;background:var(--well)}
.recmeta{display:flex;gap:14px;padding:8px 12px 10px 62px;font-size:10px;
  letter-spacing:.1em;color:var(--faint);text-transform:uppercase}
.recmeta .hash{color:var(--amber2)}

/* harness events */
.evt{display:flex;align-items:center;gap:12px;max-width:820px;margin:0 auto 12px;
  color:var(--faint);font-size:10px;letter-spacing:.16em;text-transform:uppercase}
.evt::before,.evt::after{content:"";flex:1;height:1px;background:var(--line)}
.evt b{color:var(--dim)}
.evt.finish{color:var(--amber)}
.evt.finish::before,.evt.finish::after{background:var(--amber-dim)}
.evt.finish b{color:var(--amber)}

/* empty state */
.empty{margin:auto;text-align:center;padding:60px 30px;max-width:560px}
.empty .schem{font-size:11px;letter-spacing:.14em;color:var(--faint);margin-bottom:26px}
.empty .schem b{color:var(--amber)}
.empty h2{font-size:22px;letter-spacing:.12em;margin-bottom:14px;color:var(--txt);
  text-transform:uppercase}
.empty h2 b{color:var(--amber)}
.empty p{color:var(--dim);font-size:12.5px;margin-bottom:28px}

/* ---------- diff register ---------- */
#diffpane{flex:1;border-left:1px solid var(--line);display:flex;flex-direction:column;
  min-width:0;background:var(--well)}
#diffTitle .hash{color:var(--amber)}
#diff{flex:1;overflow:auto;padding:14px 16px;font-size:11.5px;line-height:1.6;
  white-space:pre;color:var(--dim)}
#diff .add{color:var(--green)}
#diff .del{color:var(--red)}
#diff .hunk{color:var(--amber2)}
#diff .file{color:var(--blue);font-weight:700}
#diff .ctx{color:var(--faint)}

/* ---------- modal ---------- */
#overlay{position:fixed;inset:0;background:rgba(2,3,5,.7);display:none;
  align-items:center;justify-content:center;z-index:10}
#overlay.show{display:flex}
.modal{width:560px;max-width:94vw;max-height:90vh;overflow-y:auto;padding:22px}
.modal h2{font-size:13px;letter-spacing:.22em;text-transform:uppercase;
  color:var(--amber);margin-bottom:20px}
.field{margin-bottom:16px}
.field .lbl{display:block;margin-bottom:7px}
.row{display:flex;gap:10px}.row>*{flex:1}
.seg-switch{display:flex;border:1px solid var(--line2)}
.seg-switch button{flex:1;border:0;background:var(--well)}
.seg-switch button.on{background:var(--amber);color:#000;font-weight:700}
.modal .actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}
#browser{border:1px solid var(--line2);max-height:200px;overflow-y:auto;
  margin-top:8px;font-size:11.5px;background:var(--well)}
#browser .bi{padding:6px 10px;cursor:pointer;display:flex;gap:8px;align-items:baseline}
#browser .bi:hover{background:var(--panel2);color:var(--amber)}
#browser .bi .tag{color:var(--amber2);font-size:9px;letter-spacing:.12em}
.formerr{color:var(--red);font-size:11px;margin-top:8px;min-height:14px}
.hint{color:var(--faint);font-size:10.5px;margin-top:6px}
</style></head><body>

<aside id="side">
  <div id="brand">
    <div class="word">9<b>XF</b><span class="cursor" style="color:var(--amber)">▮</span></div>
    <div class="tag">NIGHT CONSOLE · AUTONOMOUS LOOPS</div>
  </div>
  <button id="newBtn" class="primary" aria-label="New session">+ New session</button>
  <div class="raillabel">Sessions</div>
  <div id="runlist" role="list"></div>
  <div id="railfoot"><span id="clock">--:--:--</span><span>LOCAL · 127.0.0.1</span></div>
</aside>

<main id="main">
  <header id="top">
    <div id="readouts">
      <div class="cell goal"><span class="lbl">Goal</span><div class="val" id="topGoal">—</div></div>
      <div class="cell iter"><span class="lbl">Iter</span>
        <div class="val" id="iterRead">···<span class="cap"></span></div></div>
      <div class="cell tasks"><span class="lbl">Tasks</span>
        <div class="val" id="taskRead">—</div><div class="segs" id="taskSegs"></div></div>
      <div class="cell"><span class="lbl">Status</span>
        <div class="val statusword never" id="topPill">no run</div></div>
      <div class="cell actions">
        <button id="stopBtn" class="danger" style="display:none">Stop</button>
        <button id="resumeBtn" class="primary" style="display:none">Resume</button>
      </div>
    </div>
    <div id="pulsewrap" style="display:none"><span class="lbl">Pulse — one tick per iteration</span><div id="pulse"></div></div>
  </header>

  <div id="panes">
    <section id="chatwrap" aria-label="transcript">
      <div class="panehead"><span>Transcript</span><span id="livehint"></span></div>
      <div id="chat">
        <div class="empty">
          <div class="schem">[ PLAN ] → [ WRITE ] → [ VALIDATE ] → [ <b>REPAIR</b> ] → [ COMMIT ] ⟲</div>
          <h2>Night shift<br>for your <b>code</b></h2>
          <p>Set a goal. Pick a folder. A local model works the loop —
          verified, committed, checkpointed — while you sleep.</p>
          <button class="primary" onclick="openNew()">Start a session</button>
        </div>
      </div>
      <div id="statusbar"></div>
    </section>
    <section id="diffpane" aria-label="diff register">
      <div class="panehead"><span id="diffTitle">Diff register</span><span id="diffPin"></span></div>
      <div id="diff"><span class="ctx">select an iteration record to inspect its commit</span></div>
    </section>
  </div>
</main>

<div id="overlay" role="dialog" aria-modal="true"><div class="modal frame">
  <h2>New session</h2>
  <div class="field"><span class="lbl">Folder</span>
    <div class="row"><input id="fDir" placeholder="/Users/you/runs/my-tool" autocomplete="off">
      <button style="flex:0 0 auto" onclick="pickFolder()">Browse</button></div>
    <div id="browser" style="display:none"></div>
    <div class="hint">a new or empty folder — or an existing 9xf run to continue</div>
  </div>
  <div class="field"><span class="lbl">Goal — the unchanging north star</span>
    <textarea id="fGoal" placeholder="Write a CLI tool that organizes files in a directory by type"></textarea></div>
  <div class="field"><span class="lbl">Mode</span>
    <div class="seg-switch" role="radiogroup">
      <button id="mReg" class="on" onclick="setMode('')">Regular</button>
      <button id="mOver" onclick="setMode('overnight')">Overnight · max search</button>
    </div></div>
  <div class="row">
    <div class="field"><span class="lbl">Model</span><select id="fModel"></select></div>
    <div class="field"><span class="lbl">Budget</span>
      <div class="row">
        <input id="fIters" type="number" placeholder="iters" min="1">
        <input id="fHours" type="number" placeholder="hours" step="0.5" min="0.5">
      </div></div>
  </div>
  <div class="formerr" id="fErr" role="alert"></div>
  <div class="actions">
    <button onclick="closeNew()">Cancel</button>
    <button class="primary" onclick="startSession()">Start</button>
  </div>
</div></div>

<script>
const $ = id => document.getElementById(id);
const esc = s => String(s??'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pad3 = n => String(n).padStart(3,'0');
let current = null, pinnedCommit = null, lastDiffCommit = null, lastRender = '', lastRail = '';

/* instrument clock */
setInterval(() => { $('clock').textContent = new Date().toISOString().slice(11,19) + ' UTC'; }, 1000);

/* ---------- sidebar ---------- */
function ledClass(r){
  if (r.finished) return 'finished';
  if (r.status === 'running') return 'running';
  if (r.status === 'failed') return 'failed';
  if (r.status === 'stale') return 'stale';
  return '';
}
async function tickRuns(){
  let runs; try{ runs = await (await fetch('/api/runs')).json(); }catch(e){ return; }
  /* re-render only on change — innerHTML swaps destroy elements mid-click */
  const html = runs.map(r => `
    <div class="runitem ${current===r.dir?'active':''}" role="listitem" tabindex="0"
         onclick="selectRun('${esc(r.dir)}')" onkeydown="if(event.key==='Enter')selectRun('${esc(r.dir)}')">
      <i class="led ${ledClass(r)}" aria-hidden="true"></i>
      <div><div class="g">${esc(r.goal)}</div>
      <div class="s">${r.finished?'finished':esc(r.status)} · iter ${r.iteration}${r.tasks_total?` · ${r.tasks_done}/${r.tasks_total}`:''}</div></div>
    </div>`).join('') ||
    '<div class="s" style="padding:12px 16px;color:var(--faint);font-size:11px">no sessions on record</div>';
  if (html !== lastRail){ $('runlist').innerHTML = html; lastRail = html; }
}
function selectRun(dir){ current = dir; pinnedCommit = null; lastRender = ''; lastRail = ''; tickRun(); tickRuns(); }

/* ---------- pulse strip: the run's life as a seismograph ---------- */
function pulseSvg(entries, running){
  const iters = entries.filter(e => e.event === 'iteration').slice(-140);
  const step = 8, w = Math.max(600, iters.length*step + 26), h = 30, base = 19;
  const parts = [`<line x1="0" y1="${base}" x2="${w}" y2="${base}" stroke="#1a212c"/>`];
  iters.forEach((e, i) => {
    const x = 8 + i*step;
    parts.push(e.ok
      ? `<line x1="${x}" y1="${base}" x2="${x}" y2="5" stroke="#ffb000" stroke-width="2"><title>iter ${e.iteration}: validated</title></line>`
      : `<line x1="${x}" y1="${base}" x2="${x}" y2="${h-2}" stroke="#ff5257" stroke-width="2"><title>iter ${e.iteration}: failed</title></line>`);
  });
  if (running) parts.push(`<rect class="cursor" x="${8 + iters.length*step}" y="8" width="5" height="11" fill="#ffb000"/>`);
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="xMinYMid meet"
    role="img" aria-label="iteration pulse: ${iters.filter(e=>e.ok).length} passed, ${iters.filter(e=>!e.ok).length} failed">${parts.join('')}</svg>`;
}

/* ---------- task segments ---------- */
function segsHtml(tasks){
  return tasks.slice(0, 28).map(t => {
    const c = t.status==='x' ? 'done' : t.status==='!' ? 'def' : t.status==='~' ? 'cur' : '';
    return `<i class="seg ${c}" title="T${t.num} ${esc(t.text)}"></i>`;
  }).join('');
}

/* ---------- transcript records ---------- */
function flags(e){
  const f = [];
  if (e.task_id) f.push(`<span class="flag">T${e.task_id}</span>`);
  if (e.repairs) f.push(`<span class="flag ${e.ok?'good':'bad'}">repair×${e.repairs}</span>`);
  if (e.candidates > 1) f.push(`<span class="flag">best of ${e.candidates}</span>`);
  if (e.critic === 'REVISE') f.push(`<span class="flag warn">critic revise</span>`);
  if (e.stuck.length) f.push(`<span class="flag warn">stuck ${esc(e.stuck.join('+'))}</span>`);
  if (e.regression) f.push(`<span class="flag bad">regression</span>`);
  if (e.acceptance === true) f.push(`<span class="flag good">acceptance ✓</span>`);
  if (e.acceptance === false) f.push(`<span class="flag warn">acceptance ✗</span>`);
  if (e.overflow) f.push(`<span class="flag warn">ctx overflow</span>`);
  return f.join('');
}
function entryHtml(e){
  if (e.event === 'iteration'){
    const sel = pinnedCommit && e.commit === pinnedCommit ? 'selected' : '';
    return `<article class="rec ${e.ok?'ok':'bad'} ${e.commit?'clickable':''} ${sel}"
      ${e.commit?`onclick="loadDiff('${esc(e.commit)}', true)"`:''}>
      <div class="rechead">
        <span class="recno">${pad3(e.iteration)}</span>
        <span class="recmode">${esc(e.mode)}</span>
        ${flags(e)}
        <span class="verdict ${e.ok?'ok':'bad'}">${e.ok?'✓ PASS':'✗ FAIL'}</span>
      </div>
      <div class="recline plan"><span class="lbl">Plan</span><span class="txt">${esc(e.subtask)}</span></div>
      <div class="recline execl"><span class="lbl">Exec</span><span class="txt">${esc(e.summary||'(no summary)')}</span></div>
      ${e.files.length?`<div class="files">${e.files.map(f=>`<span class="file">${esc(f)}</span>`).join('')}</div>`:''}
      ${e.tool_runs.map(t=>`<div class="recline execl"><span class="lbl">Tool</span><span class="txt">${esc(t.name)} → ${esc(t.result)}</span></div>`).join('')}
      ${e.errors.length?`<div class="errblock">${e.errors.map(x=>esc(x)).join('<br>')}</div>`:''}
      <div class="recmeta">${e.commit?`<span class="hash">${esc(e.commit)}</span><span>click to inspect diff</span>`:'<span>no commit</span>'}</div>
    </article>`;
  }
  if (e.event === 'finished') return `<div class="evt finish"><b>◉ goal complete</b> ${esc(e.summary)}</div>`;
  if (e.event === 'shutdown') return `<div class="evt">■ stopped — <b>${esc(e.summary)}</b></div>`;
  if (e.event === 'startup')  return `<div class="evt">▶ ${esc(e.summary)}</div>`;
  return `<div class="evt"><b>${esc(e.event)}</b> ${esc(e.summary)}</div>`;
}

async function tickRun(){
  if (!current) return;
  let r; try{ r = await (await fetch('/api/run?dir='+encodeURIComponent(current))).json(); }catch(e){ return; }
  if (r.error) return;
  $('topGoal').textContent = r.goal;
  $('iterRead').innerHTML = `${pad3(r.iteration)}<span class="cap"> /${r.cap}</span>`;
  $('taskRead').textContent = r.tasks_total ? `${r.tasks_done} of ${r.tasks_total} done` : '—';
  $('taskSegs').innerHTML = segsHtml(r.tasks || []);
  const status = r.finished ? 'finished' : (r.status === 'never started' ? 'never' : r.status);
  $('topPill').textContent = r.finished ? '◉ finished' : r.status;
  $('topPill').className = 'val statusword ' + status;
  const running = r.status === 'running';
  $('stopBtn').style.display = running && !r.stop_present ? '' : 'none';
  $('resumeBtn').style.display = (!running && !r.finished) ? '' : 'none';
  $('pulsewrap').style.display = r.entries.some(e => e.event === 'iteration') ? '' : 'none';
  $('pulse').innerHTML = pulseSvg(r.entries, running);

  const sb = $('statusbar');
  if (running){
    sb.style.display = 'flex';
    sb.innerHTML = `<span class="cursor">▮</span><span><b>${esc((r.mode||'…').toUpperCase())}</b> — iter ${r.iteration}/${r.cap}${r.live_subtask?` — ${esc(r.live_subtask)}`:''}${r.stop_present?' — stopping at boundary':''}</span>`;
    $('livehint').textContent = 'live · polling 2s';
  } else { sb.style.display = 'none'; $('livehint').textContent = ''; }

  const html = r.entries.map(entryHtml).join('') ||
    '<div class="empty"><p>spinning up…</p></div>';
  if (html !== lastRender){
    const chat = $('chat');
    const nearBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 160;
    chat.innerHTML = html;
    if (nearBottom) chat.scrollTop = chat.scrollHeight;
    lastRender = html;
    if (!pinnedCommit){
      const commits = r.entries.filter(e => e.commit && e.event === 'iteration');
      if (commits.length) loadDiff(commits[commits.length-1].commit, false);
    }
  }
}

/* ---------- diff register ---------- */
function colorize(text){
  return text.split('\n').map(l => {
    const e = esc(l);
    if (l.startsWith('diff --git') || l.startsWith('commit')) return `<span class="file">${e}</span>`;
    if (l.startsWith('+++') || l.startsWith('---')) return `<span class="file">${e}</span>`;
    if (l.startsWith('@@')) return `<span class="hunk">${e}</span>`;
    if (l.startsWith('+')) return `<span class="add">${e}</span>`;
    if (l.startsWith('-')) return `<span class="del">${e}</span>`;
    return `<span class="ctx">${e}</span>`;
  }).join('\n');
}
async function loadDiff(commit, pin){
  if (pin){ pinnedCommit = commit; lastRender = ''; }
  if (commit === lastDiffCommit && !pin) return;
  lastDiffCommit = commit;
  $('diffTitle').innerHTML = `Diff register · <span class="hash">${esc(commit)}</span>`;
  $('diffPin').innerHTML = pin ? `<button onclick="unpin()" style="padding:2px 8px;font-size:9px">⟲ follow latest</button>` : '';
  let r; try{ r = await (await fetch(`/api/diff?dir=${encodeURIComponent(current)}&commit=${commit}`)).json(); }catch(e){ return; }
  $('diff').innerHTML = r.error ? `<span class="del">${esc(r.error)}</span>` : colorize(r.diff);
}
function unpin(){ pinnedCommit = null; lastRender = ''; $('diffPin').innerHTML = ''; tickRun(); }

/* ---------- controls ---------- */
$('stopBtn').onclick = async () => {
  await fetch('/api/stop', {method:'POST', body: JSON.stringify({dir: current})}); tickRun();
};
$('resumeBtn').onclick = async () => {
  const r = await (await fetch('/api/start', {method:'POST', body: JSON.stringify({dir: current})})).json();
  if (r.error) alert(r.error); tickRun();
};

/* ---------- new session modal ---------- */
let mode = '';
function setMode(m){ mode = m; $('mReg').className = m ? '' : 'on'; $('mOver').className = m ? 'on' : ''; }
function openNew(){ $('overlay').classList.add('show'); $('fErr').textContent=''; loadModels(); $('fGoal').focus(); }
function closeNew(){ $('overlay').classList.remove('show'); $('browser').style.display='none'; }
$('newBtn').onclick = openNew;
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeNew(); });
async function loadModels(){
  try{
    const m = await (await fetch('/api/models')).json();
    $('fModel').innerHTML = m.models.map(x => `<option ${x===m.default?'selected':''}>${esc(x)}</option>`).join('');
  }catch(e){}
}
async function pickFolder(){
  if (window.ninexf && window.ninexf.pickFolder){     /* electron: native dialog */
    const p = await window.ninexf.pickFolder();
    if (p) $('fDir').value = p;
    return;
  }
  browseTo($('fDir').value || '');                    /* browser: server-side picker */
}
async function browseTo(path){
  let r; try{ r = await (await fetch('/api/browse?path='+encodeURIComponent(path))).json(); }catch(e){ return; }
  $('fDir').value = r.path;
  const b = $('browser'); b.style.display = 'block';
  b.innerHTML = (r.parent?`<div class="bi" onclick="browseTo('${esc(r.parent)}')">⬑ ..</div>`:'') +
    r.dirs.map(d=>`<div class="bi" onclick="browseTo('${esc(d.path)}')">▸ ${esc(d.name)} ${d.is_run?'<span class="tag">9XF RUN</span>':''}</div>`).join('') +
    `<div class="bi" onclick="$('browser').style.display='none'"><b style="color:var(--amber)">✓ use this folder</b>&nbsp;— or append a new subfolder name above</div>`;
}
async function startSession(){
  const payload = {
    dir: $('fDir').value.trim(), goal: $('fGoal').value.trim(), preset: mode,
    model: $('fModel').value || null,
    iterations: $('fIters').value ? parseInt($('fIters').value) : null,
    hours: $('fHours').value ? parseFloat($('fHours').value) : null,
  };
  if (!payload.dir){ $('fErr').textContent = 'ERR — pick a folder first'; return; }
  if (!payload.goal){ $('fErr').textContent = 'ERR — write a goal; one sentence is enough'; return; }
  $('fErr').textContent = 'igniting…';
  let r; try{ r = await (await fetch('/api/start', {method:'POST', body: JSON.stringify(payload)})).json(); }
  catch(e){ $('fErr').textContent = 'ERR — server unreachable'; return; }
  if (r.error){ $('fErr').textContent = 'ERR — ' + r.error; return; }
  closeNew(); selectRun(r.dir);
}

tickRuns(); setInterval(tickRuns, 2500); setInterval(tickRun, 2000);
</script></body></html>"""
