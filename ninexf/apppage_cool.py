"""The `9xf app` page — cool mode.

Aesthetic direction: a refined, premium dark workstation in the spirit of
Linear / Raycast / Vercel. Layered near-black surfaces with genuine elevation
(soft shadows, hairline rgba borders), one cool violet-indigo accent used
sparingly, an ambient radial bloom behind the header for atmosphere, and clean
system sans for prose with monospace reserved for hashes, numbers, and diffs.

The signature element is the PULSE — a smooth column chart of every iteration,
gradient-filled bars rising for a pass and dropping for a fail, with a softly
pulsing live cursor.

Constraints: one self-contained file, fully offline (system fonts only),
prefers-reduced-motion respected, :focus-visible styling, and color is never
the only signal (every state also carries a glyph or word).
"""

APP_PAGE_COOL = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>9xf</title>
<style>
:root{
  --bg:#0a0a0f;
  --surface:#101017;
  --surface-2:#16161f;
  --elevated:#1b1b26;
  --hair:rgba(255,255,255,.06);
  --hair-2:rgba(255,255,255,.10);
  --hair-strong:rgba(255,255,255,.16);

  --accent:#8b7fff;
  --accent-bright:#a99dff;
  --accent-deep:#6d5fe6;
  --accent-glow:rgba(139,127,255,.28);
  --accent-faint:rgba(139,127,255,.10);

  --green:#4ade80;
  --green-soft:rgba(74,222,128,.14);
  --red:#f87171;
  --red-soft:rgba(248,113,113,.13);
  --amber:#fbbf24;
  --amber-soft:rgba(251,191,36,.13);
  --cyan:#67e8f9;
  --blue:#7dd3fc;

  --txt:#edecf4;
  --txt-2:#c3c2d4;
  --dim:#8b8aa0;
  --faint:#5a5970;
  --ghost:#3a3a4d;

  --sans:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;

  --shadow-sm:0 1px 2px rgba(0,0,0,.4);
  --shadow-md:0 4px 16px rgba(0,0,0,.32),0 1px 2px rgba(0,0,0,.4);
  --shadow-lg:0 24px 60px rgba(0,0,0,.5),0 8px 24px rgba(0,0,0,.4);
  --radius:12px;
  --radius-sm:9px;
}
*{box-sizing:border-box;margin:0}
html,body{height:100%}
body{
  background:var(--bg);color:var(--txt);
  font:13.5px/1.6 var(--sans);
  display:flex;overflow:hidden;
  font-variant-numeric:tabular-nums;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  letter-spacing:-.01em;
}

/* ambient bloom — atmosphere behind the whole canvas */
body::before{
  content:'';position:fixed;top:-280px;left:50%;transform:translateX(-50%);
  width:1100px;height:620px;pointer-events:none;z-index:0;
  background:radial-gradient(ellipse at center,var(--accent-glow),transparent 62%);
  opacity:.5;filter:blur(20px);
}

::selection{background:var(--accent-glow);color:#fff}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-thumb{background:var(--hair-2);border-radius:5px;border:2px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:var(--hair-strong);background-clip:padding-box}
::-webkit-scrollbar-track{background:transparent}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* ---------- primitives ---------- */
.lbl{font-size:10.5px;font-weight:600;color:var(--faint);letter-spacing:.04em;text-transform:uppercase}

button{
  font:inherit;font-size:12.5px;font-weight:500;cursor:pointer;color:var(--txt-2);
  background:var(--surface-2);border:1px solid var(--hair-2);border-radius:var(--radius-sm);
  padding:7px 15px;letter-spacing:-.01em;
  transition:background .15s ease,border-color .15s ease,color .15s ease,box-shadow .15s ease,transform .08s ease;
}
button:hover{background:var(--elevated);border-color:var(--hair-strong);color:var(--txt)}
button:active{transform:translateY(.5px)}
button:disabled{opacity:.4;cursor:default;transform:none}
button.primary{
  background:linear-gradient(180deg,var(--accent),var(--accent-deep));
  border:1px solid transparent;color:#fff;font-weight:600;
  box-shadow:0 1px 0 rgba(255,255,255,.18) inset,0 6px 18px var(--accent-glow);
}
button.primary:hover{
  background:linear-gradient(180deg,var(--accent-bright),var(--accent));
  box-shadow:0 1px 0 rgba(255,255,255,.25) inset,0 8px 26px var(--accent-glow);
  color:#fff;
}
button.danger:hover{border-color:rgba(248,113,113,.5);color:var(--red);background:var(--red-soft)}

input,textarea,select{
  font:inherit;font-size:13px;background:var(--bg);color:var(--txt);
  border:1px solid var(--hair-2);border-radius:var(--radius-sm);padding:9px 13px;width:100%;
  transition:border-color .15s ease,box-shadow .15s ease;
}
input::placeholder,textarea::placeholder{color:var(--ghost)}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-faint)}
textarea{resize:vertical;min-height:76px;line-height:1.55}

@keyframes blink{0%,52%{opacity:1}53%,100%{opacity:.15}}
.cursor{animation:blink 1.05s steps(1) infinite}
@keyframes breathe{0%,100%{box-shadow:0 0 0 0 var(--green-soft)}50%{box-shadow:0 0 0 4px transparent,0 0 10px 1px rgba(74,222,128,.45)}}
@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

/* ---------- sidebar ---------- */
#side{
  width:280px;min-width:280px;background:var(--surface);
  display:flex;flex-direction:column;position:relative;z-index:1;
  border-right:1px solid var(--hair);
  transition:width .18s ease,min-width .18s ease;
}
#side.collapsed{width:0;min-width:0;overflow:hidden}
#brand{padding:20px 20px 14px;display:flex;align-items:center;gap:11px}
#brand .mark{
  width:30px;height:30px;border-radius:8px;flex:none;
  background:linear-gradient(140deg,var(--accent-bright),var(--accent-deep));
  box-shadow:0 4px 12px var(--accent-glow),0 1px 0 rgba(255,255,255,.2) inset;
  display:flex;align-items:center;justify-content:center;
  font:700 14px/1 var(--mono);color:#fff;letter-spacing:-.04em;
}
#brand .word{font-size:15px;font-weight:650;color:var(--txt);letter-spacing:-.02em}
#brand .tag{font-size:11px;color:var(--faint);margin-top:1px;font-weight:450}
#newBtn{margin:6px 16px 8px;display:block;width:calc(100% - 32px);padding:9px}
.raillabel{padding:14px 20px 6px;font-size:10.5px;font-weight:600;color:var(--faint);letter-spacing:.05em;text-transform:uppercase}
#runlist{flex:1;overflow-y:auto;padding:0 10px}
.runitem{
  display:flex;gap:11px;align-items:flex-start;padding:9px 12px;cursor:pointer;
  border-radius:10px;margin-bottom:2px;position:relative;
  border:1px solid transparent;
  transition:background .15s ease,border-color .15s ease;
}
.runitem:hover{background:var(--surface-2)}
.runitem.active{background:var(--elevated);border-color:var(--hair-2);box-shadow:var(--shadow-sm)}
.runitem.active::before{content:"";position:absolute;left:-1px;top:11px;bottom:11px;width:3px;
  border-radius:0 3px 3px 0;background:linear-gradient(180deg,var(--accent-bright),var(--accent-deep))}
.led{width:8px;height:8px;margin-top:6px;border-radius:50%;background:var(--ghost);flex:none;transition:background .2s}
.led.running{background:var(--green);animation:breathe 2.4s ease-in-out infinite}
.led.finished{background:var(--accent);box-shadow:0 0 8px var(--accent-glow)}
.led.failed{background:var(--red);box-shadow:0 0 7px var(--red-soft)}
.led.stale{background:var(--amber)}
.runitem .g{font-size:13px;color:var(--txt-2);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;max-width:210px;font-weight:500}
.runitem.active .g{color:var(--txt)}
.runitem .s{font-size:11px;color:var(--faint);margin-top:2px}
#railfoot{padding:13px 20px;display:flex;align-items:center;
  justify-content:space-between;border-top:1px solid var(--hair)}
#clock{font:10.5px var(--mono);color:var(--dim)}
#modeSwitch{font-size:11px;color:var(--faint);text-decoration:none;display:flex;align-items:center;gap:5px;
  padding:3px 9px;border-radius:7px;border:1px solid var(--hair);transition:color .15s,border-color .15s,background .15s}
#modeSwitch:hover{color:var(--txt-2);border-color:var(--hair-2);background:var(--surface-2)}

/* ---------- header ---------- */
#main{flex:1;display:flex;flex-direction:column;min-width:0;position:relative;z-index:1}
#top{
  border-bottom:1px solid var(--hair);
  background:linear-gradient(180deg,rgba(20,20,28,.7),rgba(16,16,23,.55));
  backdrop-filter:blur(20px) saturate(1.3);
}
#readouts{display:flex;align-items:center;gap:30px;padding:16px 26px 13px}
.cell{min-width:0}
.cell .val{margin-top:3px;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cell.goal{flex:1}
.cell.goal .val{font-size:14.5px;font-weight:600;color:var(--txt);letter-spacing:-.015em}
.cell.iter .val{font:650 20px/1.2 var(--mono);color:var(--txt);letter-spacing:-.02em}
.cell.iter .cap{color:var(--faint);font-size:13px;font-weight:400}
.segs{display:flex;gap:3px;margin-top:7px;flex-wrap:wrap;max-width:230px}
.seg{width:9px;height:9px;border-radius:3px;background:var(--ghost);transition:background .25s}
.seg.done{background:var(--green)}
.seg.cur{background:var(--accent);box-shadow:0 0 7px var(--accent-glow)}
.seg.def{background:var(--red);opacity:.6}
.statusword{font-size:12px;font-weight:600;display:inline-flex;align-items:center;gap:6px;
  padding:4px 11px;border-radius:99px;border:1px solid var(--hair-2);background:var(--surface-2)}
.statusword::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
.statusword.running{color:var(--green);background:var(--green-soft);border-color:rgba(74,222,128,.3)}
.statusword.finished{color:var(--accent-bright);background:var(--accent-faint);border-color:rgba(139,127,255,.3)}
.statusword.failed{color:var(--red);background:var(--red-soft);border-color:rgba(248,113,113,.3)}
.statusword.stale{color:var(--amber);background:var(--amber-soft);border-color:rgba(251,191,36,.3)}
.statusword.stopped,.statusword.never{color:var(--dim)}
.cell.actions{display:flex;align-items:center;gap:9px}
#pulsewrap{padding:0 26px 14px}
#pulsewrap .lbl{display:block;margin-bottom:6px}
#pulse{display:block;width:100%;background:linear-gradient(180deg,rgba(255,255,255,.018),transparent);
  border:1px solid var(--hair);border-radius:10px;padding:6px 4px}

/* ---------- panes ---------- */
#panes{flex:1;display:flex;min-height:0}
.panehead{padding:14px 26px 8px;font-size:10.5px;font-weight:600;color:var(--faint);letter-spacing:.05em;
  text-transform:uppercase;display:flex;justify-content:space-between;align-items:center;gap:8px}
.panehead #livehint{font-weight:500;letter-spacing:.02em;text-transform:none;color:var(--accent-bright);font-size:11px}
#chatwrap{flex:1;display:flex;flex-direction:column;min-width:300px}
.gutter{flex:none;width:9px;cursor:col-resize;background:transparent;
  border-left:1px solid var(--hair);transition:border-color .15s,box-shadow .15s}
.gutter:hover,.gutter.drag{border-left-color:var(--accent);box-shadow:-1px 0 0 var(--accent-glow)}
.iconbtn{border:1px solid transparent;background:transparent;color:var(--dim);padding:6px 8px;
  border-radius:8px;font-size:15px;line-height:1;font-weight:400}
.iconbtn:hover{background:var(--surface-2);color:var(--txt);border-color:transparent}
#chat{flex:1;overflow-y:auto;padding:8px 26px 20px;scroll-behavior:smooth}
#statusbar{display:none;border-top:1px solid var(--hair);
  padding:11px 26px;font-size:12.5px;color:var(--dim);align-items:center;gap:11px;
  background:linear-gradient(180deg,transparent,var(--accent-faint))}
#statusbar .cursor{color:var(--accent-bright)}
#statusbar b{color:var(--txt);font-weight:600}

/* ---------- transcript records ---------- */
.rec{background:var(--surface);border:1px solid var(--hair);border-radius:var(--radius);
  margin:0 auto 8px;max-width:760px;overflow:hidden;box-shadow:var(--shadow-sm);
  animation:rise .25s ease both;
  transition:border-color .18s ease,box-shadow .18s ease}
.rec:hover{border-color:var(--hair-2)}
.rec.selected{border-color:rgba(139,127,255,.45);box-shadow:0 0 0 1px var(--accent-faint),var(--shadow-md)}
.rec[data-ok="true"]{border-left:3px solid var(--green)}
.rec[data-ok="false"]{border-left:3px solid var(--red)}
.rec[data-live="1"]{border-left:3px solid var(--accent)}
.rechead{display:flex;align-items:center;gap:11px;padding:12px 15px;cursor:pointer;
  font-size:12px;color:var(--dim);user-select:none;transition:background .15s ease}
.rechead:hover{background:var(--surface-2)}
.chev{flex:none;color:var(--faint);font-size:9px;width:10px;
  transition:transform .22s cubic-bezier(.4,0,.2,1)}
.rec.open .chev,.actgroup.open .chev{transform:rotate(90deg)}
.recno{flex:none;font:600 12px var(--mono);color:var(--faint)}
.recmode{flex:none;color:var(--dim);font-size:11px;font-weight:500;text-transform:capitalize}
.rectitle{flex:1;min-width:0;color:var(--txt);font-size:13px;font-weight:500;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;letter-spacing:-.01em}
.flag{flex:none;padding:2px 9px;border-radius:99px;background:var(--surface-2);color:var(--dim);
  font-size:10.5px;font-weight:500;border:1px solid var(--hair)}
.flag.warn{background:var(--amber-soft);color:var(--amber);border-color:rgba(251,191,36,.25)}
.flag.bad{background:var(--red-soft);color:var(--red);border-color:rgba(248,113,113,.25)}
.flag.good{background:var(--green-soft);color:var(--green);border-color:rgba(74,222,128,.25)}
.verdict{margin-left:auto;font-weight:600;font-size:11.5px;display:inline-flex;align-items:center;gap:5px}
.verdict.ok{color:var(--green)}
.verdict.bad{color:var(--red)}
.recbody{display:grid;grid-template-rows:0fr;transition:grid-template-rows .24s cubic-bezier(.4,0,.2,1)}
.rec.open .recbody{grid-template-rows:1fr}
.rbi{overflow:hidden;min-height:0;padding:0 16px 0 38px}
.rec.open .rbi{padding-bottom:14px}
.recline{display:flex;gap:12px;padding-top:9px}
.recline .lbl{flex:none;width:38px;font-size:10.5px;font-weight:600;color:var(--faint);padding-top:1px}
.recline .txt{font-size:12.5px;line-height:1.6;word-break:break-word;min-width:0}
.recline.plan .txt{color:var(--txt-2)}
.recline.execl .txt{color:var(--dim)}
.files{display:flex;flex-wrap:wrap;gap:6px;padding:10px 0 0 50px}
.file{font:11px var(--mono);background:var(--surface-2);border:1px solid var(--hair);
  border-radius:6px;padding:3px 9px;color:var(--blue)}
.errblock{margin:9px 0 0 50px;border-radius:9px;padding:9px 12px;
  font:11.5px/1.55 var(--mono);color:var(--red);word-break:break-word;
  background:var(--red-soft);border:1px solid rgba(248,113,113,.2)}
.recmeta{display:flex;gap:15px;align-items:center;padding:11px 0 0 50px;font-size:11px;color:var(--faint)}
.recmeta .hash{font-family:var(--mono);color:var(--accent-bright);cursor:pointer;
  padding:2px 8px;border-radius:6px;background:var(--accent-faint);transition:background .15s}
.recmeta .hash:hover{background:rgba(139,127,255,.2)}

/* activity / process stream */
.actgroup{max-width:760px;margin:0 auto 8px;border-radius:var(--radius);
  background:var(--surface-2);border:1px solid var(--hair);
  animation:rise .25s ease both;transition:border-color .15s}
.actgroup:hover{border-color:var(--hair-2)}
.acthead{display:flex;align-items:center;gap:10px;padding:9px 15px;cursor:pointer;
  font-size:11.5px;color:var(--dim);user-select:none}
.acthead .chev{color:var(--faint)}
.actcount{flex:none;font:600 11px var(--mono);color:var(--accent-bright);
  padding:1px 8px;border-radius:99px;background:var(--accent-faint)}
.actpath{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--dim)}
.actlast{flex:none;max-width:46%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  color:var(--faint)}
.actbody{display:grid;grid-template-rows:0fr;transition:grid-template-rows .24s cubic-bezier(.4,0,.2,1)}
.actgroup.open .actbody{grid-template-rows:1fr}
.abi{overflow:hidden;min-height:0}
.actgroup.open .abi{padding:0 16px 10px 38px}
.actrow{display:flex;gap:12px;padding-top:6px;font-size:11.5px;color:var(--dim)}
.actrow .k{flex:none;width:68px;color:var(--faint);font-weight:600}

/* milestones */
.evt{display:flex;align-items:center;justify-content:center;gap:9px;max-width:760px;
  margin:14px auto;color:var(--faint);font-size:12px;text-align:center}
.evt b{color:var(--dim);font-weight:600}
.evt.finish{color:var(--accent-bright)}
.evt.finish b{color:var(--accent-bright)}

/* empty state */
.empty{margin:auto;text-align:center;padding:64px 32px;max-width:460px;animation:rise .4s ease both}
.empty .glyph{width:54px;height:54px;margin:0 auto 22px;border-radius:14px;
  background:linear-gradient(140deg,var(--accent-bright),var(--accent-deep));
  box-shadow:0 12px 32px var(--accent-glow),0 1px 0 rgba(255,255,255,.2) inset;
  display:flex;align-items:center;justify-content:center;font:700 22px/1 var(--mono);color:#fff;letter-spacing:-.04em}
.empty h2{font-size:23px;font-weight:650;margin-bottom:13px;color:var(--txt);line-height:1.25;letter-spacing:-.02em}
.empty h2 b{background:linear-gradient(120deg,var(--accent-bright),var(--cyan));
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.empty p{color:var(--dim);font-size:14px;margin-bottom:28px;line-height:1.65}

/* ---------- diff register ---------- */
#diffpane{flex:none;width:46%;min-width:240px;display:flex;flex-direction:column;
  min-height:0;background:var(--surface);border-left:1px solid var(--hair)}
#diffTitle .hash{font-family:var(--mono);color:var(--accent-bright)}
#diff{flex:1;overflow:auto;padding:12px 24px 18px;font:11.5px/1.65 var(--mono);
  white-space:pre;color:var(--dim)}
#diff.swap{animation:fadein .22s ease}
@keyframes fadein{from{opacity:0}to{opacity:1}}
#diff .add{color:var(--green)}
#diff .del{color:var(--red)}
#diff .hunk{color:var(--accent-bright)}
#diff .file{color:var(--blue);font-weight:700}
#diff .ctx{color:var(--faint)}

/* ---------- modal ---------- */
#overlay,#copyOverlay{position:fixed;inset:0;background:rgba(5,5,9,.6);display:none;
  align-items:center;justify-content:center;z-index:20;backdrop-filter:blur(8px)}
#overlay.show,#copyOverlay.show{display:flex;animation:fadein .18s ease}
.modal{width:580px;max-width:94vw;max-height:90vh;overflow-y:auto;padding:28px;
  background:var(--elevated);border:1px solid var(--hair-2);border-radius:16px;
  box-shadow:var(--shadow-lg);animation:rise .24s cubic-bezier(.2,.7,.2,1) both}
.modal h2{font-size:17px;font-weight:650;color:var(--txt);margin-bottom:20px;letter-spacing:-.02em}
.field{margin-bottom:17px}
.field .lbl{display:block;margin-bottom:7px}
.row{display:flex;gap:11px}.row>*{flex:1}
.seg-switch{display:flex;border:1px solid var(--hair-2);border-radius:var(--radius-sm);overflow:hidden;background:var(--bg)}
.seg-switch button{flex:1;border:0;border-radius:0;background:transparent;color:var(--dim);box-shadow:none}
.seg-switch button:hover{background:var(--surface-2);color:var(--txt-2)}
.seg-switch button.on{background:linear-gradient(180deg,var(--accent),var(--accent-deep));color:#fff;font-weight:600;
  box-shadow:0 1px 0 rgba(255,255,255,.15) inset}
.modal .actions{display:flex;justify-content:flex-end;gap:11px;margin-top:22px}
#browser{border:1px solid var(--hair-2);border-radius:var(--radius-sm);margin-top:9px;background:var(--bg);
  overflow:hidden;display:none;flex-direction:column;max-height:300px}
.browpath{flex:none;padding:9px 13px;border-bottom:1px solid var(--hair);
  font:11.5px var(--mono);color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.browlist{flex:1;overflow-y:auto;padding:5px}
#browser .bi{padding:8px 11px;cursor:pointer;display:flex;gap:10px;align-items:center;
  border-radius:8px;font-size:12.5px;color:var(--txt-2)}
#browser .bi:hover{background:var(--surface-2);color:var(--txt)}
#browser .bi.muted{color:var(--faint);cursor:default}
#browser .bi.muted:hover{background:transparent}
#browser .bi .ic{flex:none;width:13px;color:var(--faint);text-align:center}
#browser .bi .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#browser .bi .tag{flex:none;color:var(--accent-bright);font-size:10px;border:1px solid rgba(139,127,255,.3);
  border-radius:99px;padding:1px 8px;background:var(--accent-faint)}
.browfoot{flex:none;padding:9px 11px;border-top:1px solid var(--hair);display:flex;
  align-items:center;gap:11px}
.browfoot .sel{flex:1;min-width:0;font:11px var(--mono);color:var(--faint);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.browfoot button{flex:none;padding:6px 14px;font-size:11.5px}
.formerr{color:var(--red);font-size:12.5px;margin-top:9px;min-height:14px}
.hint{color:var(--faint);font-size:11.5px;margin-top:7px}
.kbd{font:10.5px var(--mono);color:var(--dim);border:1px solid var(--hair-2);
  border-radius:5px;padding:2px 6px;background:var(--bg)}
.modal .actions .sp{margin-right:auto;color:var(--faint);font-size:11.5px;display:flex;
  align-items:center;gap:7px}
</style></head><body>

<aside id="side">
  <div id="brand">
    <div class="mark">9x</div>
    <div><div class="word">9xf</div><div class="tag">autonomous coding loops</div></div>
  </div>
  <button id="newBtn" class="primary" title="New session  (n)" aria-label="New session">New session</button>
  <div class="raillabel">Sessions</div>
  <div id="runlist" role="list"></div>
  <div id="railfoot">
    <span id="clock">--:--:--</span>
    <a id="modeSwitch" href="/" title="Switch to basic mode">Basic mode</a>
  </div>
</aside>

<main id="main">
  <header id="top">
    <div id="readouts">
      <button id="sideToggle" class="iconbtn" title="Toggle sidebar  (⌘/Ctrl+B)" aria-label="Toggle sidebar">☰</button>
      <div class="cell goal"><span class="lbl">Goal</span><div class="val" id="topGoal">—</div></div>
      <div class="cell iter"><span class="lbl">Iter</span>
        <div class="val" id="iterRead">···<span class="cap"></span></div></div>
      <div class="cell tasks"><span class="lbl">Tasks</span>
        <div class="val" id="taskRead">—</div><div class="segs" id="taskSegs"></div></div>
      <div class="cell"><span class="lbl">Status</span>
        <div class="val" style="margin-top:5px"><span class="statusword never" id="topPill">no run</span></div></div>
      <div class="cell actions">
        <button id="copyBtn" style="display:none">Copy diagnostics</button>
        <button id="stopBtn" class="danger" style="display:none">Stop</button>
        <button id="resumeBtn" class="primary" style="display:none">Resume</button>
      </div>
    </div>
    <div id="pulsewrap" style="display:none"><span class="lbl">Pulse — one bar per iteration</span><div id="pulse"></div></div>
  </header>

  <div id="panes">
    <section id="chatwrap" aria-label="transcript">
      <div class="panehead"><span>Transcript</span><span id="livehint"></span></div>
      <div id="chat">
        <div class="empty">
          <div class="glyph">9x</div>
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

<div id="overlay" role="dialog" aria-modal="true"><div class="modal">
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
    <span class="sp"><span class="kbd">⌘/Ctrl ↵</span> to start</span>
    <button onclick="closeNew()">Cancel</button>
    <button id="startBtn" class="primary" onclick="startSession()">Start</button>
  </div>
</div></div>

<div id="copyOverlay" role="dialog" aria-modal="true"><div class="modal">
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
let openActs = new Set();

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
  const html = runs.map(r => `
    <div class="runitem ${current===r.dir?'active':''}" role="listitem" tabindex="0"
         onclick="selectRun('${esc(r.dir)}')" onkeydown="if(event.key==='Enter')selectRun('${esc(r.dir)}')">
      <i class="led ${ledClass(r)}" aria-hidden="true"></i>
      <div><div class="g">${esc(r.goal)}</div>
      <div class="s">${r.finished?'finished':esc(r.status)} · iter ${r.iteration}${r.tasks_total?` · ${r.tasks_done}/${r.tasks_total}`:''}</div></div>
    </div>`).join('') ||
    '<div class="s" style="padding:14px 18px;color:var(--faint);font-size:12px">No sessions on record</div>';
  if (html !== lastRail){ $('runlist').innerHTML = html; lastRail = html; }
}
function selectRun(dir){
  current = dir; pinnedCommit = null; lastRender = ''; lastRail = '';
  openIters = new Set(); touched = new Set(); autoIter = null; lastEntries = [];
  openActs = new Set();
  tickRun(); tickRuns();
}

/* ---------- pulse: column chart of iterations ---------- */
function pulseSvg(entries, running){
  const iters = entries.filter(e => e.event === 'iteration').slice(-140);
  const step = 9, bw = 5, w = Math.max(600, iters.length*step + 28), h = 40, base = h/2;
  const defs = `<defs>
    <linearGradient id="gp" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#4ade80"/><stop offset="1" stop-color="#4ade80" stop-opacity=".35"/></linearGradient>
    <linearGradient id="gf" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#f87171" stop-opacity=".35"/><stop offset="1" stop-color="#f87171"/></linearGradient>
    <radialGradient id="gc"><stop offset="0" stop-color="#a99dff"/><stop offset="1" stop-color="#a99dff" stop-opacity="0"/></radialGradient>
  </defs>`;
  const grid = `<line x1="6" y1="${base}" x2="${w-6}" y2="${base}" stroke="rgba(255,255,255,.07)" stroke-width="1"/>`;
  const parts = [defs, grid];
  iters.forEach((e, i) => {
    const x = 8 + i*step;
    if (e.ok){
      const bh = base - 5;
      parts.push(`<rect x="${x}" y="5" width="${bw}" height="${bh}" rx="2" fill="url(#gp)"><title>iter ${e.iteration}: validated</title></rect>`);
    } else {
      const bh = (h-5) - base;
      parts.push(`<rect x="${x}" y="${base}" width="${bw}" height="${bh}" rx="2" fill="url(#gf)"><title>iter ${e.iteration}: failed</title></rect>`);
    }
  });
  if (running){
    const cx = 8 + iters.length*step + bw/2;
    parts.push(`<circle cx="${cx}" cy="${base}" r="9" fill="url(#gc)"/>`);
    parts.push(`<rect class="cursor" x="${cx-2.5}" y="${base-9}" width="5" height="18" rx="2.5" fill="#a99dff"/>`);
  }
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

/* ---------- transcript ---------- */
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
function toggleAct(key){
  if (openActs.has(key)) openActs.delete(key); else openActs.add(key);
  renderTranscript(lastEntries, false);
}
function activityGroupHtml(group){
  const key = 'act' + (group[0].iteration || 0);
  const open = openActs.has(key);
  const path = [...new Set(group.map(g => g.mode).filter(Boolean))].slice(0, 7);
  const last = group[group.length - 1];
  const rows = group.map(g =>
    `<div class="actrow"><span class="k">${esc(g.mode||'')}</span><span>${esc(g.summary)}</span></div>`).join('');
  const n = group.length;
  return `<div class="actgroup ${open?'open':''}">
    <div class="acthead" onclick="toggleAct('${key}')">
      <span class="chev">▶</span>
      <span class="actcount">${n} step${n>1?'s':''}</span>
      <span class="actpath">${path.map(esc).join('  ›  ')}</span>
      ${open?'':`<span class="actlast">${esc(last.summary||'')}</span>`}
    </div>
    <div class="actbody"><div class="abi">${rows}</div></div>
  </div>`;
}
function entryHtml(e){
  if (e.event === 'live'){
    return `<article class="rec open selected" data-live="1">
      <div class="rechead" style="cursor:default">
        <span class="chev" style="visibility:hidden">▶</span>
        <span class="recno">${pad3(e.iteration)}</span>
        <span class="recmode">${esc(e.mode)}</span>
        <span class="rectitle">${esc(e.subtask)}</span>
        <span class="flag warn">live</span>
        <span class="verdict ok"><span class="cursor">▮</span> Running</span>
      </div>
      <div class="recbody"><div class="rbi">
        <div class="recline execl"><span class="lbl">Exec</span><span class="txt">${esc(e.summary)}</span></div>
        <div class="recmeta"><span>not committed yet</span></div>
      </div></div>
    </article>`;
  }
  if (e.event === 'iteration'){
    const open = openIters.has(e.iteration);
    const sel = pinnedCommit && e.commit === pinnedCommit ? 'selected' : '';
    const title = esc(e.subtask || '(no task)');
    return `<article class="rec ${open?'open':''} ${sel}" data-ok="${e.ok}">
      <div class="rechead" onclick="toggleRec(${e.iteration})">
        <span class="chev">▶</span>
        <span class="recno">${pad3(e.iteration)}</span>
        <span class="recmode">${esc(e.mode)}</span>
        <span class="rectitle">${title}</span>
        ${flags(e)}
        <span class="verdict ${e.ok?'ok':'bad'}">${e.ok?'Passed':'Failed'}</span>
      </div>
      <div class="recbody"><div class="rbi">
        <div class="recline plan"><span class="lbl">Plan</span><span class="txt">${title}</span></div>
        <div class="recline execl"><span class="lbl">Exec</span><span class="txt">${esc(e.summary||'(no summary)')}</span></div>
        ${e.files.length?`<div class="files">${e.files.map(f=>`<span class="file">${esc(f)}</span>`).join('')}</div>`:''}
        ${e.model_calls?`<div class="recline execl"><span class="lbl">Model</span><span class="txt">${e.model_calls} call${e.model_calls===1?'':'s'} · ${esc(e.model_seconds)}s</span></div>`:''}
        ${e.tool_runs.map(t=>`<div class="recline execl"><span class="lbl">Tool</span><span class="txt">${esc(t.name)} → ${esc(t.result)}</span></div>`).join('')}
        ${e.warnings&&e.warnings.length?`<div class="errblock" style="color:var(--amber);background:var(--amber-soft);border-color:rgba(251,191,36,.2)">${e.warnings.map(x=>esc(x)).join('<br>')}</div>`:''}
        ${e.errors.length?`<div class="errblock">${e.errors.map(x=>esc(x)).join('<br>')}</div>`:''}
        <div class="recmeta">${e.commit?`<span class="hash" onclick="event.stopPropagation();loadDiff('${esc(e.commit)}',true)">${esc(e.commit)}</span><span>view diff →</span>`:'<span>no commit</span>'}</div>
      </div></div>
    </article>`;
  }
  if (e.event === 'finished') return `<div class="evt finish"><b>◉ goal complete</b> ${esc(e.summary)}</div>`;
  if (e.event === 'shutdown') return `<div class="evt">■ stopped — <b>${esc(e.summary)}</b></div>`;
  if (e.event === 'startup')  return `<div class="evt">▶ ${esc(e.summary)}</div>`;
  return `<div class="evt"><b>${esc(e.event)}</b> ${esc(e.summary)}</div>`;
}

function renderTranscript(entries, allowScroll){
  let html = '', i = 0;
  while (i < entries.length){
    if (entries[i].event === 'activity'){
      const group = [];
      while (i < entries.length && entries[i].event === 'activity'){ group.push(entries[i]); i++; }
      html += activityGroupHtml(group);
    } else {
      html += entryHtml(entries[i]); i++;
    }
  }
  if (!html) html = '<div class="empty"><p>spinning up…</p></div>';
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
  $('topPill').textContent = r.finished ? 'finished' : r.status;
  $('topPill').className = 'statusword ' + status;
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
  $('diffPin').innerHTML = pin ? `<button onclick="unpin()" style="padding:3px 11px;font-size:11px">follow latest</button>` : '';
  let r; try{ r = await (await fetch(`/api/diff?dir=${encodeURIComponent(current)}&commit=${commit}`)).json(); }catch(e){ return; }
  const d = $('diff');
  d.innerHTML = r.error ? `<span class="del">${esc(r.error)}</span>` : colorize(r.diff);
  d.classList.remove('swap'); void d.offsetWidth; d.classList.add('swap');
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
    $('copyText').focus(); $('copyText').select();
    btn.textContent = old;
  }
};

/* ---------- new session modal ---------- */
let mode = '';
function setMode(m){ mode = m; $('mReg').className = m ? '' : 'on'; $('mOver').className = m ? 'on' : ''; }
function openNew(){ $('overlay').classList.add('show'); $('fErr').textContent=''; loadModels(); $('fGoal').focus(); }
function closeNew(){ $('overlay').classList.remove('show'); $('browser').style.display='none'; }
$('newBtn').onclick = openNew;
const typing = () => /^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement||{}).tagName||'');
const modalOpen = () => $('overlay').classList.contains('show');
document.addEventListener('keydown', e => {
  if (e.key === 'Escape'){ closeNew(); $('copyOverlay').classList.remove('show'); return; }
  if ((e.metaKey || e.ctrlKey) && (e.key === 'b' || e.key === 'B')){
    e.preventDefault(); $('side').classList.toggle('collapsed'); return;
  }
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && modalOpen()){
    e.preventDefault(); startSession(); return;
  }
  if (e.key === 'n' && !typing() && !modalOpen() && !e.metaKey && !e.ctrlKey){
    e.preventDefault(); openNew();
  }
});
async function loadModels(){
  try{
    const m = await (await fetch('/api/models')).json();
    const recommended = new Set(m.recommended || []);
    $('fModel').innerHTML = m.models.map(x => {
      const label = recommended.has(x) ? `${x} · recommended` : x;
      return `<option value="${esc(x)}" ${x===m.default?'selected':''}>${esc(label)}</option>`;
    }).join('');
  }catch(e){}
}
async function pickFolder(){
  if (window.ninexf && window.ninexf.pickFolder){
    try{ const p = await window.ninexf.pickFolder(); if (p) $('fDir').value = p; return; }
    catch(e){}
  }
  browseTo($('fDir').value || '');
}
async function browseTo(path){
  let r; try{ r = await (await fetch('/api/browse?path='+encodeURIComponent(path))).json(); }catch(e){ return; }
  $('fDir').value = r.path;
  const rows = (r.parent
      ? `<div class="bi" onclick="browseTo('${esc(r.parent)}')"><span class="ic">↑</span><span class="nm">..</span></div>`
      : '') +
    (r.dirs.length
      ? r.dirs.map(d=>`<div class="bi" onclick="browseTo('${esc(d.path)}')"><span class="ic">▸</span><span class="nm">${esc(d.name)}</span>${d.is_run?'<span class="tag">9xf run</span>':''}</div>`).join('')
      : '<div class="bi muted"><span class="ic"></span><span class="nm">no subfolders here</span></div>');
  const b = $('browser'); b.style.display = 'flex';
  b.innerHTML =
    `<div class="browpath" title="${esc(r.path)}">${esc(r.path)}${r.is_run?'  ·  existing 9xf run':''}</div>` +
    `<div class="browlist">${rows}</div>` +
    `<div class="browfoot"><span class="sel">use this folder${r.is_run?' (continue run)':''}</span>` +
    `<button class="primary" onclick="$('browser').style.display='none'">Use folder</button></div>`;
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

/* ---------- sidebar toggle ---------- */
$('sideToggle').onclick = () => $('side').classList.toggle('collapsed');

/* ---------- resizable split ---------- */
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
    let w = rect.right - e.clientX;
    w = Math.max(240, Math.min(w, rect.width - 320));
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
