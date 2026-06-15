"""The `9xf app` page — design direction: a flat, pastel, gently goofy workshop.

A soft pale pink/purple workspace for a machine that codes while you sleep. The
home screen is a compact gamified overview — level + XP, a streak heatmap,
achievement tiles, and an interactive pixel mascot ("Looper") who naps when
idle, tinkers while a run is live, and celebrates when a goal ships. Pick a
session and the view flips to the working transcript with a live code-diff
register.

Flat by design: pastel fills, hairline borders, no shadows, no glows, no
gradients. System sans for prose, monospace reserved for numbers/hashes/diffs.

Constraints honored: one self-contained file, no external fonts/assets (fully
offline — the mascot is hand-built pixel art in SVG), prefers-reduced-motion
respected, :focus-visible styles, and color is never the only signal (every
state also carries a glyph or word).
"""

APP_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Loopy</title>
<style>
:root{
  /* flat pale pink/purple pastels — light surfaces, hairline borders */
  --ink:#e1dae9; --panel:#eee8f4; --panel2:#ded6ec; --well:#d5cce4;
  --line:#cbc0dd; --line2:#b9abd0;
  --accent:#9576cf; --accent2:#7a5fb0; --accent-soft:#ece1f9; --accent-bright:#b6a1e4;
  --pink:#d99fcb;
  --green:#5fa07f; --red:#c96d86; --blue:#7e94bf;
  --txt:#3b3348; --dim:#867b96; --faint:#a99fb6;
  --on-accent:#ffffff; --scrim:rgba(59,51,72,.30);
  --hm1:#e0d2f3; --hm2:#c7aee8; --hm3:#a98fd8; --hm4:#8a6cc4;
  --good-bg:#e2f0e9; --bad-bg:#f7e2e8; --err-bg:#f9e8ec;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace;
}
:root[data-theme="dark"]{
  /* same pastels, dark plum surfaces — still flat, no glows */
  --ink:#0a0810; --panel:#121019; --panel2:#1b1724; --well:#0d0a14;
  --line:#201b2c; --line2:#2f2840;
  --accent:#b6a1e4; --accent2:#cbb9f2; --accent-soft:#2d2747; --accent-bright:#cbbaf0;
  --pink:#e0a6cf;
  --green:#7cc49e; --red:#e08aa0; --blue:#9db4dd;
  --txt:#e8e3f1; --dim:#a79db9; --faint:#766d86;
  --on-accent:#1b1726; --scrim:rgba(0,0,0,.55);
  --hm1:#332b50; --hm2:#4a3d77; --hm3:#7a62b8; --hm4:#b6a1e4;
  --good-bg:rgba(124,196,158,.16); --bad-bg:rgba(224,138,160,.16); --err-bg:rgba(224,138,160,.14);
}
*{box-sizing:border-box;margin:0}
html,body{height:100%}
body{
  background:var(--ink);
  color:var(--txt);font:13.5px/1.6 var(--sans);display:flex;overflow:hidden;
  font-variant-numeric:tabular-nums;
  -webkit-font-smoothing:antialiased;
}
::selection{background:var(--accent-soft);color:var(--txt)}
*{scrollbar-width:thin;scrollbar-color:var(--line) transparent}
::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-thumb{background:var(--line);border-radius:3px}
::-webkit-scrollbar-thumb:hover{background:var(--line2)}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-corner{background:transparent}
:focus-visible{outline:1px solid var(--accent);outline-offset:2px}

/* ---------- primitives ---------- */
.lbl{font-size:11px;color:var(--faint)}
button{
  font:inherit;font-size:12.5px;cursor:pointer;color:var(--txt);
  background:var(--panel);border:1px solid var(--line2);border-radius:8px;
  padding:6px 14px;transition:background .12s,border-color .12s,color .12s;
}
button:hover{background:var(--panel2);border-color:var(--accent)}
button:active{transform:translateY(1px)}
button:disabled{opacity:.45;cursor:default;transform:none}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--on-accent);font-weight:600}
button.primary:hover{background:var(--accent2);border-color:var(--accent2);color:var(--on-accent)}
button.danger:hover{border-color:var(--red);color:var(--red);background:var(--panel)}
input,textarea,select{
  font:inherit;font-size:13px;background:var(--well);color:var(--txt);
  border:1px solid var(--line2);border-radius:8px;padding:8px 12px;width:100%;
}
input:focus,textarea:focus,select:focus{outline:none;border-color:var(--accent)}
textarea{resize:vertical;min-height:72px}
.frame{position:relative;border:1px solid var(--line);border-radius:9px;background:var(--panel)}

@keyframes blink{0%,55%{opacity:1}56%,100%{opacity:0}}
.cursor{animation:blink 1.1s steps(1) infinite}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}

/* view switching: home (overview) vs run (transcript) */
#top,#panes{display:none}
body.run #top,body.run #panes{display:flex}
#home{display:none}
body.home #home{display:flex}

/* ---------- sidebar ---------- */
#side{width:256px;min-width:256px;background:var(--well);
  display:flex;flex-direction:column;transition:width .16s ease,min-width .16s ease}
#side.collapsed{width:0;min-width:0;overflow:hidden}
#brand{padding:16px 16px 6px;cursor:pointer;border-radius:10px;margin:6px 8px 0;
  transition:background .14s ease}
#brand:hover{background:var(--panel2)}
#brand .word{font-size:16px;font-weight:600;color:var(--txt)}
#brand .word b{color:var(--accent)}
#brand .tag{font-size:11px;color:var(--faint);margin-top:1px}
#newBtn{margin:12px 14px 4px;display:block;width:calc(100% - 28px)}
.raillabel{padding:12px 18px 4px;font-size:11px;color:var(--faint);display:flex;
  justify-content:space-between;align-items:center}
.raillabel .lvchip{font:600 10px var(--mono);color:var(--accent2);
  background:var(--accent-soft);border-radius:99px;padding:1px 8px}
#runlist{flex:1;overflow-y:auto;padding:0 8px}
.runitem{display:flex;gap:10px;align-items:flex-start;padding:7px 11px;cursor:pointer;
  border-radius:7px;margin-bottom:1px;position:relative;
  transition:background .14s ease}
.runitem:hover{background:var(--panel2)}
.runitem.active{background:var(--accent-soft)}
.runitem.active::before{content:"";position:absolute;left:3px;top:9px;bottom:9px;width:2px;
  border-radius:2px;background:var(--accent)}
.led{width:7px;height:7px;margin-top:6px;border-radius:50%;background:var(--faint);flex:none}
.led.running{background:var(--green)}
.led.finished{background:var(--accent)}
.led.failed{background:var(--red)}
.led.stale{background:var(--accent-bright)}
.runitem .g{font-size:12.5px;color:var(--txt);overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;max-width:196px}
.runitem .s{font-size:11px;color:var(--faint);margin-top:1px}
#railfoot{padding:9px 18px;display:flex;align-items:center;
  justify-content:space-between;font:10.5px var(--mono);color:var(--faint)}
#clock{color:var(--dim)}
#railfoot .rf-right{display:flex;align-items:center;gap:8px}
#themeBtn{border:0;background:transparent;color:var(--faint);cursor:pointer;
  font-size:13px;line-height:1;padding:3px 5px;border-radius:6px;transition:color .12s,background .12s}
#themeBtn:hover{color:var(--accent);background:var(--panel2)}

/* ---------- header: readouts + pulse ---------- */
#main{flex:1;display:flex;flex-direction:column;min-width:0;position:relative}
#top{border-bottom:1px solid var(--line);flex-direction:column}
#readouts{display:flex;align-items:center;gap:24px;padding:12px 22px 9px}
.cell{min-width:0}
.cell .val{margin-top:1px;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cell.goal{flex:1}
.cell.goal .val{font-size:14px;font-weight:500}
.cell.iter .val{font:600 16px/1.3 var(--mono);color:var(--txt)}
.cell.iter .cap{color:var(--faint);font-size:12px;font-weight:400}
.segs{display:flex;gap:3px;margin-top:5px;flex-wrap:wrap;max-width:220px}
.seg{width:8px;height:8px;border-radius:2px;background:var(--line2)}
.seg.done{background:var(--green)}
.seg.cur{background:var(--accent)}
.seg.def{background:var(--red);opacity:.7}
.statusword{font-size:13px}
.statusword.running{color:var(--green)}
.statusword.finished{color:var(--accent)}
.statusword.failed{color:var(--red)}
.statusword.stale{color:var(--accent2)}
.statusword.stopped,.statusword.never{color:var(--dim)}
.cell.actions{display:flex;align-items:center;gap:8px}
#pulsewrap{padding:0 22px 9px}
#pulsewrap .lbl{display:block;margin-bottom:2px}
#pulse{display:block;width:100%}
/* pulse strokes via CSS so they follow the theme (var() can't live in SVG attrs) */
#pulse .pl-base{stroke:var(--line)}
#pulse .pl-pass{stroke:var(--green)}
#pulse .pl-fail{stroke:var(--red)}
#pulse .pl-cur{fill:var(--accent)}

/* ---------- overview / home (flat, mostly boxless) ---------- */
#home{flex:1;overflow-y:auto;flex-direction:column;align-items:center;padding:30px 32px 90px}
.hwrap{width:100%;max-width:700px}

/* header: greeting (left) + level cluster (right), no box */
.hhead{display:flex;align-items:flex-end;justify-content:space-between;gap:24px;flex-wrap:wrap}
.hgreet{display:flex;align-items:center;gap:9px;font-size:18px;font-weight:600;color:var(--txt)}
.hgreet .spark{color:var(--accent)}
.hsub{color:var(--dim);font-size:12.5px;margin-top:3px}
.lvcluster{display:flex;align-items:center;gap:10px;flex:none}
.lvbadge{flex:none;width:38px;height:38px;border-radius:8px;display:flex;
  flex-direction:column;align-items:center;justify-content:center;
  background:var(--accent);color:var(--on-accent)}
.lvbadge .n{font:700 16px/1 var(--mono)}
.lvbadge .k{font-size:7.5px;letter-spacing:.1em;text-transform:uppercase;opacity:.9;margin-top:1px}
.lvinfo{min-width:148px}
.lvtop{display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:5px}
.lvtop .t{font-size:12.5px;font-weight:600;color:var(--txt)}
.lvtop .x{font:10.5px var(--mono);color:var(--faint)}
.xpbar{height:6px;border-radius:3px;background:var(--well);overflow:hidden}
.xpfill{height:100%;border-radius:3px;background:var(--accent);
  width:0;transition:width .6s cubic-bezier(.4,0,.2,1)}

/* thin dividers + uppercase section labels give structure without boxes */
.hrule{height:1px;background:var(--line);margin:20px 0}
.hsec{font-size:10.5px;color:var(--faint);margin-bottom:12px;letter-spacing:.05em;
  text-transform:uppercase;display:flex;align-items:center;justify-content:space-between}
.hsec .tag{text-transform:none;letter-spacing:0;font-size:11px}

/* flat stat strip — no boxes, just numbers */
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:14px}
.stat .sk{font-size:10.5px;color:var(--faint)}
.stat .sv{font:600 21px/1.15 var(--sans);color:var(--txt);margin-top:3px}
.stat .sv small{font-size:11px;color:var(--dim);font-weight:400}
.stat .sv .em{color:var(--accent)}
.statnote{margin-top:11px;font-size:11px;color:var(--faint)}

/* heatmap — boxless, legend sits beside the grid so space reads even */
.heatrow{display:flex;align-items:flex-end;gap:18px;flex-wrap:wrap}
.heatscroll{overflow-x:auto;padding-bottom:2px}
.heat{display:grid;grid-template-rows:repeat(7,11px);grid-auto-flow:column;
  grid-auto-columns:11px;gap:3px;width:max-content}
.hc{width:11px;height:11px;border-radius:2px;background:var(--line)}
.hc.l1{background:var(--hm1)}
.hc.l2{background:var(--hm2)}
.hc.l3{background:var(--hm3)}
.hc.l4{background:var(--hm4)}
.heatleg{display:flex;align-items:center;gap:5px;font-size:11px;color:var(--faint)}
.heatleg .hc{width:9px;height:9px}

/* achievements — flat circles, name on hover */
.badges{display:flex;flex-wrap:wrap;gap:9px}
.badge{cursor:default;transition:transform .14s}
.badge.unlk:hover{transform:translateY(-2px)}
.badge .g{font-size:16px;line-height:1;color:var(--on-accent);
  display:inline-flex;width:36px;height:36px;align-items:center;justify-content:center;
  border-radius:50%;background:var(--accent)}
.badge.lock{opacity:.5}
.badge.lock .g{color:var(--faint);background:var(--panel2)}

/* ---------- pixel mascot ---------- */
#mascot{position:fixed;right:24px;bottom:20px;z-index:40;cursor:pointer;
  display:flex;flex-direction:column;align-items:center;user-select:none;
  -webkit-user-select:none}
#mascot svg{width:80px;height:80px;image-rendering:pixelated}
#mascot svg .m-tip{fill:var(--mascot-tip)}   /* antenna tip — themed via CSS */
/* play mode: JS drives transform; physics perches Looper on transcript cards */
#mascot.play{left:0;top:0;right:auto;bottom:auto;animation:none;
  transform-origin:50% 100%;will-change:transform;z-index:12}
#mascot.play svg{width:44px;height:44px}
#mascot.idle{animation:bob 3.2s ease-in-out infinite}
#mascot.working{animation:bob 1.3s ease-in-out infinite}
#mascot.happy{animation:hop .5s ease-in-out infinite}
#mascot.poke{animation:squish .32s ease}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(-6px)}}
@keyframes hop{0%,100%{transform:translateY(0)}40%{transform:translateY(-14px)}70%{transform:translateY(-3px)}}
@keyframes squish{0%{transform:scale(1,1)}40%{transform:scale(1.12,.86)}100%{transform:scale(1,1)}}
#bubble{position:absolute;bottom:86px;right:0;max-width:190px;white-space:normal;
  background:var(--panel);border:1px solid var(--line2);color:var(--txt);
  font-size:12px;line-height:1.45;padding:7px 11px;border-radius:11px;
  opacity:0;transform:translateY(6px) scale(.96);
  transition:opacity .18s ease,transform .18s ease;pointer-events:none}
#bubble.show{opacity:1;transform:translateY(0) scale(1)}
#bubble::after{content:"";position:absolute;bottom:-6px;right:30px;width:10px;height:10px;
  background:var(--panel);border-right:1px solid var(--line2);border-bottom:1px solid var(--line2);
  transform:rotate(45deg)}
#zzz{position:absolute;top:-2px;right:4px;font:600 13px var(--mono);color:var(--faint);
  opacity:0}
#mascot.sleep #zzz{animation:floatz 2.6s ease-in-out infinite}
@keyframes floatz{0%{opacity:0;transform:translateY(4px)}30%{opacity:.8}100%{opacity:0;transform:translateY(-12px)}}
.xppop{position:absolute;top:6px;right:30px;font:700 13px var(--mono);color:var(--accent);
  pointer-events:none;animation:xprise .9s ease forwards}
@keyframes xprise{0%{opacity:0;transform:translateY(0)}20%{opacity:1}100%{opacity:0;transform:translateY(-26px)}}
/* little thought emotes (?, ♥, …) Looper puffs out while reacting */
.emote{position:absolute;bottom:50px;left:50%;font:700 15px var(--mono);color:var(--accent);
  pointer-events:none;animation:emoteRise 1.1s ease forwards}
@keyframes emoteRise{
  0%{opacity:0;transform:translate(-50%,6px) scale(.5)}
  25%{opacity:1;transform:translate(-50%,-7px) scale(1)}
  100%{opacity:0;transform:translate(-50%,-24px) scale(1)}}

/* ---------- panes ---------- */
#panes{flex:1;min-height:0}
body.nodiff #gutter,body.nodiff #diffpane{display:none}   /* diff register collapsed */
.panehead{padding:12px 22px 4px;font-size:11px;color:var(--faint);display:flex;
  justify-content:space-between;align-items:center;gap:8px}
#chatwrap{flex:1;display:flex;flex-direction:column;min-width:280px}
.gutter{flex:none;width:6px;cursor:col-resize;background:transparent;transition:background .12s}
.gutter:hover,.gutter.drag{background:var(--line2)}
/* icon button: quiet, square, for chrome controls (collapse, etc.) */
.iconbtn{border:0;background:transparent;color:var(--dim);padding:5px 7px;
  border-radius:7px;font-size:14px;line-height:1}
.iconbtn:hover{background:var(--panel2);color:var(--txt)}
#chat{flex:1;overflow-y:auto;padding:12px 22px 18px;scroll-behavior:smooth}
.miniToggle{font:inherit;font-size:10.5px;color:var(--faint);background:transparent;
  border:1px solid var(--line);border-radius:99px;padding:2px 9px;cursor:pointer;
  transition:color .12s,border-color .12s,background .12s}
.miniToggle:hover{color:var(--dim);border-color:var(--line2)}
.miniToggle.on{color:var(--accent);border-color:var(--accent);background:var(--accent-soft)}
#statusbar{display:none;border-top:1px solid var(--line);
  padding:9px 22px;font-size:12.5px;color:var(--dim);align-items:center;gap:10px}
#statusbar .cursor{color:var(--accent);font-weight:700}
#statusbar b{color:var(--txt)}

/* ---------- transcript records: collapsible cards ---------- */
.rec{background:var(--panel);border:1px solid transparent;border-radius:8px;margin:0 auto 6px;
  max-width:740px;overflow:hidden;transition:border-color .18s ease}
.rec.selected{border-color:var(--accent-bright)}
.rechead{display:flex;align-items:center;gap:10px;padding:10px 14px;cursor:pointer;
  font-size:11.5px;color:var(--dim);user-select:none;transition:background .14s ease}
.rechead:hover{background:var(--panel2)}
.chev{flex:none;color:var(--faint);font-size:9px;width:9px;
  transition:transform .2s cubic-bezier(.4,0,.2,1)}
.rec.open .chev,.actgroup.open .chev{transform:rotate(90deg)}
.recno{flex:none;font:600 11.5px var(--mono);color:var(--dim)}
.recmode{flex:none;color:var(--faint)}
.rectitle{flex:1;min-width:0;color:var(--txt);font-size:12.5px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.flag{flex:none;padding:1px 8px;border-radius:99px;background:var(--panel2);color:var(--dim);font-size:10.5px}
.flag.warn{background:var(--accent-soft);color:var(--accent2)}
.flag.bad{background:var(--bad-bg);color:var(--red)}
.flag.good{background:var(--good-bg);color:var(--green)}
.verdict{margin-left:auto;font-weight:600;font-size:11.5px}
.verdict.ok{color:var(--green)}
.verdict.bad{color:var(--red)}
/* smooth height animation via grid 0fr→1fr (handles arbitrary content height) */
.recbody{display:grid;grid-template-rows:0fr;transition:grid-template-rows .22s cubic-bezier(.4,0,.2,1)}
.rec.open .recbody{grid-template-rows:1fr}
.rbi{overflow:hidden;min-height:0;padding:0 14px 0 33px}
.rec.open .rbi{padding-bottom:12px}
.recline{display:flex;gap:10px;padding-top:8px}
.recline .lbl{flex:none;width:34px;font-size:11px;color:var(--faint);padding-top:1px}
.recline .txt{font-size:12.5px;line-height:1.55;word-break:break-word;min-width:0}
.recline.plan .txt{color:var(--txt)}
.recline.execl .txt{color:var(--dim)}
.files{display:flex;flex-wrap:wrap;gap:6px;padding:8px 0 0 44px}
.file{font:11px var(--mono);background:var(--panel2);border-radius:6px;padding:2px 8px;color:var(--blue)}
.errblock{margin:8px 0 0 44px;border-radius:8px;padding:7px 10px;
  font:11.5px/1.5 var(--mono);color:var(--red);word-break:break-word;
  background:var(--err-bg)}
.streampreview{margin:6px 0 0 44px;border-radius:8px;padding:8px 11px;max-height:120px;overflow:hidden;
  font:11.5px/1.55 var(--mono);color:var(--dim);white-space:pre-wrap;word-break:break-word;
  background:var(--panel2);border:1px solid var(--line)}
.streampreview .cursor{color:var(--accent);font-weight:700}
.recmeta{display:flex;gap:14px;padding:10px 0 0 44px;font-size:11px;color:var(--faint)}
.recmeta .hash{font-family:var(--mono);color:var(--accent2);cursor:pointer}
.recmeta .hash:hover{color:var(--accent);text-decoration:underline}

/* activity / process stream — quieter, collapsible as one block */
.actgroup{max-width:740px;margin:0 auto 6px;border-radius:8px;
  background:var(--well);transition:background .14s}
.actgroup:hover{background:var(--panel2)}
.acthead{display:flex;align-items:center;gap:9px;padding:7px 14px;cursor:pointer;
  font-size:11px;color:var(--dim);user-select:none}
.acthead .chev{color:var(--dim);opacity:.7}
.actcount{flex:none;font:600 10.5px var(--mono);color:var(--dim)}
.actpath{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  color:var(--faint)}
.actlast{flex:none;max-width:46%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  color:var(--dim);opacity:.85}
.actbody{display:grid;grid-template-rows:0fr;transition:grid-template-rows .22s cubic-bezier(.4,0,.2,1)}
.actgroup.open .actbody{grid-template-rows:1fr}
.abi{overflow:hidden;min-height:0}
.actgroup.open .abi{padding:0 14px 8px 33px}
.actrow{display:flex;gap:10px;padding-top:5px;font-size:11.5px;color:var(--faint)}
.actrow .k{flex:none;width:64px;color:var(--dim);font-weight:500}

/* milestones */
.evt{display:flex;align-items:center;justify-content:center;gap:8px;max-width:740px;
  margin:8px auto;color:var(--faint);font-size:11.5px;text-align:center}
.evt b{color:var(--dim)}
.evt.finish{color:var(--accent)}
.evt.finish b{color:var(--accent)}

/* empty state (within a run with no entries yet) */
.empty{margin:auto;text-align:center;padding:60px 30px;max-width:480px}
.empty h2{font-size:21px;font-weight:600;margin-bottom:12px;color:var(--txt);line-height:1.3}
.empty h2 b{color:var(--accent)}
.empty p{color:var(--dim);font-size:13.5px;margin-bottom:26px}

/* ---------- diff register ---------- */
#diffpane{flex:none;width:46%;min-width:240px;display:flex;flex-direction:column;
  min-height:0;background:var(--well);border-left:1px solid var(--line)}
#diffTitle .hash{font-family:var(--mono);color:var(--accent)}
#diff{flex:1;overflow:auto;padding:10px 22px 16px;font:11.5px/1.6 var(--mono);
  white-space:pre;color:var(--dim)}
#diff.swap{animation:fadein .2s ease}
@keyframes fadein{from{opacity:0}to{opacity:1}}
#diff .add{color:var(--green)}
#diff .del{color:var(--red)}
#diff .hunk{color:var(--accent2)}
#diff .file{font:inherit;background:transparent;border-radius:0;padding:0;
  color:var(--blue);font-weight:700}
#diff .ctx{color:var(--faint)}

/* ---------- modal ---------- */
#overlay,#copyOverlay,#onboardOverlay,#settingsOverlay,#aboutOverlay{position:fixed;inset:0;background:var(--scrim);display:none;
  align-items:center;justify-content:center;z-index:50}
#overlay.show,#copyOverlay.show,#onboardOverlay.show,#settingsOverlay.show,#aboutOverlay.show{display:flex}
.modal{width:560px;max-width:94vw;max-height:90vh;overflow-y:auto;padding:26px;border-radius:10px}
.modal h2{font-size:16px;font-weight:600;color:var(--txt);margin-bottom:18px}
.field{margin-bottom:16px}
.field .lbl{display:block;margin-bottom:6px}
.row{display:flex;gap:10px}.row>*{flex:1}
.seg-switch{display:flex;border:1px solid var(--line2);border-radius:8px;overflow:hidden}
.seg-switch button{flex:1;border:0;border-radius:0;background:var(--panel)}
.seg-switch button.on{background:var(--accent);color:var(--on-accent);font-weight:600}
.modal .actions{display:flex;justify-content:flex-end;gap:10px;margin-top:20px}
/* in-app folder browser (plain-browser fallback) — a mini file dialog */
#browser{border:1px solid var(--line2);border-radius:10px;margin-top:8px;background:var(--well);
  overflow:hidden;display:none;flex-direction:column;max-height:300px}
.browpath{flex:none;padding:8px 12px;border-bottom:1px solid var(--line);
  font:11.5px var(--mono);color:var(--dim);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.browlist{flex:1;overflow-y:auto;padding:4px}
#browser .bi{padding:7px 10px;cursor:pointer;display:flex;gap:9px;align-items:center;
  border-radius:7px;font-size:12.5px;color:var(--txt)}
#browser .bi:hover{background:var(--panel2)}
#browser .bi.muted{color:var(--faint);cursor:default}
#browser .bi.muted:hover{background:transparent}
#browser .bi .ic{flex:none;width:12px;color:var(--faint);text-align:center}
#browser .bi .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#browser .bi .tag{flex:none;color:var(--accent2);font-size:10px;background:var(--accent-soft);
  border-radius:99px;padding:0 7px}
.browfoot{flex:none;padding:8px 10px;border-top:1px solid var(--line);display:flex;
  align-items:center;gap:10px}
.browfoot .sel{flex:1;min-width:0;font:11px var(--mono);color:var(--faint);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.browfoot button{flex:none;padding:5px 13px;font-size:11.5px}
.formerr{color:var(--red);font-size:12px;margin-top:8px;min-height:14px}
.hint{color:var(--faint);font-size:11.5px;margin-top:6px}
.kbd{font:10.5px var(--mono);color:var(--faint);border:1px solid var(--line2);
  border-radius:5px;padding:1px 5px;background:var(--well)}
.modal .actions .sp{margin-right:auto;color:var(--faint);font-size:11px;display:flex;
  align-items:center;gap:6px}
.hero{display:grid;grid-template-columns:1.25fr .75fr;gap:20px;align-items:stretch}
.heroCard{padding:20px;border:1px solid var(--line);border-radius:12px;background:var(--panel)}
.heroCard h1{font-size:32px;line-height:1.05;margin-bottom:8px}
.heroCard h1 b{color:var(--accent)}
.heroCard p{font-size:13px;color:var(--dim);max-width:48ch}
.heroActions{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
.heroActions button,.heroActions a{display:inline-flex;align-items:center;justify-content:center;
  text-decoration:none}
.heroMeta{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:18px}
.heroChip{padding:11px 12px;border:1px solid var(--line);border-radius:10px;background:var(--well)}
.heroChip .k{font-size:10px;color:var(--faint);text-transform:uppercase;letter-spacing:.06em}
.heroChip .v{margin-top:5px;font-size:12px;color:var(--txt)}
.heroAside{display:flex;flex-direction:column;justify-content:space-between;gap:16px}
.heroMascot{display:flex;align-items:center;gap:14px}
.heroMascot .art{width:88px;height:88px;flex:none}
.heroMascot .note{font-size:12.5px;color:var(--dim)}
.startstrip{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0 2px}
.pillbtn{background:var(--well)}
.sectionTop{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}
.onboard{width:720px;max-width:95vw;padding:0;overflow:hidden}
.onTop{display:grid;grid-template-columns:240px 1fr}
.onMascot{padding:28px 22px;border-right:1px solid var(--line);background:var(--well);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px}
.onMascotArt{width:124px;height:124px}
.onBubble{padding:12px 14px;border:1px solid var(--line2);border-radius:14px;background:var(--panel);font-size:12.5px;color:var(--txt);line-height:1.55}
.onMain{padding:26px}
.onKicker{font-size:10.5px;color:var(--faint);letter-spacing:.08em;text-transform:uppercase}
.onTitle{font-size:24px;line-height:1.15;margin:8px 0 8px}
.onText{font-size:13px;color:var(--dim);margin-bottom:18px}
.choiceGrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.choice{padding:16px;border:1px solid var(--line);border-radius:12px;background:var(--panel);cursor:pointer}
.choice:hover,.choice.active{border-color:var(--accent);background:var(--panel2)}
.choice b{display:block;font-size:13px;margin-bottom:5px}
.choice span{display:block;font-size:12px;color:var(--dim)}
.onActions{display:flex;justify-content:space-between;gap:10px;margin-top:20px}
.miniNote{font-size:11.5px;color:var(--faint);margin-top:8px}
.quietCard{padding:14px;border:1px solid var(--line);border-radius:12px;background:var(--well)}
.quietCard h3{font-size:13px;margin-bottom:6px}
@media (max-width:720px){
  .stats{grid-template-columns:repeat(3,1fr)}
  .hero,.onTop,.choiceGrid{grid-template-columns:1fr}
  .onMascot{border-right:0;border-bottom:1px solid var(--line)}
  .heroMeta{grid-template-columns:1fr}
}
</style></head><body class="home">

<aside id="side">
  <div id="brand" onclick="goHome()" title="Home" role="button" tabindex="0">
    <div class="word">Lo<b>opy</b></div>
    <div class="tag">local coding loops</div>
  </div>
  <button id="newBtn" class="primary" title="New project  (n)" aria-label="New project">+ New project</button>
  <div class="raillabel"><span>Sessions</span><span class="lvchip" id="railLevel" style="display:none"></span></div>
  <div id="runlist" role="list"></div>
  <div id="railfoot"><span id="clock">--:--:--</span>
    <span class="rf-right"><span id="railStreak"></span>
      <button id="themeBtn" title="Toggle light / dark  (theme)" aria-label="Toggle dark mode">☾</button>
    </span></div>
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
        <div class="val statusword never" id="topPill">no run</div></div>
      <div class="cell actions">
        <button id="copyBtn" style="display:none">Copy diagnostics</button>
        <button id="stopBtn" class="danger" style="display:none">Stop</button>
        <button id="resumeBtn" class="primary" style="display:none">Resume</button>
      </div>
    </div>
    <div id="pulsewrap" style="display:none"><span class="lbl">Pulse — one tick per iteration</span><div id="pulse"></div></div>
  </header>

  <section id="home" aria-label="overview">
    <div class="hwrap">
      <div class="hero">
        <div class="heroCard">
          <div class="onKicker">Loopy v1</div>
          <h1>Your local <b>coding loop</b> with a cute co-pilot.</h1>
          <p>Pick a folder, choose a model, and let Loopy plan, build, test, and commit on your machine. No account, no email capture, no hosted runtime.</p>
          <div class="heroActions">
            <button class="primary" onclick="launchPrimaryFlow()">Get started</button>
            <button onclick="openExistingProject()">Open existing project</button>
            <button onclick="openSettings()">Settings</button>
            <button onclick="openAbout()">About</button>
            <button onclick="openDocs()">Docs</button>
          </div>
          <div class="heroMeta">
            <div class="heroChip"><div class="k">Install</div><div class="v">macOS-first desktop release</div></div>
            <div class="heroChip"><div class="k">Models</div><div class="v" id="heroModel">Local Ollama or your own API key</div></div>
            <div class="heroChip"><div class="k">Storage</div><div class="v">Settings and keys stay on this Mac</div></div>
          </div>
        </div>
        <div class="heroAside heroCard">
          <div class="heroMascot">
            <div class="art" id="homeMascotArt"></div>
            <div>
              <div style="font-size:14px;font-weight:600">Loopy is on guide duty.</div>
              <div class="note" id="homeMascotNote">I’ll help you pick a model and get your first project running.</div>
            </div>
          </div>
          <div class="quietCard">
            <h3>Start page</h3>
            <div class="note">Use <b>Get started</b> on a first launch, or open an existing Loopy project to jump straight into the transcript and diff view.</div>
          </div>
        </div>
      </div>

      <div class="hhead">
        <div>
          <div class="hgreet"><span class="spark">✦</span> <span id="greetLine">What's up next?</span></div>
          <div class="hsub" id="greetSub">Set a goal and a local model will plan, build, test, and commit on its own.</div>
        </div>
        <div class="lvcluster">
          <div class="lvbadge"><span class="n" id="lvNum">1</span><span class="k">lvl</span></div>
          <div class="lvinfo">
            <div class="lvtop"><span class="t" id="lvTitle">Apprentice</span><span class="x" id="lvXp">0 XP</span></div>
            <div class="xpbar"><div class="xpfill" id="xpFill"></div></div>
          </div>
        </div>
      </div>

      <div class="hrule"></div>
      <div class="sectionTop">
        <div class="hsec" style="margin:0"><span>Recent momentum</span><span class="tag" id="streakTag"></span></div>
        <div class="startstrip">
          <button class="pillbtn" onclick="openNew()">New project</button>
          <button class="pillbtn" onclick="openSettings()">Change defaults</button>
          <button class="pillbtn" onclick="openAbout()">Check updates</button>
        </div>
      </div>
      <div class="stats" id="stats"></div>
      <div class="statnote" id="statnote"></div>

      <div class="hrule"></div>
      <div class="hsec"><span>Activity · last 20 weeks</span><span class="tag"></span></div>
      <div class="heatrow">
        <div class="heatscroll"><div class="heat" id="heat"></div></div>
        <div class="heatleg">less
          <i class="hc"></i><i class="hc l1"></i><i class="hc l2"></i><i class="hc l3"></i><i class="hc l4"></i>
          more</div>
      </div>

      <div class="hrule"></div>
      <div class="hsec"><span>Achievements</span><span class="tag" id="achTag"></span></div>
      <div class="badges" id="badges"></div>
    </div>
  </section>

  <div id="panes">
    <section id="chatwrap" aria-label="transcript">
      <div class="panehead"><span>Transcript</span>
        <span style="display:flex;align-items:center;gap:8px">
          <span id="livehint"></span>
          <button id="playBtn" class="miniToggle" title="Let Loopy hop around your transcript">✦ Loopy</button>
          <button id="diffBtn" class="miniToggle" title="Show or hide the diff register">Diff</button>
        </span></div>
      <div id="chat"></div>
      <div id="statusbar"></div>
    </section>
    <div class="gutter" id="gutter" role="separator" aria-orientation="vertical" title="Drag to resize"></div>
    <section id="diffpane" aria-label="diff register">
      <div class="panehead"><span id="diffTitle">Diff register</span>
        <span style="display:flex;align-items:center;gap:8px"><span id="diffPin"></span>
          <button class="iconbtn" onclick="toggleDiff()" title="Hide diff register" aria-label="Hide diff register">✕</button>
        </span></div>
      <div id="diff"><span class="ctx">select an iteration record to inspect its commit</span></div>
    </section>
  </div>
</main>

<!-- Loopy, the pixel mascot -->
<div id="mascot" class="idle" title="hi, I'm Loopy" role="button" tabindex="0" aria-label="Loopy the mascot">
  <div id="bubble" aria-live="polite"></div>
  <div id="zzz">z</div>
  <div id="mascotArt"></div>
</div>

<div id="overlay" role="dialog" aria-modal="true"><div class="modal frame">
  <h2 id="composeTitle">New project</h2>
  <div class="field"><span class="lbl">Folder</span>
    <div class="row"><input id="fDir" placeholder="/Users/you/runs/my-tool" autocomplete="off">
      <button style="flex:0 0 auto" onclick="pickFolder()">Browse</button></div>
    <div id="browser" style="display:none"></div>
    <div class="hint" id="composeHint">A new or empty folder, or an existing Loopy project to continue.</div>
  </div>
  <div class="field" id="goalField"><span class="lbl">Goal — the unchanging north star</span>
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

<div id="onboardOverlay" role="dialog" aria-modal="true"><div class="modal frame onboard">
  <div class="onTop">
    <div class="onMascot">
      <div class="onMascotArt" id="onboardMascotArt"></div>
      <div class="onBubble" id="onboardBubble">Hi, I’m Loopy. I’ll help you get this machine ready without any sign-up ceremony.</div>
    </div>
    <div class="onMain">
      <div id="onboardBody"></div>
    </div>
  </div>
</div></div>

<div id="settingsOverlay" role="dialog" aria-modal="true"><div class="modal frame">
  <h2>Loopy settings</h2>
  <div class="field"><span class="lbl">Default mode</span>
    <div class="seg-switch" role="radiogroup">
      <button id="sLocalBtn" onclick="setSettingsMode('ollama')">Local with Ollama</button>
      <button id="sApiBtn" onclick="setSettingsMode('api')">API key</button>
    </div>
  </div>
  <div class="row">
    <div class="field"><span class="lbl">Local model</span><select id="sLocalModel"></select></div>
    <div class="field"><span class="lbl">API model</span><select id="sApiModel"></select></div>
  </div>
  <div class="field"><span class="lbl">Ollama endpoint</span><input id="sOllamaEndpoint" placeholder="http://localhost:11434"></div>
  <div class="field"><span class="lbl">API key</span><input id="sApiKey" type="password" placeholder="stored locally on this Mac"></div>
  <div class="hint" id="settingsSavedHint">Loopy stores app defaults separately from each project’s `9xf.config.json`.</div>
  <div class="formerr" id="settingsErr" role="alert"></div>
  <div class="actions">
    <button onclick="closeSettings()">Close</button>
    <button class="primary" onclick="saveSettingsForm()">Save settings</button>
  </div>
</div></div>

<div id="aboutOverlay" role="dialog" aria-modal="true"><div class="modal frame">
  <h2>About Loopy</h2>
  <div class="quietCard">
    <h3 id="aboutVersion">Version</h3>
    <div class="note">Loopy is a local-first coding loops app. Runs, settings, and API keys stay on your machine.</div>
  </div>
  <div class="row" style="margin-top:16px">
    <button onclick="openDocs()">Docs</button>
    <button onclick="openReleases()">Check updates</button>
  </div>
  <div class="actions">
    <button onclick="closeAbout()">Close</button>
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
let openActs = new Set();
let appState = null, appSettings = null, settingsMode = 'ollama', composeMode = 'new';
let selectedDirIsRun = false;
const DOCS_URL = 'https://github.com/Manas-Kandi/9xf-loops';
const RELEASES_URL = 'https://github.com/Manas-Kandi/9xf-loops/releases';
function openExternal(url){
  if (window.ninexf && window.ninexf.openExternal) return window.ninexf.openExternal(url);
  return window.open(url, '_blank', 'noopener');
}
function openDocs(){ return openExternal(DOCS_URL); }
function openReleases(){ return openExternal(RELEASES_URL); }

/* instrument clock */
setInterval(() => { $('clock').textContent = new Date().toISOString().slice(11,19) + ' UTC'; }, 1000);

/* ---------- view switching: home vs run ---------- */
function goHome(){
  current = null; pinnedCommit = null; lastRender = ''; lastRail = '';
  document.body.className = 'home';
  leavePlay();
  tickStats(); tickRuns(); setMascotFromStats();
}

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
    '<div class="s" style="padding:12px 16px;color:var(--faint);font-size:11px">no projects yet — hit New project</div>';
  if (html !== lastRail){ $('runlist').innerHTML = html; lastRail = html; }
  // any run live? nudge the mascot into work mode while on the home screen
  if (!current) mascotWorkingHint = runs.some(r => r.status === 'running');
}
function selectRun(dir){
  current = dir; pinnedCommit = null; lastRender = ''; lastRail = '';
  openIters = new Set(); touched = new Set(); autoIter = null; lastEntries = [];
  openActs = new Set();
  document.body.className = 'run' + (diffShown ? '' : ' nodiff');
  $('chat').innerHTML = '<div class="empty"><p>spinning up…</p></div>';
  tickRun(); tickRuns();
}

/* ---------- gamified overview ---------- */
const LEVEL_TITLES = ['Apprentice','Tinkerer','Builder','Engineer','Architect',
  'Maestro','Virtuoso','Luminary','Legend'];
function levelTitle(l){ return LEVEL_TITLES[Math.min(l-1, LEVEL_TITLES.length-1)] || 'Legend'; }
function hourLabel(h){
  if (h === null || h === undefined) return '—';
  const ap = h < 12 ? 'AM' : 'PM'; const hr = h % 12 || 12; return `${hr} ${ap}`;
}
let lastStats = null;
function renderHome(s){
  lastStats = s;
  const p = s.progress || {level:1,xp:0,pct:0};
  $('lvNum').textContent = p.level;
  $('lvTitle').textContent = levelTitle(p.level);
  $('lvXp').textContent = `${p.xp.toLocaleString()} XP`;
  $('xpFill').style.width = Math.max(4, p.pct) + '%';
  $('railLevel').style.display = ''; $('railLevel').textContent = `Lv ${p.level}`;

  const stats = [
    ['Sessions', s.sessions],
    ['Iterations', s.iterations],
    ['Goals', `<span class="em">${s.goals}</span>`],
    ['Pass rate', `${s.pass_rate}<small>%</small>`],
    ['Streak', `${s.current_streak}<small> d</small>`],
  ];
  $('stats').innerHTML = stats.map(([k,v]) =>
    `<div class="stat"><div class="sk">${k}</div><div class="sv">${v}</div></div>`).join('');
  $('statnote').textContent = s.sessions
    ? `${s.active_days} active day${s.active_days===1?'':'s'} · ${s.tasks_done} tasks done · mostly ${s.favorite_model}`
    : '';

  $('heat').innerHTML = (s.heatmap||[]).map(d =>
    `<i class="hc l${d.level}" title="${d.date}: ${d.count} iteration${d.count===1?'':'s'}"></i>`).join('');
  $('streakTag').textContent = s.longest_streak
    ? `longest ${s.longest_streak}d · peak ${hourLabel(s.peak_hour)}` : '';

  $('badges').innerHTML = (s.achievements||[]).map(a =>
    `<div class="badge ${a.unlocked?'unlk':'lock'}" title="${esc(a.name)} — ${esc(a.blurb)}"><div class="g">${a.unlocked?a.glyph:'🔒'}</div></div>`).join('');
  $('achTag').textContent = `${s.unlocked_count}/${(s.achievements||[]).length}`;
  $('railStreak').textContent = s.current_streak ? `🔥 ${s.current_streak}d` : '';

  $('greetSub').textContent = s.sessions
    ? "Loopy's kept the lights on — pick a project, or start something new."
    : 'Set a goal and a local model will plan, build, test, and commit on its own.';
  $('greetLine').textContent = s.sessions ? greetByLevel(p.level) : "What's up next?";
  if (appSettings){
    $('heroModel').textContent = appSettings.preferred_mode === 'api'
      ? `Saved API model: ${appSettings.api_model}`
      : `Saved local model: ${appSettings.preferred_model}`;
    $('homeMascotNote').textContent = appSettings.onboarding_complete
      ? 'Your defaults are saved. I can open an existing project or kick off a fresh one.'
      : 'First launch? I’ll walk you through model setup in under a minute.';
  }
}
function greetByLevel(l){
  if (l >= 7) return 'Welcome back, legend.';
  if (l >= 4) return 'Welcome back, builder.';
  if (l >= 2) return 'Good to see you again.';
  return 'Ready for the night shift?';
}
async function tickStats(){
  if (current) return;            // only refresh the overview while it's visible
  let s; try{ s = await (await fetch('/api/stats')).json(); }catch(e){ return; }
  if (s && !s.error) renderHome(s);
}

/* ---------- pixel mascot: "Looper" ----------
   A composited 16x16 sprite: one fixed BODY plus swappable FACE / ARMS / LEGS
   overlays. Animations are short sequences of those combos, so a handful of
   hand-drawn parts yields walking, thinking, cheering, flossing, even kicking
   a ball around — fully offline, no text, all feeling on the face + body. */
const COL = {B:'#c2a7e2', D:'#9f86d0', E:'#463a57', L:'#ffffff',
  M:'#9270c4', C:'#e3a9d0', H:'#9f86d0'};            // H = hand/arm
const BODY = [
  '................',
  '.......A........',   // antenna tip (themed)
  '.......D........',
  '....BBBBBBBB....',
  '...BBBBBBBBBB...',
  '..BBBBBBBBBBBB..',
  '..BBBBBBBBBBBB..',
  '..BBBBBBBBBBBB..',
  '..BBBBBBBBBBBB..',
  '..BCBBBBBBBBCB..',   // cheeks
  '..BBBBBBBBBBBB..',
  '...BBBBBBBBBB...',
  '....BBBBBBBB....',
  '................',
  '................',
  '................',
];
const FACES = {        // eyes rows 6-7, mouth rows 8-9
  idle:     {6:'....LE....LE....', 7:'....EE....EE....', 9:'.....MMMMMM.....'},
  blink:    {7:'....EE....EE....', 9:'.....MMMMMM.....'},
  happy:    {6:'....EE....EE....', 9:'....MMMMMMMM....'},
  sleep:    {7:'....EE....EE....', 9:'.......MM.......'},
  sad:      {7:'....EE....EE....', 8:'......MMMM......', 9:'.....M....M.....'},
  confused: {6:'....LE..........', 7:'....EE....E.....', 9:'.....M.MM.M.....'},
  focus:    {7:'....EE....EE....', 9:'.......MM.......'},
  surprise: {6:'....EE....EE....', 7:'....EE....EE....', 9:'......MMMM......'},
  content:  {6:'....LE....LE....', 7:'....EE....EE....', 9:'......MM........'},
};
const ARMS = {
  down:   {8:'.H............H.', 9:'.H............H.'},
  swingA: {7:'.H..............', 9:'..............H.'},
  swingB: {7:'..............H.', 9:'.H..............'},
  up:     {3:'.H............H.', 4:'.H............H.'},
  chin:   {9:'....H.........H.'},
  face:   {6:'....HH..........', 9:'..............H.'},
  head:   {3:'....H...........', 4:'.H............H.'},
  flossA: {6:'..............H.', 10:'.H..............'},
  flossB: {6:'.H..............', 10:'..............H.'},
  out:    {7:'.H............H.'},
  hip:    {9:'...H..........H.'},
};
const LEGS = {
  stand: {13:'....BB....BB....', 14:'....DD....DD....'},
  walkA: {13:'...BB......BB...', 14:'..DD........DD..'},
  walkB: {13:'......BBBB......', 14:'......DDDD......'},
  tuck:  {13:'.....DDDD.......'},
  kick:  {13:'....BB....BBBB..', 14:'....DD........D.'},
  sit:   {13:'...DDDDDDDDDD...'},
};
// animations: frames are [face, arms, legs, holdFrames, ball?]  ball=[x,y,colour]
const ANIM = {
  idle:    {loop:true, frames:[['idle','down','stand',90],['blink','down','stand',6],
            ['idle','down','stand',70],['idle','down','stand',46]]},
  cheer:   {next:'idle', frames:[['happy','up','stand',10],['happy','up','tuck',9],
            ['happy','up','stand',9],['happy','up','tuck',9],['happy','up','stand',16]]},
  dance:   {next:'idle', frames:[['happy','hip','walkA',9],['happy','out','walkB',9],
            ['happy','hip','walkA',9],['happy','out','walkB',9],['happy','up','stand',12]]},
  floss:   {next:'idle', frames:[['happy','flossA','stand',8],['happy','flossB','stand',8],
            ['happy','flossA','stand',8],['happy','flossB','stand',8],['happy','flossA','stand',9]]},
  joy:     {next:'idle', frames:[['surprise','down','stand',6],['happy','up','tuck',12],
            ['happy','up','stand',8],['happy','up','tuck',10],['happy','up','stand',12]]},
  slump:   {next:'idle', frames:[['surprise','down','stand',7],['sad','down','sit',46],['sad','down','sit',46]]},
  facepalm:{next:'idle', frames:[['sad','face','stand',28],['sad','face','stand',40]]},
  scratch: {next:'idle', frames:[['confused','head','stand',14],['confused','head','walkA',14],
            ['confused','head','stand',16]]},
  think:   {next:'idle', frames:[['focus','chin','stand',46],['focus','chin','stand',34]]},
  stretch: {next:'idle', frames:[['focus','up','stand',16],['content','up','tuck',12],['idle','down','stand',14]]},
  soccer:  {next:'idle', frames:[['surprise','down','stand',12,[11,13,'#f4f4f4']],
            ['focus','out','stand',8,[10,13,'#f4f4f4']],['happy','out','kick',8,[12,12,'#f4f4f4']],
            ['happy','up','stand',8,[14,11,'#f4f4f4']],['happy','up','stand',8,[16,10,'#f4f4f4']],
            ['happy','up','stand',12]]},
  bball:   {next:'idle', frames:[['focus','out','stand',8,[7,12,'#e08a3c']],
            ['focus','down','stand',7,[7,8,'#e08a3c']],['happy','up','tuck',7,[7,4,'#e08a3c']],
            ['focus','down','stand',7,[7,8,'#e08a3c']],['focus','out','stand',8,[7,12,'#e08a3c']],
            ['focus','down','stand',7,[7,8,'#e08a3c']],['happy','up','stand',10]]},
};
function compose(f, a, l){
  const rows = BODY.slice();
  [LEGS[l], ARMS[a], FACES[f]].forEach(ov => { if (!ov) return;
    for (const k in ov){ const r = +k, s = ov[k], arr = rows[r].split('');
      for (let x = 0; x < s.length; x++) if (s[x] !== '.') arr[x] = s[x];
      rows[r] = arr.join(''); } });
  return rows;
}
function spriteSvg(rows, ball){
  let cells = '';
  for (let y = 0; y < rows.length; y++){ const row = rows[y];
    for (let x = 0; x < 16; x++){ const ch = row[x];
      if (ch === 'A'){ cells += `<rect class="m-tip" x="${x}" y="${y}" width="1" height="1"/>`; continue; }
      if (ch === '.' || !COL[ch]) continue;
      cells += `<rect x="${x}" y="${y}" width="1" height="1" fill="${COL[ch]}"/>`; } }
  if (ball) cells += `<rect x="${ball[0]}" y="${ball[1]}" width="2" height="2" fill="${ball[2]}"/>`;
  return `<svg viewBox="0 0 16 16" shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">${cells}</svg>`;
}
let mascotState = 'idle', mascotWorkingHint = false, blinkTimer = null, prevGoals = null;
let interactiveOn = true, bobPhase = 0, lastFinishedDir = null, diffShown = true;
const finishedSeen = new Set();
// physics + animation + "brain" state for play mode
const play = {on:false, raf:0, t:0, x:0, y:0, vx:0, vy:0, sx:1, sy:1, grounded:false,
  targetKey:'', pendingReact:false, tilt:0, droop:0,
  anim:null, ai:0, af:0, animLoop:false, animNext:'idle', acting:false, walkT:0};

let lastSig = '';
function renderPose(f, a, l, ball){
  const sig = f + a + l + (ball ? ball.join(',') : '');
  if (sig === lastSig) return; lastSig = sig;     // skip identical frames (cheap)
  $('mascotArt').innerHTML = spriteSvg(compose(f, a, l), ball);
}
function setMascotArt(face){                       // static pose for dock / home mode
  renderPose(FACES[face] ? face : 'idle', face === 'happy' ? 'up' : 'down', 'stand', null);
}
function pick(a){ return a[Math.floor(Math.random()*a.length)]; }
// frame-based animation player (play mode)
function playAnim(name){
  const A = ANIM[name]; if (!A) return;
  play.anim = A.frames; play.ai = 0; play.af = A.frames[0][3];
  play.animLoop = !!A.loop; play.animNext = A.next || 'idle'; play.acting = !A.loop;
  const fr = A.frames[0]; renderPose(fr[0], fr[1], fr[2], fr[4] || null);
}
function stepAnim(){
  if (!play.anim){ playAnim('idle'); return; }
  if (--play.af > 0) return;                        // hold current frame
  play.ai++;
  if (play.ai >= play.anim.length){
    if (play.animLoop) play.ai = 0;
    else { play.acting = false; playAnim(play.animNext); return; }
  }
  const fr = play.anim[play.ai]; play.af = fr[3]; renderPose(fr[0], fr[1], fr[2], fr[4] || null);
}
function setMascotState(st){
  if (play.on) return;                 // physics owns the body in play mode
  if (st === mascotState) return;
  mascotState = st;
  const m = $('mascot');
  m.classList.remove('idle','working','happy','sleep');
  document.documentElement.style.setProperty('--mascot-tip',
    st === 'working' ? 'var(--green)' : st === 'happy' ? 'var(--pink)' : 'var(--accent)');
  if (st === 'happy'){
    m.classList.add('happy'); setMascotArt('happy');
    setTimeout(() => { if (mascotState === 'happy') setMascotState(mascotWorkingHint ? 'working' : 'idle'); }, 3200);
  } else if (st === 'working'){
    m.classList.add('working'); setMascotArt('idle');
  } else if (st === 'sleep'){
    m.classList.add('sleep'); setMascotArt('sleep');
  } else {
    m.classList.add('idle'); setMascotArt('idle');
  }
}
function setMascotFromStats(){
  if (play.on) return;                            // physics owns the body in play mode
  if (mascotState === 'happy') return;            // let a celebration finish
  if (mascotWorkingHint) return setMascotState('working');
  if (lastStats && lastStats.sessions === 0) return setMascotState('sleep');
  setMascotState('idle');
}
// idle blink loop
function scheduleBlink(){
  clearTimeout(blinkTimer);
  blinkTimer = setTimeout(() => {
    if (mascotState === 'idle' && !document.hidden){
      setMascotArt('blink');
      setTimeout(() => { if (mascotState === 'idle') setMascotArt('idle'); }, 150);
    }
    scheduleBlink();
  }, 2600 + Math.random()*3400);
}
function pokeMascot(){
  if (play.on){ playAnim(pick(['cheer','floss','dance','joy'])); return; }   // boop → goofs off
  const m = $('mascot');
  m.classList.remove('poke'); void m.offsetWidth; m.classList.add('poke');
  setMascotArt('happy');
  setTimeout(() => { if (!play.on) setMascotArt(mascotState === 'sleep' ? 'sleep' : 'idle'); }, 700);
}
$('mascot').onclick = pokeMascot;
$('mascot').onkeydown = e => { if (e.key === 'Enter' || e.key === ' '){ e.preventDefault(); pokeMascot(); } };

/* ---------- Looper's pixel physics + brain ----------
   Looper is a little critic that roams the transcript on his own: he wanders
   up and down the cards, picks one to "inspect", reads the live code, and
   reacts to what he finds — happy on a Pass, sad on a Fail, head-tilt-confused
   on errors. The brain (looperThink) picks intents on a randomized timer; the
   physics (physicsStep) carries him there with gravity + squash-and-stretch. */
const MS = 44, GRAV = 0.7;
let brainTimer = 0, seenKeys = new Set();

// every card/activity-block currently on screen, as perchable platforms
function platforms(){
  const c = $('chat').getBoundingClientRect();
  const out = [];
  $('chat').querySelectorAll('.rec, .actgroup').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.bottom > c.top + 6 && r.top < c.bottom - 6 && r.height > 14)
      out.push({el, key: el.dataset.k || '', r});
  });
  return out;
}
function platByKey(k){
  if (!k) return null;
  let el; try{ el = $('chat').querySelector(`[data-k="${CSS.escape(k)}"]`); }catch(e){ el = null; }
  if (!el) return null;
  const c = $('chat').getBoundingClientRect();
  const r = el.getBoundingClientRect();
  if (r.bottom < c.top + 6 || r.top > c.bottom - 6) return null;   // scrolled off
  return {el, key: k, r};
}
function perchOf(p){
  // sit on the card's top-LEFT corner, tucked into the gutter looking at it —
  // beside your work, not floating over the text
  const c = $('chat').getBoundingClientRect();
  let tx = p.r.left - MS * 0.34;
  let ty = p.r.top - MS + 7;                                       // feet on the top edge
  tx = Math.max(c.left - MS * 0.25, Math.min(tx, c.right - MS));
  ty = Math.max(c.top + 2, Math.min(ty, c.bottom - MS - 2));
  return {tx, ty};
}

/* ----- reactions: read a card's verdict/flags and act it out (no words) ----- */
function moodOf(el){
  if (el.querySelector('.verdict.ok')) return 'happy';
  if (el.querySelector('.verdict.bad')) return 'sad';
  if (el.querySelector('.errblock, .flag.bad, .flag.warn')) return 'confused';
  return 'read';                                                   // plain card / live code
}
function doReact(el){
  const mood = moodOf(el);
  if (mood === 'happy') playAnim(pick(['cheer','dance','floss','joy']));   // never the same yay twice
  else if (mood === 'sad'){ play.droop = 1; playAnim(pick(['slump','facepalm'])); }
  else if (mood === 'confused'){ play.tilt = 1; playAnim(pick(['scratch','think'])); }
  else playAnim('think');                                                  // reading / inspecting
}

/* ----- the brain: pick where to go and what to do next ----- */
function looperThink(){
  if (!play.on) return;
  if (play.acting){ scheduleThink(1200); return; }        // let a routine finish first
  const ps = platforms();
  if (!ps.length){ scheduleThink(2500); return; }
  const keys = ps.map(p => p.key);
  const fresh = keys.filter(k => k && !seenKeys.has(k));
  seenKeys = new Set(keys);
  const cur = ps.findIndex(p => p.key === play.targetKey);

  // mostly he rests and watches; ambles over now and then; perks up for new
  // cards; and every so often just goofs off where he's standing
  let key = play.targetKey, move = false;
  if (fresh.length && Math.random() < 0.7){               // new card landed — go look
    key = fresh[fresh.length-1]; move = true;
  } else {
    const roll = Math.random();
    if (roll < 0.55){                                      // rest — sometimes amuse himself
      if (Math.random() < 0.32) playAnim(pick(['soccer','bball','stretch','think','dance','floss']));
    }
    else if (roll < 0.74 && cur > 0){ key = ps[cur-1].key; move = true; }                 // up one
    else if (roll < 0.92 && cur >= 0 && cur < ps.length-1){ key = ps[cur+1].key; move = true; } // down one
    else { key = ps[Math.floor(Math.random()*ps.length)].key; move = true; }              // rarely, elsewhere
  }
  if (move){ play.targetKey = key; play.pendingReact = true; }
  scheduleThink(4000 + Math.random()*5000);               // calm: a decision every 4–9s
}
function scheduleThink(ms){ clearTimeout(brainTimer); brainTimer = setTimeout(looperThink, ms); }

/* ----- the body: carry him toward the brain's target ----- */
function physicsStep(){
  if (!play.on) return;
  play.t++;
  let tgt = platByKey(play.targetKey);
  if (!tgt){ const ps = platforms(); tgt = ps[ps.length-1]; if (tgt) play.targetKey = tgt.key; }
  if (!tgt){ play.raf = requestAnimationFrame(physicsStep); return; }
  const perch = perchOf(tgt);

  if (play.grounded){
    const dx = perch.tx - play.x, dy = perch.ty - play.y;
    if (dy > 14){ play.grounded = false; }                         // card below → calmly fall to it
    else if (dy < -26){                                            // card above → a gentle hop up
      play.grounded = false; play.vy = -(5 + Math.min(5, Math.abs(dy)*0.045));
      play.vx = Math.max(-3.5, Math.min(3.5, dx*0.05));
    } else {                                                       // close → walk/glide smoothly
      play.x += dx*0.12; play.y += dy*0.12;
      if (Math.abs(dx) < 1.2 && Math.abs(dy) < 1.2 && play.pendingReact){ play.pendingReact = false; doReact(tgt.el); }
    }
  }
  if (!play.grounded){
    play.vy += GRAV; play.y += play.vy; play.x += play.vx; play.vx *= 0.99;
    if (play.vy < 0){ play.sx = 0.93; play.sy = 1.09; }            // slight stretch rising
    if (play.y >= perch.ty && play.vy >= 0){                       // land softly
      play.y = perch.ty; play.vy = 0; play.vx = 0; play.grounded = true;
      play.sx = 1.13; play.sy = 0.87;                              // gentle squash
      if (play.pendingReact){ play.pendingReact = false; doReact(tgt.el); }
    }
  }

  // ----- animate: locomotion while travelling, otherwise the current routine -----
  const dxn = perch.tx - play.x, dyn = perch.ty - play.y;
  const moving = !play.grounded || Math.abs(dxn) > 2.5 || Math.abs(dyn) > 2.5;
  if (moving){
    play.anim = null; play.acting = false;                         // travel overrides routines
    if (!play.grounded) renderPose(play.vy < 0 ? 'focus' : 'surprise', play.vy < 0 ? 'up' : 'out', 'tuck', null);
    else { play.walkT++; const wf = (play.walkT >> 2) & 1; renderPose('focus', wf?'swingA':'swingB', wf?'walkA':'walkB', null); }
  } else {
    stepAnim();
  }

  // ----- ease squash/tilt/droop + compose the transform -----
  play.sx += (1-play.sx)*0.18; play.sy += (1-play.sy)*0.18;
  play.tilt += (0-play.tilt)*0.02; play.droop += (0-play.droop)*0.02;
  let bob = 0, rot = 0;
  if (play.grounded && !moving){
    const sad = play.droop > 0.2;
    bobPhase += sad ? 0.03 : 0.045;
    bob = Math.sin(bobPhase) * (sad ? 0.6 : 1.0) + play.droop * 4;        // breathing; sadness sinks
  }
  rot += Math.sin(play.t * 0.35) * 6 * play.tilt;                         // confused head-tilt
  $('mascot').style.transform =
    `translate(${play.x.toFixed(1)}px,${(play.y+bob).toFixed(1)}px) rotate(${rot.toFixed(2)}deg) scale(${play.sx.toFixed(3)},${play.sy.toFixed(3)})`;
  play.raf = requestAnimationFrame(physicsStep);
}

function enterPlay(){
  if (play.on) return;
  const ps = platforms(); if (!ps.length) return;
  const start = ps[ps.length-1], perch = perchOf(start);
  play.on = true; play.t = 0; bobPhase = 0;
  play.targetKey = start.key; play.pendingReact = true;
  play.tilt = 0; play.droop = 0;
  play.x = perch.tx; play.y = perch.ty - 120; play.vx = 0; play.vy = 0; play.grounded = false;
  play.anim = null; play.acting = false; play.walkT = 0; lastSig = '';
  const m = $('mascot'); m.classList.add('play'); m.classList.remove('idle','working','happy','sleep');
  playAnim('idle');
  seenKeys = new Set(ps.map(p => p.key));
  cancelAnimationFrame(play.raf); play.raf = requestAnimationFrame(physicsStep);
  scheduleThink(2500);
}
function leavePlay(){
  if (!play.on) return;
  play.on = false; cancelAnimationFrame(play.raf); clearTimeout(brainTimer);
  const m = $('mascot'); m.classList.remove('play'); m.style.transform = '';
  mascotState = '';                                              // force a fresh dock state
  setMascotFromStats();
}
function updatePlayMode(){
  const want = interactiveOn && document.body.classList.contains('run') && platforms().length > 0;
  if (want) enterPlay(); else leavePlay();
}
$('playBtn').onclick = () => {
  interactiveOn = !interactiveOn;
  try{ localStorage.setItem('9xf-looper', interactiveOn ? 'on' : 'off'); }catch(e){}
  $('playBtn').classList.toggle('on', interactiveOn);
  updatePlayMode();
};
function initInteractive(){
  let v = null; try{ v = localStorage.getItem('9xf-looper'); }catch(e){}
  interactiveOn = v !== 'off';                                   // default on
  $('playBtn').classList.toggle('on', interactiveOn);
}

/* ---------- diff register: collapse for a clean, single-column read ---------- */
function setDiff(show){
  diffShown = show;
  document.body.classList.toggle('nodiff', !show);
  $('diffBtn').classList.toggle('on', show);
  try{ localStorage.setItem('9xf-diff', show ? 'on' : 'off'); }catch(e){}
}
function toggleDiff(){ setDiff(document.body.classList.contains('nodiff')); }
$('diffBtn').onclick = toggleDiff;
function initDiff(){
  let v = null; try{ v = localStorage.getItem('9xf-diff'); }catch(e){}
  setDiff(v !== 'off');                                          // default shown
}
// celebrate when the shipped-goal count ticks up (on the home screen)
function checkCelebrate(goals){
  if (prevGoals !== null && goals > prevGoals) setMascotState('happy');
  prevGoals = goals;
}

/* ---------- pulse strip: the run's life as a seismograph ---------- */
function pulseSvg(entries, running){
  const iters = entries.filter(e => e.event === 'iteration').slice(-140);
  const step = 8, w = Math.max(600, iters.length*step + 26), h = 30, base = 19;
  const parts = [`<line class="pl-base" x1="0" y1="${base}" x2="${w}" y2="${base}"/>`];
  iters.forEach((e, i) => {
    const x = 8 + i*step;
    parts.push(e.ok
      ? `<line class="pl-pass" x1="${x}" y1="${base}" x2="${x}" y2="5" stroke-width="2"><title>iter ${e.iteration}: validated</title></line>`
      : `<line class="pl-fail" x1="${x}" y1="${base}" x2="${x}" y2="${h-2}" stroke-width="2"><title>iter ${e.iteration}: failed</title></line>`);
  });
  if (running) parts.push(`<rect class="cursor pl-cur" x="${8 + iters.length*step}" y="8" width="5" height="11"/>`);
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
function toggleAct(key){
  if (openActs.has(key)) openActs.delete(key); else openActs.add(key);
  renderTranscript(lastEntries, false);
}
/* a run of consecutive process steps, folded into one quiet block */
function activityGroupHtml(group){
  const key = 'act' + (group[0].iteration || 0);
  const open = openActs.has(key);
  const path = [...new Set(group.map(g => g.mode).filter(Boolean))].slice(0, 7);
  const last = group[group.length - 1];
  const rows = group.map(g =>
    `<div class="actrow"><span class="k">${esc(g.mode||'')}</span><span>${esc(g.summary)}</span></div>`).join('');
  const n = group.length;
  return `<div class="actgroup ${open?'open':''}" data-k="${key}">
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
    const gen = e.model_tokens > 0;
    const badge = gen ? `${e.model_tokens} tok${e.model_tps?` · ${e.model_tps} tok/s`:''}` : 'Running';
    return `<article class="rec open selected" data-k="live">
      <div class="rechead" style="cursor:default">
        <span class="chev" style="visibility:hidden">▶</span>
        <span class="recno">${pad3(e.iteration)}</span>
        <span class="recmode">${esc(e.mode)}</span>
        <span class="rectitle">${esc(e.subtask)}</span>
        <span class="flag warn">live</span>
        <span class="verdict ok"><span class="cursor">▮</span> ${esc(badge)}</span>
      </div>
      <div class="recbody"><div class="rbi">
        <div class="recline execl"><span class="lbl">${gen?'Gen':'Exec'}</span><span class="txt">${esc(e.summary)}</span></div>
        ${gen&&e.model_preview?`<div class="streampreview">${esc(e.model_preview)}<span class="cursor">▮</span></div>`:''}
        <div class="recmeta"><span>not committed yet</span></div>
      </div></div>
    </article>`;
  }
  if (e.event === 'iteration'){
    const open = openIters.has(e.iteration);
    const sel = pinnedCommit && e.commit === pinnedCommit ? 'selected' : '';
    const title = esc(e.subtask || '(no task)');
    return `<article class="rec ${open?'open':''} ${sel}" data-k="i${e.iteration}">
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
        ${e.warnings&&e.warnings.length?`<div class="errblock" style="color:var(--accent2);background:var(--accent-soft)">${e.warnings.map(x=>esc(x)).join('<br>')}</div>`:''}
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
    if (entries[i].event === 'activity'){       // fold a consecutive run of steps
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
  $('topPill').textContent = r.finished ? '◉ finished' : r.status;
  $('topPill').className = 'val statusword ' + status;
  const running = r.status === 'running';
  $('stopBtn').style.display = running && !r.stop_present ? '' : 'none';
  $('resumeBtn').style.display = (!running && !r.finished) ? '' : 'none';
  $('copyBtn').style.display = current ? '' : 'none';
  $('pulsewrap').style.display = r.entries.some(e => e.event === 'iteration') ? '' : 'none';
  $('pulse').innerHTML = pulseSvg(r.entries, running);

  // mascot mirrors the live run; in play mode the physics engine owns the body
  mascotWorkingHint = running;
  const freshFinish = r.finished && !finishedSeen.has(current);
  if (r.finished) finishedSeen.add(current);
  if (play.on){
    document.documentElement.style.setProperty('--mascot-tip', running ? 'var(--green)' : 'var(--accent)');
    if (freshFinish) playAnim('cheer');
  } else if (r.finished){ setMascotState('happy'); } else { setMascotFromStats(); }

  const sb = $('statusbar');
  if (running){
    sb.style.display = 'flex';
    const gen = r.live_tokens > 0 ? ` — generating ${r.live_tokens} tok${r.live_tps?` (${r.live_tps} tok/s)`:''}` : '';
    sb.innerHTML = `<span class="cursor">▮</span><span><b>${esc(r.mode||'…')}</b> — iter ${r.iteration}/${r.cap}${r.live_subtask?` — ${esc(r.live_subtask)}`:''}${gen}${r.stop_present?' — stopping at boundary':''}</span>`;
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
  updatePlayMode();                 // start/refresh Looper once cards exist
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
  const d = $('diff');
  d.innerHTML = r.error ? `<span class="del">${esc(r.error)}</span>` : colorize(r.diff);
  d.classList.remove('swap'); void d.offsetWidth; d.classList.add('swap');  // retrigger fade
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
let lastModelPayload = null;
let onboard = null;
function providerModeFor(model){ return String(model||'').startsWith('ollama/') ? 'ollama' : 'api'; }
function syncHomeMascots(){
  $('homeMascotArt').innerHTML = spriteSvg(compose('happy', 'up', 'stand'));
  $('onboardMascotArt').innerHTML = spriteSvg(compose('happy', 'up', 'stand'));
}
function setOnboardMascot(face, bubble){
  $('onboardMascotArt').innerHTML = spriteSvg(compose(face, face === 'focus' ? 'chin' : 'up', 'stand'));
  $('onboardBubble').textContent = bubble;
}
function applyComposeMode(){
  const existing = composeMode === 'existing';
  $('composeTitle').textContent = existing ? 'Open existing project' : 'New project';
  $('composeHint').textContent = existing
    ? 'Pick an existing Loopy project folder. If it already has 9xf.config.json, Loopy will resume it.'
    : 'A new or empty folder, or an existing Loopy project to continue.';
  $('goalField').style.display = existing ? 'none' : '';
  $('startBtn').textContent = existing ? 'Open' : 'Start';
}
function populateModelSelects(m){
  if (!m) return;
  lastModelPayload = m;
  const recommended = new Set(m.recommended || []);
  const optHtml = (m.models || []).map(x => {
    const label = recommended.has(x) ? `${x} · recommended` : x;
    return `<option value="${esc(x)}">${esc(label)}</option>`;
  }).join('');
  $('fModel').innerHTML = optHtml;
  $('sLocalModel').innerHTML = optHtml;
  $('sApiModel').innerHTML = (m.api_models || []).map(x => `<option value="${esc(x)}">${esc(x)}</option>`).join('');
  if (appSettings){
    $('fModel').value = appSettings.preferred_mode === 'api' ? appSettings.api_model : appSettings.preferred_model;
    $('sLocalModel').value = appSettings.preferred_model;
    $('sApiModel').value = appSettings.api_model;
  }
}
async function loadModels(){
  try{
    const m = await (await fetch('/api/models')).json();
    populateModelSelects(m);
  }catch(e){}
}
async function loadAppState(){
  try{
    appState = await (await fetch('/api/onboarding')).json();
    appSettings = appState.settings;
  }catch(e){ return; }
  $('aboutVersion').textContent = `Version ${appState.version}`;
  settingsMode = appSettings.preferred_mode || 'ollama';
  if (!$('fDir').value && appSettings.last_dir) $('fDir').value = appSettings.last_dir;
  syncHomeMascots();
  if (appState.needs_onboarding) openOnboarding();
}
function launchPrimaryFlow(){
  if (appState && appState.needs_onboarding) openOnboarding();
  else openNew();
}
function openExistingProject(){ openNew(true); }
function openNew(existing=false){
  composeMode = existing ? 'existing' : 'new';
  selectedDirIsRun = false;
  $('overlay').classList.add('show');
  $('fErr').textContent = '';
  if (!existing) $('fGoal').focus();
  if (appSettings && appSettings.last_dir) $('fDir').value = appSettings.last_dir;
  applyComposeMode();
  loadModels();
}
function closeNew(){ $('overlay').classList.remove('show'); $('browser').style.display='none'; }
$('newBtn').onclick = () => openNew();
const typing = () => /^(INPUT|TEXTAREA|SELECT)$/.test((document.activeElement||{}).tagName||'');
const modalOpen = () => $('overlay').classList.contains('show') || $('onboardOverlay').classList.contains('show')
  || $('settingsOverlay').classList.contains('show') || $('aboutOverlay').classList.contains('show');
document.addEventListener('keydown', e => {
  if (e.key === 'Escape'){
    closeNew(); closeOnboarding(); closeSettings(); closeAbout(); $('copyOverlay').classList.remove('show'); return;
  }
  if ((e.metaKey || e.ctrlKey) && (e.key === 'b' || e.key === 'B')){  // toggle sidebar
    e.preventDefault(); $('side').classList.toggle('collapsed'); return;
  }
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && modalOpen()){  // submit new session
    e.preventDefault(); startSession(); return;
  }
  if (e.key === 'n' && !typing() && !modalOpen() && !e.metaKey && !e.ctrlKey){  // new session
    e.preventDefault(); openNew();
  }
});
function setSettingsMode(m){
  settingsMode = m;
  $('sLocalBtn').className = m === 'ollama' ? 'on' : '';
  $('sApiBtn').className = m === 'api' ? 'on' : '';
}
function openSettings(){
  $('settingsOverlay').classList.add('show');
  $('settingsErr').textContent = '';
  loadModels().then(() => {
    if (!appSettings) return;
    setSettingsMode(appSettings.preferred_mode || 'ollama');
    $('sOllamaEndpoint').value = appSettings.ollama_endpoint || 'http://localhost:11434';
    $('sApiKey').value = '';
    $('settingsSavedHint').textContent = appSettings.api_key_present
      ? 'An API key is already stored locally on this Mac. Leave the field blank to keep it.'
      : 'No API key saved yet. Add one only if you want to use hosted models.';
  });
}
function closeSettings(){ $('settingsOverlay').classList.remove('show'); }
function openAbout(){ $('aboutOverlay').classList.add('show'); }
function closeAbout(){ $('aboutOverlay').classList.remove('show'); }
async function saveSettingsForm(){
  const payload = {
    preferred_mode: settingsMode,
    preferred_model: $('sLocalModel').value || (appSettings && appSettings.preferred_model),
    api_model: $('sApiModel').value || (appSettings && appSettings.api_model),
    ollama_endpoint: $('sOllamaEndpoint').value.trim(),
    onboarding_complete: true,
  };
  const apiKey = $('sApiKey').value.trim();
  if (settingsMode === 'api' && apiKey){
    const vr = await (await fetch('/api/validate/provider', {method:'POST', body: JSON.stringify({
      model: payload.api_model, api_key: apiKey,
    })})).json();
    if (vr.error || !vr.ok){ $('settingsErr').textContent = vr.error || 'Could not save that API setup.'; return; }
    payload.api_key = apiKey;
  }
  if (settingsMode === 'ollama'){
    const vr = await (await fetch('/api/validate/ollama', {method:'POST', body: JSON.stringify({
      endpoint: payload.ollama_endpoint,
    })})).json();
    if (vr.error || !vr.ok){ $('settingsErr').textContent = vr.error || 'Loopy could not reach Ollama there.'; return; }
  }
  const r = await (await fetch('/api/settings', {method:'POST', body: JSON.stringify(payload)})).json();
  if (r.error){ $('settingsErr').textContent = r.error; return; }
  appSettings = r.settings;
  appState = {...appState, needs_onboarding:false, settings:r.settings};
  closeSettings();
  tickStats();
}
function openOnboarding(){
  onboard = {
    step:'welcome',
    mode: (appSettings && appSettings.preferred_mode) || 'ollama',
    ollamaEndpoint: (appSettings && appSettings.ollama_endpoint) || 'http://localhost:11434',
    ollamaModels: [],
    ollamaModel: (appSettings && appSettings.preferred_model) || '',
    apiModel: (appSettings && appSettings.api_model) || 'mistral/mistral-small-2603',
    apiKey: '',
    error: '',
    note: '',
  };
  $('onboardOverlay').classList.add('show');
  renderOnboarding();
}
function closeOnboarding(){ $('onboardOverlay').classList.remove('show'); }
function setOnboardStep(step, mode){
  if (mode) onboard.mode = mode;
  onboard.step = step;
  onboard.error = '';
  renderOnboarding();
}
function renderOnboarding(){
  if (!onboard) return;
  const body = $('onboardBody');
  if (onboard.step === 'welcome'){
    setOnboardMascot('happy', 'No sign-up maze. Just pick how you want Loopy to talk to models.');
    body.innerHTML = `
      <div class="onKicker">Welcome</div>
      <div class="onTitle">Meet Loopy.</div>
      <div class="onText">This app stays local-first: your runs stay on disk, there’s no email collection, and your API keys never leave this Mac unless you choose a hosted provider.</div>
      <div class="choiceGrid">
        <div class="choice ${onboard.mode==='ollama'?'active':''}" onclick="setOnboardStep('ollama','ollama')"><b>Use a local model</b><span>Connect to Ollama and pick an installed model.</span></div>
        <div class="choice ${onboard.mode==='api'?'active':''}" onclick="setOnboardStep('api','api')"><b>Bring your own API key</b><span>Save a hosted-model key locally and use it for new projects.</span></div>
      </div>
      <div class="onActions"><span></span><button class="primary" onclick="setOnboardStep('${onboard.mode}')">Continue</button></div>`;
    return;
  }
  if (onboard.step === 'ollama'){
    setOnboardMascot('focus', onboard.ollamaModels.length
      ? 'Nice, I found Ollama. Pick the local model you want as your default.'
      : 'I’m checking whether Ollama is awake on this Mac.');
    body.innerHTML = `
      <div class="onKicker">Local setup</div>
      <div class="onTitle">Use Ollama on your machine</div>
      <div class="onText">Loopy will call the Ollama server directly. If it is not running yet, start Ollama first and then ask me to check again.</div>
      <div class="field"><span class="lbl">Ollama endpoint</span><input id="onOllamaEndpoint" value="${esc(onboard.ollamaEndpoint)}"></div>
      ${onboard.ollamaModels.length ? `<div class="field"><span class="lbl">Default model</span><select id="onOllamaModel">${onboard.ollamaModels.map(m => `<option value="${esc(m)}" ${m===onboard.ollamaModel?'selected':''}>${esc(m)}</option>`).join('')}</select></div>` : ''}
      <div class="miniNote">${onboard.note || 'Install a model with `ollama pull gpt-oss:20b` or another coder model if the list is empty.'}</div>
      <div class="formerr" role="alert">${esc(onboard.error || '')}</div>
      <div class="onActions">
        <button onclick="setOnboardStep('welcome')">Back</button>
        <span style="display:flex;gap:10px">
          <button onclick="checkOnboardOllama()">Check Ollama</button>
          <button class="primary" onclick="finishOllamaOnboarding()" ${onboard.ollamaModels.length?'':'disabled'}>Save and continue</button>
        </span>
      </div>`;
    return;
  }
  setOnboardMascot('content', 'Hosted model path: save the key locally here, and Loopy will use it only when you start a project.');
  body.innerHTML = `
    <div class="onKicker">API setup</div>
    <div class="onTitle">Bring your own API key</div>
    <div class="onText">Choose a hosted model, paste the key once, and Loopy will keep it locally on this Mac.</div>
    <div class="field"><span class="lbl">API model</span><select id="onApiModel">${((lastModelPayload && lastModelPayload.api_models) || ['mistral/mistral-small-2603']).map(m => `<option value="${esc(m)}" ${m===onboard.apiModel?'selected':''}>${esc(m)}</option>`).join('')}</select></div>
    <div class="field"><span class="lbl">API key</span><input id="onApiKey" type="password" placeholder="stored locally on this Mac"></div>
    <div class="miniNote">No account is created here. Loopy only stores this key locally so it can start runs for you later.</div>
    <div class="formerr" role="alert">${esc(onboard.error || '')}</div>
    <div class="onActions">
      <button onclick="setOnboardStep('welcome')">Back</button>
      <button class="primary" onclick="finishApiOnboarding()">Save and continue</button>
    </div>`;
}
async function checkOnboardOllama(){
  onboard.ollamaEndpoint = $('onOllamaEndpoint').value.trim();
  const r = await (await fetch('/api/validate/ollama', {method:'POST', body: JSON.stringify({
    endpoint: onboard.ollamaEndpoint,
  })})).json();
  onboard.error = r.error || '';
  onboard.note = r.ok ? 'Loopy found local models and can use this endpoint.' : '';
  onboard.ollamaModels = r.models || [];
  onboard.ollamaModel = onboard.ollamaModels[0] || onboard.ollamaModel;
  renderOnboarding();
}
async function finishOllamaOnboarding(){
  if ($('onOllamaModel')) onboard.ollamaModel = $('onOllamaModel').value;
  const r = await (await fetch('/api/settings', {method:'POST', body: JSON.stringify({
    preferred_mode:'ollama',
    preferred_model:onboard.ollamaModel,
    ollama_endpoint:onboard.ollamaEndpoint,
    onboarding_complete:true,
  })})).json();
  if (r.error){ onboard.error = r.error; renderOnboarding(); return; }
  appSettings = r.settings; appState = {...appState, needs_onboarding:false, settings:r.settings};
  closeOnboarding(); openNew();
}
async function finishApiOnboarding(){
  onboard.apiModel = $('onApiModel').value;
  onboard.apiKey = $('onApiKey').value.trim();
  const vr = await (await fetch('/api/validate/provider', {method:'POST', body: JSON.stringify({
    model:onboard.apiModel, api_key:onboard.apiKey,
  })})).json();
  if (vr.error || !vr.ok){ onboard.error = vr.error || 'That API setup did not validate.'; renderOnboarding(); return; }
  const r = await (await fetch('/api/settings', {method:'POST', body: JSON.stringify({
    preferred_mode:'api',
    api_model:onboard.apiModel,
    onboarding_complete:true,
    api_key:onboard.apiKey,
  })})).json();
  if (r.error){ onboard.error = r.error; renderOnboarding(); return; }
  appSettings = r.settings; appState = {...appState, needs_onboarding:false, settings:r.settings};
  closeOnboarding(); openNew();
}
async function pickFolder(){
  if (window.ninexf && window.ninexf.pickFolder){     /* electron: native macOS dialog */
    try{ const p = await window.ninexf.pickFolder(); if (p) $('fDir').value = p; return; }
    catch(e){ /* native bridge failed — fall through to the in-app browser */ }
  }
  browseTo($('fDir').value || '');                    /* browser: server-side picker */
}
async function browseTo(path){
  let r; try{ r = await (await fetch('/api/browse?path='+encodeURIComponent(path))).json(); }catch(e){ return; }
  $('fDir').value = r.path;
  selectedDirIsRun = !!r.is_run;
  const rows = (r.parent
      ? `<div class="bi" onclick="browseTo('${esc(r.parent)}')"><span class="ic">↑</span><span class="nm">..</span></div>`
      : '') +
    (r.dirs.length
      ? r.dirs.map(d=>`<div class="bi" onclick="browseTo('${esc(d.path)}')"><span class="ic">▸</span><span class="nm">${esc(d.name)}</span>${d.is_run?'<span class="tag">Loopy project</span>':''}</div>`).join('')
      : '<div class="bi muted"><span class="ic"></span><span class="nm">no subfolders here</span></div>');
  const b = $('browser'); b.style.display = 'flex';
  b.innerHTML =
    `<div class="browpath" title="${esc(r.path)}">${esc(r.path)}${r.is_run?'  ·  existing Loopy project':''}</div>` +
    `<div class="browlist">${rows}</div>` +
    `<div class="browfoot"><span class="sel">use this folder${r.is_run?' (continue project)':''}</span>` +
    `<button class="primary" onclick="$('browser').style.display='none'">Use folder</button></div>`;
}
async function startSession(){
  const chosenModel = $('fModel').value || null;
  const payload = {
    dir: $('fDir').value.trim(), goal: $('fGoal').value.trim(), preset: mode,
    model: chosenModel,
    provider_mode: providerModeFor(chosenModel),
    endpoint: providerModeFor(chosenModel) === 'ollama' ? (appSettings && appSettings.ollama_endpoint) : null,
    iterations: $('fIters').value ? parseInt($('fIters').value) : null,
    hours: $('fHours').value ? parseFloat($('fHours').value) : null,
  };
  if (!payload.dir){ $('fErr').textContent = 'Pick a folder first'; return; }
  if (composeMode !== 'existing' && !selectedDirIsRun && !payload.goal){
    $('fErr').textContent = 'Write a goal — one sentence is enough'; return;
  }
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
$('brand').onkeydown = e => { if (e.key === 'Enter') goHome(); };

/* ---------- light / dark theme ---------- */
function applyTheme(t){
  const dark = t === 'dark';
  if (dark) document.documentElement.setAttribute('data-theme', 'dark');
  else document.documentElement.removeAttribute('data-theme');
  $('themeBtn').textContent = dark ? '☀' : '☾';   // shows what you'll switch TO
}
function initTheme(){
  let t = null;
  try{ t = localStorage.getItem('9xf-theme'); }catch(e){}
  if (t !== 'dark' && t !== 'light')
    t = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
  applyTheme(t);
}
$('themeBtn').onclick = () => {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  try{ localStorage.setItem('9xf-theme', next); }catch(e){}
  applyTheme(next);
};

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

/* ---------- boot ---------- */
initTheme();
initInteractive();
initDiff();
setMascotArt('idle');
setMascotState('idle');
syncHomeMascots();
scheduleBlink();
loadAppState();
tickStats(); tickRuns();
setInterval(tickRuns, 2500);
setInterval(tickRun, 2000);
setInterval(() => { tickStats(); if (lastStats) checkCelebrate(lastStats.goals); setMascotFromStats(); }, 4000);
</script></body></html>"""
