"""The `9xf app` page — design direction: quiet, warm, minimal.

A calm dark workspace for a machine that works while you sleep. Warm near-black
neutrals with a single muted terracotta accent (the Claude palette), system
sans-serif for prose, monospace reserved for numbers/hashes/diffs, soft rounded
surfaces instead of rules and boxes, and one signature element — the PULSE
strip, a seismograph of every iteration (green tick up = validated, red drop =
failed, blinking cursor = alive right now).

Constraints honored: one self-contained file, no external fonts/assets (fully
offline), prefers-reduced-motion respected, :focus-visible styles, and color is
never the only signal (every state also carries a glyph or word).
"""

APP_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>9xf</title>
<style>
:root{
  --ink:#161513; --panel:#1e1d1a; --panel2:#262420; --well:#110f0e;
  --line:#2a2825; --line2:#3a3733;
  --amber:#d97757; --amber2:#b05f43; --amber-dim:#5c3527;
  --green:#97b58c; --red:#cd6f63; --blue:#9db4cd;
  --txt:#e8e6e1; --dim:#9b9892; --faint:#6e6b64;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
}
*{box-sizing:border-box;margin:0}
html,body{height:100%}
body{
  background:var(--ink);
  color:var(--txt);font:13.5px/1.6 var(--sans);display:flex;overflow:hidden;
  font-variant-numeric:tabular-nums;
  -webkit-font-smoothing:antialiased;
}
::selection{background:var(--amber);color:#fff}
::-webkit-scrollbar{width:8px;height:8px}
::-webkit-scrollbar-thumb{background:var(--line2);border-radius:4px}
::-webkit-scrollbar-track{background:transparent}
:focus-visible{outline:1px solid var(--amber);outline-offset:2px}

/* ---------- primitives ---------- */
.lbl{font-size:11px;color:var(--faint)}
button{
  font:inherit;font-size:12.5px;cursor:pointer;color:var(--txt);
  background:transparent;border:1px solid var(--line2);border-radius:8px;
  padding:6px 14px;transition:background .12s,border-color .12s,color .12s;
}
button:hover{background:var(--panel2);border-color:var(--faint)}
button:active{transform:translateY(1px)}
button:disabled{opacity:.45;cursor:default;transform:none}
button.primary{background:var(--amber);border-color:var(--amber);color:#fff;font-weight:600}
button.primary:hover{background:#e08763;border-color:#e08763;color:#fff}
button.danger:hover{border-color:var(--red);color:var(--red);background:transparent}
input,textarea,select{
  font:inherit;font-size:13px;background:var(--well);color:var(--txt);
  border:1px solid var(--line2);border-radius:8px;padding:8px 12px;width:100%;
}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--amber2)}
textarea{resize:vertical;min-height:72px}
.frame{position:relative;border:1px solid var(--line);border-radius:14px;background:var(--panel)}

@keyframes blink{0%,55%{opacity:1}56%,100%{opacity:0}}
.cursor{animation:blink 1.1s steps(1) infinite}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

/* ---------- sidebar ---------- */
#side{width:272px;min-width:272px;background:var(--well);
  display:flex;flex-direction:column;transition:width .16s ease,min-width .16s ease}
#side.collapsed{width:0;min-width:0;overflow:hidden}
#brand{padding:20px 18px 8px}
#brand .word{font-size:16px;font-weight:600;color:var(--txt)}
#brand .word b{color:var(--amber)}
#brand .tag{font-size:11px;color:var(--faint);margin-top:1px}
#newBtn{margin:14px 14px 6px;display:block;width:calc(100% - 28px)}
.raillabel{padding:12px 18px 4px;font-size:11px;color:var(--faint)}
#runlist{flex:1;overflow-y:auto;padding:0 8px}
.runitem{display:flex;gap:10px;align-items:flex-start;padding:8px 10px;cursor:pointer;
  border-radius:10px;margin-bottom:1px}
.runitem:hover{background:var(--panel)}
.runitem.active{background:var(--panel2)}
.led{width:7px;height:7px;margin-top:6px;border-radius:50%;background:var(--faint);flex:none}
.led.running{background:var(--green)}
.led.finished{background:var(--amber)}
.led.failed{background:var(--red)}
.led.stale{background:var(--amber2)}
.runitem .g{font-size:13px;color:var(--txt);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;max-width:206px}
.runitem .s{font-size:11px;color:var(--faint);margin-top:1px}
#railfoot{padding:10px 18px;display:flex;
  justify-content:space-between;font:10.5px var(--mono);color:var(--faint)}
#clock{color:var(--dim)}

/* ---------- header: readouts + pulse ---------- */
#main{flex:1;display:flex;flex-direction:column;min-width:0}
#top{border-bottom:1px solid var(--line)}
#readouts{display:flex;align-items:center;gap:28px;padding:14px 22px 10px}
.cell{min-width:0}
.cell .val{margin-top:1px;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cell.goal{flex:1}
.cell.goal .val{font-size:14px;font-weight:500}
.cell.iter .val{font:600 16px/1.3 var(--mono);color:var(--txt)}
.cell.iter .cap{color:var(--faint);font-size:12px;font-weight:400}
.segs{display:flex;gap:3px;margin-top:5px;flex-wrap:wrap;max-width:220px}
.seg{width:8px;height:8px;border-radius:2px;background:var(--line2)}
.seg.done{background:var(--green)}
.seg.cur{background:var(--amber)}
.seg.def{background:var(--red);opacity:.55}
.statusword{font-size:13px}
.statusword.running{color:var(--green)}
.statusword.finished{color:var(--amber)}
.statusword.failed{color:var(--red)}
.statusword.stale{color:var(--amber2)}
.statusword.stopped,.statusword.never{color:var(--dim)}
.cell.actions{display:flex;align-items:center;gap:8px}
#pulsewrap{padding:0 22px 10px}
#pulsewrap .lbl{display:block;margin-bottom:2px}
#pulse{display:block;width:100%}

/* ---------- panes ---------- */
#panes{flex:1;display:flex;min-height:0}
.panehead{padding:12px 22px 4px;font-size:11px;color:var(--faint);display:flex;
  justify-content:space-between;align-items:center;gap:8px}
#chatwrap{flex:1;display:flex;flex-direction:column;min-width:280px}
.gutter{flex:none;width:7px;cursor:col-resize;background:transparent;
  border-left:1px solid var(--line);transition:border-color .12s}
.gutter:hover,.gutter.drag{border-left-color:var(--amber2)}
/* icon button: quiet, square, for chrome controls (collapse, etc.) */
.iconbtn{border:0;background:transparent;color:var(--dim);padding:5px 7px;
  border-radius:7px;font-size:14px;line-height:1}
.iconbtn:hover{background:var(--panel2);color:var(--txt)}
#chat{flex:1;overflow-y:auto;padding:12px 22px 18px;scroll-behavior:smooth}
#statusbar{display:none;border-top:1px solid var(--line);
  padding:9px 22px;font-size:12.5px;color:var(--dim);align-items:center;gap:10px}
#statusbar .cursor{color:var(--amber);font-weight:700}
#statusbar b{color:var(--txt)}

/* ---------- transcript records: collapsible cards ---------- */
.rec{background:var(--panel);border-radius:10px;margin:0 auto 6px;max-width:740px;
  overflow:hidden}
.rec.selected{box-shadow:0 0 0 1px var(--amber2)}
.rechead{display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;
  font-size:11.5px;color:var(--dim);user-select:none}
.rechead:hover{background:var(--panel2)}
.chev{flex:none;color:var(--faint);font-size:9px;width:9px;transition:transform .15s}
.rec.open .chev{transform:rotate(90deg)}
.recno{flex:none;font:600 11.5px var(--mono);color:var(--dim)}
.recmode{flex:none;color:var(--faint)}
.rectitle{flex:1;min-width:0;color:var(--txt);font-size:12.5px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.flag{flex:none;padding:1px 8px;border-radius:99px;background:var(--panel2);color:var(--dim);font-size:10.5px}
.flag.warn{background:rgba(217,119,87,.13);color:var(--amber)}
.flag.bad{background:rgba(205,111,99,.13);color:var(--red)}
.flag.good{background:rgba(151,181,140,.13);color:var(--green)}
.dotv{flex:none;width:7px;height:7px;border-radius:50%;background:var(--dim)}
.dotv.ok{background:var(--green)}
.dotv.bad{background:var(--red)}
.recbody{display:none;padding:2px 14px 12px 33px}
.rec.open .recbody{display:block}
.recline{display:flex;gap:10px;padding-top:8px}
.recline .lbl{flex:none;width:34px;font-size:11px;color:var(--faint);padding-top:1px}
.recline .txt{font-size:12.5px;line-height:1.55;word-break:break-word;min-width:0}
.recline.plan .txt{color:var(--txt)}
.recline.execl .txt{color:var(--dim)}
.files{display:flex;flex-wrap:wrap;gap:6px;padding:8px 0 0 44px}
.file{font:11px var(--mono);background:var(--panel2);border-radius:6px;padding:2px 8px;color:var(--blue)}
.errblock{margin:8px 0 0 44px;border-radius:8px;padding:7px 10px;
  font:11.5px/1.5 var(--mono);color:var(--red);word-break:break-word;
  background:rgba(205,111,99,.08)}
.recmeta{display:flex;gap:14px;padding:10px 0 0 44px;font-size:11px;color:var(--faint)}
.recmeta .hash{font-family:var(--mono);color:var(--amber2);cursor:pointer}
.recmeta .hash:hover{color:var(--amber);text-decoration:underline}

/* activity stream — lightweight, part of the flow (not floating dividers) */
.act{display:flex;align-items:center;gap:9px;max-width:740px;margin:0 auto;
  padding:3px 14px;color:var(--faint);font-size:11.5px}
.act .k{color:var(--dim);font-weight:500}
.act::before{content:"";flex:none;width:4px;height:4px;border-radius:50%;
  background:var(--line2)}

/* milestones */
.evt{display:flex;align-items:center;justify-content:center;gap:8px;max-width:740px;
  margin:8px auto;color:var(--faint);font-size:11.5px;text-align:center}
.evt b{color:var(--dim)}
.evt.finish{color:var(--amber)}
.evt.finish b{color:var(--amber)}

/* empty state */
.empty{margin:auto;text-align:center;padding:60px 30px;max-width:480px}
.empty h2{font-size:21px;font-weight:600;margin-bottom:12px;color:var(--txt);line-height:1.3}
.empty h2 b{color:var(--amber)}
.empty p{color:var(--dim);font-size:13.5px;margin-bottom:26px}

/* ---------- diff register ---------- */
#diffpane{flex:none;width:46%;min-width:240px;display:flex;flex-direction:column;
  min-height:0;background:var(--well)}
#diffTitle .hash{font-family:var(--mono);color:var(--amber)}
#diff{flex:1;overflow:auto;padding:10px 22px 16px;font:11.5px/1.6 var(--mono);
  white-space:pre;color:var(--dim)}
#diff .add{color:var(--green)}
#diff .del{color:var(--red)}
#diff .hunk{color:var(--amber2)}
#diff .file{font:inherit;background:transparent;border-radius:0;padding:0;
  color:var(--blue);font-weight:700}
#diff .ctx{color:var(--faint)}

/* ---------- modal ---------- */
#overlay,#copyOverlay{position:fixed;inset:0;background:rgba(2,3,5,.7);display:none;
  align-items:center;justify-content:center;z-index:10}
#overlay.show,#copyOverlay.show{display:flex}
.modal{width:560px;max-width:94vw;max-height:90vh;overflow-y:auto;padding:26px;border-radius:14px}
.modal h2{font-size:16px;font-weight:600;color:var(--txt);margin-bottom:18px}
.field{margin-bottom:16px}
.field .lbl{display:block;margin-bottom:6px}
.row{display:flex;gap:10px}.row>*{flex:1}
.seg-switch{display:flex;border:1px solid var(--line2);border-radius:8px;overflow:hidden}
.seg-switch button{flex:1;border:0;border-radius:0;background:transparent}
.seg-switch button.on{background:var(--amber);color:#fff;font-weight:600}
.modal .actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}
#browser{border:1px solid var(--line2);border-radius:8px;max-height:200px;overflow-y:auto;
  margin-top:8px;font-size:12.5px;background:var(--well)}
#browser .bi{padding:6px 12px;cursor:pointer;display:flex;gap:8px;align-items:baseline}
#browser .bi:hover{background:var(--panel2);color:var(--amber)}
#browser .bi .tag{color:var(--amber2);font-size:10px}
.formerr{color:var(--red);font-size:12px;margin-top:8px;min-height:14px}
.hint{color:var(--faint);font-size:11.5px;margin-top:6px}
</style></head><body>

<aside id="side">
  <div id="brand">
    <div class="word">9<b>xf</b></div>
    <div class="tag">autonomous coding loops</div>
  </div>
  <button id="newBtn" class="primary" aria-label="New session">+ New session</button>
  <div class="raillabel">Sessions</div>
  <div id="runlist" role="list"></div>
  <div id="railfoot"><span id="clock">--:--:--</span><span>LOCAL · 127.0.0.1</span></div>
</aside>

<main id="main">
  <header id="top">
    <div id="readouts">
      <button id="sideToggle" class="iconbtn" title="Toggle sidebar" aria-label="Toggle sidebar">☰</button>
      <div class="cell goal"><span class="lbl">Goal</span><div class="val" id="topGoal">—</div></div>
      <div class="cell iter"><span class="lbl">Iter</span>
        <div class="val" id="iterRead">···<span class="cap"></span></div></div>
      <div class="cell tasks"><span class="lbl">Tasks</span>
        <div class="val" id="taskRead">—</div><div class="segs" id="taskSegs"></div></div>
      <div class="cell"><span class="lbl">Status</span>
        <div class="val statusword never" id="topPill">no run</div></div>
      <div class="cell actions">
        <button id="copyBtn" style="display:none">Copy diagnostics</button>
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
          <h2>The night shift for your <b>code</b></h2>
          <p>Set a goal and pick a folder. A local model plans, writes,
          tests, and commits — on its own, for as long as you let it.</p>
          <button class="primary" onclick="openNew()">Start a session</button>
        </div>
      </div>
      <div id="statusbar"></div>
    </section>
    <div class="gutter" id="gutter" role="separator" aria-orientation="vertical" title="Drag to resize"></div>
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
        <button id="startBtn" class="primary" onclick="startSession()">Start</button>
  </div>
</div></div>

<div id="copyOverlay" role="dialog" aria-modal="true"><div class="modal frame">
  <h2>Diagnostic bundle</h2>
  <div class="field"><span class="lbl">Copy this text</span>
    <textarea id="copyText" style="min-height:320px"></textarea>
    <div class="hint" id="copyHint">Clipboard access was unavailable, so the bundle is shown here.</div>
  </div>
  <div class="actions">
    <button onclick="$('copyOverlay').classList.remove('show')">Close</button>
  </div>
</div></div>

<script>
const $ = id => document.getElementById(id);
const esc = s => String(s??'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const pad3 = n => String(n).padStart(3,'0');
let current = null, pinnedCommit = null, lastDiffCommit = null, lastRender = '', lastRail = '';
let openIters = new Set(), touched = new Set(), autoIter = null, lastEntries = [];

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
function selectRun(dir){
  current = dir; pinnedCommit = null; lastRender = ''; lastRail = '';
  openIters = new Set(); touched = new Set(); autoIter = null; lastEntries = [];
  tickRun(); tickRuns();
}

/* ---------- pulse strip: the run's life as a seismograph ---------- */
function pulseSvg(entries, running){
  const iters = entries.filter(e => e.event === 'iteration').slice(-140);
  const step = 8, w = Math.max(600, iters.length*step + 26), h = 30, base = 19;
  const parts = [`<line x1="0" y1="${base}" x2="${w}" y2="${base}" stroke="#2a2825"/>`];
  iters.forEach((e, i) => {
    const x = 8 + i*step;
    parts.push(e.ok
      ? `<line x1="${x}" y1="${base}" x2="${x}" y2="5" stroke="#97b58c" stroke-width="2"><title>iter ${e.iteration}: validated</title></line>`
      : `<line x1="${x}" y1="${base}" x2="${x}" y2="${h-2}" stroke="#cd6f63" stroke-width="2"><title>iter ${e.iteration}: failed</title></line>`);
  });
  if (running) parts.push(`<rect class="cursor" x="${8 + iters.length*step}" y="8" width="5" height="11" fill="#d97757"/>`);
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
function toggleRec(it){
  it = Number(it);
  if (openIters.has(it)) openIters.delete(it); else openIters.add(it);
  touched.add(it);
  renderTranscript(lastEntries, false);
}
function entryHtml(e){
  if (e.event === 'activity'){
    const kind = e.mode ? `<span class="k">${esc(e.mode)}</span>` : '';
    return `<div class="act">${kind}<span>${esc(e.summary)}</span></div>`;
  }
  if (e.event === 'live'){
    return `<article class="rec open selected">
      <div class="rechead" style="cursor:default">
        <span class="chev" style="visibility:hidden">▶</span>
        <span class="recno">${pad3(e.iteration)}</span>
        <span class="recmode">${esc(e.mode)}</span>
        <span class="rectitle">${esc(e.subtask)}</span>
        <span class="flag warn">live</span>
        <span class="verdict ok"><span class="cursor">▮</span> Running</span>
      </div>
      <div class="recbody">
        <div class="recline execl"><span class="lbl">Exec</span><span class="txt">${esc(e.summary)}</span></div>
        <div class="recmeta"><span>not committed yet</span></div>
      </div>
    </article>`;
  }
  if (e.event === 'iteration'){
    const open = openIters.has(e.iteration);
    const sel = pinnedCommit && e.commit === pinnedCommit ? 'selected' : '';
    const title = esc(e.subtask || '(no task)');
    return `<article class="rec ${open?'open':''} ${sel}">
      <div class="rechead" onclick="toggleRec(${e.iteration})">
        <span class="chev">▶</span>
        <span class="recno">${pad3(e.iteration)}</span>
        <span class="recmode">${esc(e.mode)}</span>
        <span class="rectitle">${title}</span>
        ${flags(e)}
        <span class="verdict ${e.ok?'ok':'bad'}">${e.ok?'Passed':'Failed'}</span>
      </div>
      <div class="recbody">
        <div class="recline plan"><span class="lbl">Plan</span><span class="txt">${title}</span></div>
        <div class="recline execl"><span class="lbl">Exec</span><span class="txt">${esc(e.summary||'(no summary)')}</span></div>
        ${e.files.length?`<div class="files">${e.files.map(f=>`<span class="file">${esc(f)}</span>`).join('')}</div>`:''}
        ${e.tool_runs.map(t=>`<div class="recline execl"><span class="lbl">Tool</span><span class="txt">${esc(t.name)} → ${esc(t.result)}</span></div>`).join('')}
        ${e.errors.length?`<div class="errblock">${e.errors.map(x=>esc(x)).join('<br>')}</div>`:''}
        <div class="recmeta">${e.commit?`<span class="hash" onclick="event.stopPropagation();loadDiff('${esc(e.commit)}',true)">${esc(e.commit)}</span><span>view diff →</span>`:'<span>no commit</span>'}</div>
      </div>
    </article>`;
  }
  if (e.event === 'finished') return `<div class="evt finish"><b>◉ goal complete</b> ${esc(e.summary)}</div>`;
  if (e.event === 'shutdown') return `<div class="evt">■ stopped — <b>${esc(e.summary)}</b></div>`;
  if (e.event === 'startup')  return `<div class="evt">▶ ${esc(e.summary)}</div>`;
  return `<div class="evt"><b>${esc(e.event)}</b> ${esc(e.summary)}</div>`;
}

function renderTranscript(entries, allowScroll){
  const html = entries.map(entryHtml).join('') ||
    '<div class="empty"><p>spinning up…</p></div>';
  if (html === lastRender) return;
  const chat = $('chat');
  const nearBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 160;
  chat.innerHTML = html;
  if (allowScroll && nearBottom) chat.scrollTop = chat.scrollHeight;
  lastRender = html;
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
  $('copyBtn').style.display = current ? '' : 'none';
  $('pulsewrap').style.display = r.entries.some(e => e.event === 'iteration') ? '' : 'none';
  $('pulse').innerHTML = pulseSvg(r.entries, running);

  const sb = $('statusbar');
  if (running){
    sb.style.display = 'flex';
    sb.innerHTML = `<span class="cursor">▮</span><span><b>${esc(r.mode||'…')}</b> — iter ${r.iteration}/${r.cap}${r.live_subtask?` — ${esc(r.live_subtask)}`:''}${r.stop_present?' — stopping at boundary':''}</span>`;
    $('livehint').textContent = 'live · polling 2s';
  } else { sb.style.display = 'none'; $('livehint').textContent = ''; }

  // auto-expand the newest iteration; auto-collapse the previous one unless the
  // user has manually toggled it. Manual choices always win.
  const iterNums = r.entries.filter(e => e.event === 'iteration').map(e => e.iteration);
  const latestIter = iterNums.length ? Math.max(...iterNums) : null;
  if (latestIter !== null && latestIter !== autoIter){
    if (autoIter !== null && !touched.has(autoIter)) openIters.delete(autoIter);
    if (!touched.has(latestIter)) openIters.add(latestIter);
    autoIter = latestIter;
  }
  lastEntries = r.entries;
  renderTranscript(r.entries, true);
  if (!pinnedCommit){
    const commits = r.entries.filter(e => e.commit && e.event === 'iteration');
    if (commits.length) loadDiff(commits[commits.length-1].commit, false);
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
  $('diffPin').innerHTML = pin ? `<button onclick="unpin()" style="padding:2px 10px;font-size:11px">follow latest</button>` : '';
  let r; try{ r = await (await fetch(`/api/diff?dir=${encodeURIComponent(current)}&commit=${commit}`)).json(); }catch(e){ return; }
  $('diff').innerHTML = r.error ? `<span class="del">${esc(r.error)}</span>` : colorize(r.diff);
}
function unpin(){ pinnedCommit = null; lastRender = ''; $('diffPin').innerHTML = ''; tickRun(); }

/* ---------- controls ---------- */
$('stopBtn').onclick = async () => {
  const b = $('stopBtn'); b.disabled = true; b.textContent = 'Stopping…';
  await fetch('/api/stop', {method:'POST', body: JSON.stringify({dir: current})});
  b.disabled = false; b.textContent = 'Stop'; tickRun();
};
$('resumeBtn').onclick = async () => {
  const r = await (await fetch('/api/start', {method:'POST', body: JSON.stringify({dir: current})})).json();
  if (r.error) alert(r.error); tickRun();
};
$('copyBtn').onclick = async () => {
  if (!current) return;
  const btn = $('copyBtn'), old = btn.textContent;
  btn.textContent = 'Copying…';
  let r;
  try{ r = await (await fetch('/api/export?dir='+encodeURIComponent(current))).json(); }
  catch(e){ btn.textContent = 'Copy failed'; setTimeout(()=>btn.textContent=old, 1600); return; }
  if (r.error){ alert(r.error); btn.textContent = old; return; }
  try{
    await navigator.clipboard.writeText(r.text);
    btn.textContent = `Copied ${Math.round((r.chars||r.text.length)/1000)}k`;
    if (r.path) btn.textContent += ' · saved';
    setTimeout(()=>btn.textContent=old, 1800);
  }catch(e){
    $('copyText').value = r.text;
    $('copyHint').textContent = r.path
      ? `Clipboard access was unavailable. The same bundle was saved to ${r.path}.`
      : 'Clipboard access was unavailable, so the bundle is shown here.';
    $('copyOverlay').classList.add('show');
    $('copyText').focus();
    $('copyText').select();
    btn.textContent = old;
  }
};

/* ---------- new session modal ---------- */
let mode = '';
function setMode(m){ mode = m; $('mReg').className = m ? '' : 'on'; $('mOver').className = m ? 'on' : ''; }
function openNew(){ $('overlay').classList.add('show'); $('fErr').textContent=''; loadModels(); $('fGoal').focus(); }
function closeNew(){ $('overlay').classList.remove('show'); $('browser').style.display='none'; }
$('newBtn').onclick = openNew;
document.addEventListener('keydown', e => {
  if (e.key === 'Escape'){ closeNew(); $('copyOverlay').classList.remove('show'); }
});
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
  if (!payload.dir){ $('fErr').textContent = 'Pick a folder first'; return; }
  if (!payload.goal){ $('fErr').textContent = 'Write a goal — one sentence is enough'; return; }
  const btn = $('startBtn');
  btn.disabled = true; btn.textContent = 'Starting…'; $('fErr').textContent = '';
  let r; try{ r = await (await fetch('/api/start', {method:'POST', body: JSON.stringify(payload)})).json(); }
  catch(e){ $('fErr').textContent = 'Server unreachable'; btn.disabled=false; btn.textContent='Start'; return; }
  if (r.error){ $('fErr').textContent = r.error; btn.disabled=false; btn.textContent='Start'; return; }
  btn.disabled = false; btn.textContent = 'Start';
  closeNew(); selectRun(r.dir);
}

/* ---------- sidebar collapse ---------- */
$('sideToggle').onclick = () => $('side').classList.toggle('collapsed');

/* ---------- resizable transcript / diff split ---------- */
(function(){
  const gutter = $('gutter'), pane = $('diffpane'), panes = $('panes');
  let dragging = false;
  gutter.addEventListener('mousedown', e => {
    dragging = true; gutter.classList.add('drag');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const rect = panes.getBoundingClientRect();
    let w = rect.right - e.clientX;                 // diff pane is on the right
    w = Math.max(240, Math.min(w, rect.width - 320)); // clamp both sides
    pane.style.width = w + 'px';
  });
  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false; gutter.classList.remove('drag');
    document.body.style.cursor = ''; document.body.style.userSelect = '';
  });
})();

tickRuns(); setInterval(tickRuns, 2500); setInterval(tickRun, 2000);
</script></body></html>"""
