"""`9xf watch` — a local dashboard for observing every registered loop at once.

Pure stdlib: http.server + one embedded HTML page (no frameworks, no external
assets) that polls /api/runs every 2 seconds. Read-only — the dashboard never
touches a run, it only observes.
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ninexf import GOAL_FILENAME, STOP_FILENAME
from ninexf.config import load_config
from ninexf.looplog import read_entries
from ninexf.registry import read_state, registered_runs

STALE_GRACE_S = 120


def _last_commit(project_dir: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%h %s"],
            cwd=project_dir, capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip().splitlines()[0] if out.returncode == 0 and out.stdout else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _run_status(state: dict, delay: float, last_iter_ok: bool | None) -> str:
    if not state:
        return "never started"
    if not state.get("running"):
        if last_iter_ok is False:
            return "failed"
        return "stopped"
    ts = state.get("ts", "")
    try:
        age = time.time() - datetime.fromisoformat(ts).timestamp()
    except ValueError:
        return "stale"
    return "running" if age < delay + STALE_GRACE_S else "stale"


def collect_runs() -> list[dict]:
    runs = []
    for d in registered_runs():
        try:
            cfg = load_config(d)
            delay, cap = cfg.delay_seconds, cfg.max_iterations
            model = cfg.model
        except (FileNotFoundError, json.JSONDecodeError):
            delay, cap, model = 5, 50, "?"
        state = read_state(d)
        entries = read_entries(d)
        iters = [e for e in entries if e.get("event") == "iteration"]
        last = iters[-1] if iters else {}
        runs.append({
            "dir": str(d),
            "name": d.name,
            "goal": (d / GOAL_FILENAME).read_text().strip(),
            "model": model,
            "status": _run_status(state, delay, last.get("validation_passed")),
            "stopped_reason": state.get("stopped_reason", ""),
            "iteration": state.get("iteration", last.get("iteration", 0)),
            "cap": cap,
            "mode": state.get("mode", last.get("mode", "")),
            "subtask": state.get("subtask", last.get("subtask", "")),
            "dots": [bool(e.get("validation_passed")) for e in iters[-40:]],
            "flags": {
                "regressions": sum(1 for e in iters if e.get("regression")),
                "stuck": sum(1 for e in iters if e.get("stuck_detected")),
                "violations": sum(1 for e in entries if e.get("event") == "violation"),
            },
            "recent": [
                {
                    "iteration": e.get("iteration"),
                    "mode": e.get("mode", "build"),
                    "ok": bool(e.get("validation_passed")),
                    "subtask": e.get("subtask", ""),
                    "summary": e.get("summary", ""),
                    "errors": e.get("errors", [])[:3],
                }
                for e in iters[-15:]
            ],
            "last_commit": _last_commit(d),
            "stop_present": (d / STOP_FILENAME).exists(),
        })
    return runs


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>9xf loops</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--text:#e6edf3;--dim:#8b949e;
--green:#3fb950;--red:#f85149;--amber:#d29922;--blue:#58a6ff;--purple:#bc8cff}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--text);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:28px}
h1{font-size:18px;font-weight:600;letter-spacing:.3px;margin-bottom:4px}
h1 .x{color:var(--purple)}
#sub{color:var(--dim);font-size:12px;margin-bottom:24px}
#grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px}
.card .top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;margin-bottom:8px}
.goal{font-weight:600;font-size:14px}
.name{color:var(--dim);font-size:11px;margin-top:2px}
.pill{font-size:11px;font-weight:600;padding:2px 9px;border-radius:999px;white-space:nowrap}
.pill.running{background:rgba(63,185,80,.15);color:var(--green)}
.pill.stopped{background:rgba(139,148,158,.15);color:var(--dim)}
.pill.failed{background:rgba(248,81,73,.12);color:var(--red)}
.pill.stale{background:rgba(210,153,34,.15);color:var(--amber)}
.pill.never{background:rgba(139,148,158,.1);color:var(--dim)}
.bar{height:6px;background:var(--border);border-radius:3px;overflow:hidden;margin:10px 0 6px}
.bar i{display:block;height:100%;background:var(--blue);border-radius:3px;transition:width .5s}
.meta{display:flex;justify-content:space-between;color:var(--dim);font-size:11px}
.subtask{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--text);background:var(--bg);
border:1px solid var(--border);border-radius:6px;padding:8px 10px;margin:10px 0;word-break:break-word}
.subtask .m{color:var(--purple);font-weight:700;margin-right:6px;text-transform:uppercase;font-size:10px}
.dots{letter-spacing:2px;font-size:13px;margin:4px 0}
.dots .ok{color:var(--green)} .dots .bad{color:var(--red)}
.flags{display:flex;gap:12px;color:var(--dim);font-size:11px;margin:6px 0}
.flags b{color:var(--amber)}
.commit{color:var(--dim);font:11px ui-monospace,Menlo,monospace;margin-top:6px;word-break:break-all}
details{margin-top:10px} summary{cursor:pointer;color:var(--dim);font-size:12px;user-select:none}
.log{margin-top:8px;max-height:240px;overflow-y:auto;font:11px ui-monospace,Menlo,monospace}
.log .row{padding:5px 0;border-top:1px solid var(--border)}
.log .ok{color:var(--green)} .log .bad{color:var(--red)}
.log .mode{color:var(--purple);text-transform:uppercase;font-size:9px;margin:0 4px}
.log .err{color:var(--red);opacity:.85;padding-left:18px}
.log .sum{color:var(--dim);padding-left:18px}
.empty{color:var(--dim);padding:60px;text-align:center;grid-column:1/-1}
.stopreason{color:var(--dim);font-size:11px;font-style:italic;margin-top:4px}
</style></head><body>
<h1>9<span class="x">xf</span> loops</h1>
<div id="sub">autonomous loop dashboard — refreshes every 2s</div>
<div id="grid"><div class="empty">loading…</div></div>
<script>
const esc = s => (s||'').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function tick(){
  let runs;
  try { runs = await (await fetch('/api/runs')).json(); }
  catch(e){ return; }
  const grid = document.getElementById('grid');
  if(!runs.length){ grid.innerHTML = '<div class="empty">no registered runs yet — create one with <b>9xf init</b></div>'; return; }
  grid.innerHTML = runs.map(r => {
    const pct = r.cap ? Math.min(100, Math.round(100*r.iteration/r.cap)) : 0;
    const pillClass = r.status === 'never started' ? 'never' : r.status;
    const dots = r.dots.map(d => d ? '<span class="ok">●</span>' : '<span class="bad">●</span>').join('');
    const rows = r.recent.slice().reverse().map(e => `
      <div class="row">
        <span class="${e.ok ? 'ok' : 'bad'}">${e.ok ? '✓' : '✗'}</span>
        <span class="mode">${esc(e.mode)}</span>#${e.iteration} ${esc(e.subtask)}
        ${e.summary ? `<div class="sum">${esc(e.summary)}</div>` : ''}
        ${e.errors.map(x => `<div class="err">${esc(String(x)).slice(0,200)}</div>`).join('')}
      </div>`).join('');
    return `<div class="card">
      <div class="top">
        <div><div class="goal">${esc(r.goal)}</div><div class="name">${esc(r.name)} · ${esc(r.model)}</div></div>
        <span class="pill ${pillClass}">${esc(r.status)}${r.stop_present ? ' · STOP' : ''}</span>
      </div>
      <div class="bar"><i style="width:${pct}%"></i></div>
      <div class="meta"><span>iteration ${r.iteration} / ${r.cap}</span><span>${pct}%</span></div>
      ${r.subtask ? `<div class="subtask"><span class="m">${esc(r.mode)}</span>${esc(r.subtask)}</div>` : ''}
      <div class="dots">${dots}</div>
      <div class="flags">
        <span>regressions <b>${r.flags.regressions}</b></span>
        <span>stuck <b>${r.flags.stuck}</b></span>
        <span>violations <b>${r.flags.violations}</b></span>
      </div>
      ${r.stopped_reason ? `<div class="stopreason">${esc(r.stopped_reason)}</div>` : ''}
      ${r.last_commit ? `<div class="commit">${esc(r.last_commit)}</div>` : ''}
      <details><summary>recent iterations</summary><div class="log">${rows || '<div class="row">none yet</div>'}</div></details>
    </div>`;
  }).join('');
}
tick(); setInterval(tick, 2000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/runs":
            body = json.dumps(collect_runs()).encode()
            ctype = "application/json"
        elif self.path in ("/", "/index.html"):
            body = PAGE.encode()
            ctype = "text/html; charset=utf-8"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # quiet
        pass


def serve(port: int = 9119, open_browser: bool = True):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"[9xf] dashboard at {url} (Ctrl+C to quit)")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[9xf] dashboard stopped")
