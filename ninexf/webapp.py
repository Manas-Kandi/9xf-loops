"""`9xf app` — the chat-style web app (v0.6): start a session, pick a folder,
type a goal, watch the loop think and build, with a live code-diff panel.

Pure stdlib on the Python side: http.server + one embedded dark-mode HTML page
that polls JSON endpoints. Unlike the dashboard (read-only), the app *controls*
runs: POST /api/start inits a project and spawns a detached `9xf run`
subprocess; POST /api/stop drops the STOP file.

This same server is what the Electron desktop app (app/ at the repo root)
hosts in a native window — the web UI works identically in a plain browser,
so the harness keeps zero pip dependencies.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ninexf import CONFIG_FILENAME, GOAL_FILENAME, STOP_FILENAME, __version__
from ninexf.apppage import APP_PAGE
from ninexf.config import load_config
from ninexf.dashboard import _run_status, collect_runs
from ninexf.looplog import read_entries
from ninexf.registry import read_state, registered_runs
from ninexf.tasks import load_tasks

COMMIT_RE = re.compile(r"^[0-9a-f]{6,40}$")
MAX_DIFF_CHARS = 200_000
MAX_ENTRIES = 300
MAX_BUNDLE_CHARS = 900_000
MAX_BUNDLE_FILE_CHARS = 120_000
DIAGNOSTIC_BUNDLE_FILENAME = "9xf-diagnostic-bundle.txt"

_PROCS: dict[str, subprocess.Popen] = {}  # dir -> spawned run process


# -- API: read ------------------------------------------------------------------

def _chat_entry(e: dict) -> dict:
    """Whittle a log entry down to what the chat UI renders."""
    return {
        "event": e.get("event", "iteration"),
        "iteration": e.get("iteration", 0),
        "timestamp": e.get("timestamp", ""),
        "mode": e.get("mode", "build"),
        "subtask": e.get("subtask", ""),
        "summary": e.get("summary", ""),
        "ok": bool(e.get("validation_passed")),
        "detail": e.get("validation_detail", ""),
        "errors": [str(x)[:300] for x in (e.get("errors") or [])][:5],
        "warnings": [str(x)[:200] for x in (e.get("parse_warnings") or [])][:3],
        "files": e.get("files_written", []),
        "commit": e.get("commit", ""),
        "repairs": len(e.get("repairs") or []),
        "repaired_ok": bool((e.get("repairs") or [{}])[-1].get("passed")),
        "candidates": len(e.get("candidates") or []),
        "chosen": e.get("chosen_candidate", 0),
        "critic": e.get("critic_verdict", ""),
        "stuck": e.get("stuck_signals", []),
        "regression": bool(e.get("regression")),
        "task_id": e.get("task_id", 0),
        "acceptance": e.get("acceptance_passed"),
        "overflow": bool(e.get("context_overflow")),
        "tool_runs": [{"name": t.get("name", ""), "result": str(t.get("result", ""))[:200]}
                      for t in (e.get("tool_runs") or [])][:3],
        "model_calls": len(e.get("model_calls") or []),
        "model_seconds": round(sum(float(c.get("latency_s", 0) or 0)
                                   for c in (e.get("model_calls") or [])), 1),
    }


def _elapsed_label(ts: str) -> str:
    try:
        started = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        seconds = max(0, int((datetime.now(timezone.utc) - started).total_seconds()))
    except (TypeError, ValueError):
        return ""
    if seconds < 60:
        return f"{seconds}s"
    return f"{seconds // 60}m {seconds % 60}s"


def run_detail(d: Path) -> dict:
    if not (d / GOAL_FILENAME).exists():
        return {"error": f"not a 9xf run: {d}"}
    try:
        cfg = load_config(d)
        model, cap, delay = cfg.model, cfg.max_iterations, cfg.delay_seconds
    except (FileNotFoundError, json.JSONDecodeError):
        model, cap, delay = "?", 0, 5
    entries = read_entries(d)
    iters = [e for e in entries if e.get("event") == "iteration"]
    state = read_state(d)
    rendered_entries = [_chat_entry(e) for e in entries[-MAX_ENTRIES:]]
    state_iter = int(state.get("iteration", 0) or 0)
    state_mode = state.get("mode", "")
    state_subtask = state.get("subtask", "")
    latest_logged = max((e.get("iteration", 0) for e in entries), default=-1)
    if state.get("running") and state_iter >= latest_logged and state_subtask:
        if not any(e.get("event") == "live" and e.get("iteration") == state_iter
                   for e in rendered_entries):
            elapsed = _elapsed_label(state.get("ts", ""))
            tokens = int(state.get("model_tokens", 0) or 0)
            tps = float(state.get("model_tps", 0) or 0)
            preview = str(state.get("model_preview", "") or "")
            summary = "in progress - waiting for the current model/tool call to finish"
            if state_subtask.startswith("waiting for model:"):
                if tokens > 0:
                    summary = f"generating · {tokens} tokens"
                    if tps:
                        summary += f" · {tps:g} tok/s"
                    if elapsed:
                        summary += f" · {elapsed}"
                else:
                    summary = "model call in progress"
                    if elapsed:
                        summary += f" for {elapsed}"
            rendered_entries.append({
                "event": "live",
                "iteration": state_iter,
                "timestamp": state.get("ts", ""),
                "mode": state_mode or "running",
                "subtask": state_subtask,
                "summary": summary,
                "ok": False,
                "detail": "",
                "errors": [],
                "warnings": [],
                "files": [],
                "commit": "",
                "repairs": 0,
                "repaired_ok": False,
                "candidates": 0,
                "chosen": 0,
                "critic": "",
                "stuck": [],
                "regression": False,
                "task_id": 0,
                "acceptance": None,
                "overflow": False,
                "tool_runs": [],
                "model_calls": 0,
                "model_seconds": 0,
                "model_tokens": tokens,
                "model_tps": tps,
                "model_preview": preview,
            })
    for a in (state.get("activity") or [])[-80:]:
        rendered_entries.append({
            "event": "activity",
            "iteration": int(a.get("iteration", 0) or 0),
            "timestamp": a.get("ts", ""),
            "mode": a.get("kind", "activity"),
            "subtask": "",
            "summary": a.get("message", ""),
            "ok": True,
            "detail": "",
            "errors": [],
            "warnings": [],
            "files": [],
            "commit": "",
            "repairs": 0,
            "repaired_ok": False,
            "candidates": 0,
            "chosen": 0,
            "critic": "",
            "stuck": [],
            "regression": False,
            "task_id": 0,
            "acceptance": None,
            "overflow": False,
            "tool_runs": [],
            "model_calls": 0,
            "model_seconds": 0,
        })
    # Order the whole stream top-to-bottom in time. Activities and the live
    # marker carry the iteration they belong to, so sort primarily by iteration
    # and secondarily by a per-event rank (lead-up activity → live → the commit
    # record). Startup pins to the top; finished/shutdown sink to the bottom.
    _RANK = {"startup": 0, "explore": 1, "violation": 1, "revert": 1,
             "activity": 1, "live": 2, "iteration": 3, "finished": 4, "shutdown": 4}
    def _chrono(item):
        idx, e = item
        ev = e.get("event", "iteration")
        it = int(e.get("iteration", 0) or 0)
        if ev == "startup":
            it = -1
        elif ev in ("finished", "shutdown"):
            it = 10**9
        return (it, _RANK.get(ev, 1), idx)
    rendered_entries = [e for _, e in sorted(enumerate(rendered_entries), key=_chrono)]
    tl = load_tasks(d)
    done, total = tl.counts()
    return {
        "dir": str(d),
        "name": d.name,
        "goal": (d / GOAL_FILENAME).read_text().strip(),
        "model": model,
        "cap": cap,
        "status": _run_status(state, delay, iters[-1].get("validation_passed") if iters else None),
        "stopped_reason": state.get("stopped_reason", ""),
        "iteration": state.get("iteration", iters[-1].get("iteration", 0) if iters else 0),
        "mode": state.get("mode", ""),
        "live_subtask": state.get("subtask", ""),
        "live_tokens": int(state.get("model_tokens", 0) or 0),
        "live_tps": float(state.get("model_tps", 0) or 0),
        "finished": any(e.get("event") == "finished" for e in entries),
        "stop_present": (d / STOP_FILENAME).exists(),
        "tasks": [{"num": t.num, "text": t.text, "status": t.status} for t in tl.tasks],
        "tasks_done": done,
        "tasks_total": total,
        "entries": rendered_entries[-MAX_ENTRIES:],
    }


def commit_diff(d: Path, commit: str) -> dict:
    if not COMMIT_RE.match(commit):
        return {"error": "bad commit"}
    try:
        out = subprocess.run(
            ["git", "show", commit, "--format=%h %s", "--unified=3", "--",
             "src", "tests", "tools", "TASKS.md", "ACCEPTANCE.md", "CONTRACT.md", "NOTES.md"],
            cwd=d, capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": str(e)}
    if out.returncode != 0:
        return {"error": out.stderr.strip()[:300] or "git show failed"}
    text = out.stdout
    if len(text) > MAX_DIFF_CHARS:
        text = text[:MAX_DIFF_CHARS] + "\n... (diff truncated)"
    return {"commit": commit, "diff": text}


def _read_for_bundle(path: Path, max_chars: int = MAX_BUNDLE_FILE_CHARS) -> str:
    try:
        text = path.read_text(errors="replace")
    except (OSError, UnicodeDecodeError) as e:
        return f"(unreadable: {e})\n"
    if len(text) > max_chars:
        return text[:max_chars] + f"\n... (truncated at {max_chars} chars)\n"
    return text


def _git_for_bundle(d: Path, args: list[str], max_chars: int = 80_000) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=d, capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"(git unavailable: {e})\n"
    text = (out.stdout or "") + (("\nSTDERR:\n" + out.stderr) if out.stderr else "")
    if len(text) > max_chars:
        return text[:max_chars] + f"\n... (truncated at {max_chars} chars)\n"
    return text or "(no output)\n"


def diagnostic_bundle(d: Path) -> dict:
    """A pasteable run bundle for asking another agent/person to diagnose it."""
    if not (d / GOAL_FILENAME).exists():
        return {"error": f"not a 9xf run: {d}"}
    sections: list[tuple[str, str]] = []

    def add(title: str, body: str) -> None:
        sections.append((title, body.rstrip() + "\n"))

    add("9XF DIAGNOSTIC BUNDLE", (
        f"dir: {d}\n"
        f"version: {__version__}\n"
        "note: paste this whole bundle into a chat to diagnose the run.\n"
    ))
    for rel in (
        GOAL_FILENAME, CONFIG_FILENAME, "state.json", "TASKS.md",
        "ACCEPTANCE.md", "CONTRACT.md", "NOTES.md", "loop_log.jsonl", "run.out",
    ):
        p = d / rel
        if p.exists():
            add(rel, _read_for_bundle(p))
        else:
            add(rel, "(missing)\n")

    state = read_state(d)
    activity = state.get("activity") or []
    if activity:
        lines = []
        for a in activity[-80:]:
            lines.append(
                f"{a.get('ts', '')} iter={a.get('iteration', 0)} "
                f"{a.get('kind', 'activity')}: {a.get('message', '')}"
            )
        add("live activity stream", "\n".join(lines) + "\n")

    add("git status --short", _git_for_bundle(d, ["status", "--short"]))
    add("git log --oneline --decorate -n 80",
        _git_for_bundle(d, ["log", "--oneline", "--decorate", "-n", "80"]))

    file_roots = ["src", "tests", "tools", "acceptance"]
    files = []
    for root in file_roots:
        base = d / root
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            if p.suffix in {".pyc", ".pyo"} or "__pycache__" in p.parts or p.name == ".DS_Store":
                continue
            files.append(p)
    tree = "\n".join(str(p.relative_to(d)) for p in files) or "(no generated files)"
    add("generated file tree", tree + "\n")
    for p in files:
        rel = str(p.relative_to(d))
        add(f"FILE {rel}", _read_for_bundle(p))

    text = "\n".join(f"===== {title} =====\n{body}" for title, body in sections)
    if len(text) > MAX_BUNDLE_CHARS:
        text = text[:MAX_BUNDLE_CHARS] + f"\n... (bundle truncated at {MAX_BUNDLE_CHARS} chars)\n"
    return {"text": text, "chars": len(text)}


def _exclude_diagnostic_bundle(d: Path) -> None:
    """Keep saved bundles out of the run's research git history."""
    exclude = d / ".git" / "info" / "exclude"
    if not exclude.exists():
        return
    entry = f"/{DIAGNOSTIC_BUNDLE_FILENAME}"
    try:
        text = exclude.read_text()
        if entry not in text.splitlines():
            sep = "" if text.endswith("\n") or not text else "\n"
            exclude.write_text(text + sep + entry + "\n")
    except OSError:
        return


def export_diagnostic_bundle(d: Path) -> dict:
    """Return the pasteable bundle and also save it beside the run."""
    bundle = diagnostic_bundle(d)
    text = bundle.get("text")
    if not text:
        return bundle
    path = d / DIAGNOSTIC_BUNDLE_FILENAME
    try:
        _exclude_diagnostic_bundle(d)
        path.write_text(text)
        bundle["path"] = str(path)
    except OSError as e:
        bundle["save_error"] = str(e)
    return bundle


def browse(path_str: str) -> dict:
    base = Path(path_str).expanduser() if path_str else Path.home()
    try:
        base = base.resolve()
    except OSError:
        base = Path.home()
    if not base.is_dir():
        base = Path.home()
    dirs = []
    try:
        for p in sorted(base.iterdir()):
            if p.is_dir() and not p.name.startswith("."):
                dirs.append({"name": p.name, "path": str(p),
                             "is_run": (p / CONFIG_FILENAME).exists()})
    except PermissionError:
        pass
    return {"path": str(base),
            "parent": str(base.parent) if base != base.parent else "",
            "is_run": (base / CONFIG_FILENAME).exists(),
            "dirs": dirs[:200]}


def list_models() -> dict:
    from ninexf.interactive import _ollama_models
    from ninexf.models import (
        DEFAULT_MODEL,
        GPT_OSS_20B_MODEL,
        MISTRAL_SMALL_MODEL,
        NVIDIA_GEMMA_MODEL,
        NVIDIA_KIMI_MODEL,
        NVIDIA_QWEN_NEXT_MODEL,
        NVIDIA_QWEN_MODEL,
        model_options,
        ollama_model_id,
    )
    installed = _ollama_models()
    found = [ollama_model_id(m) for m in installed]
    options = model_options(installed)
    return {
        "models": options,
        "default": found[0] if found else DEFAULT_MODEL,
        "recommended": [
            GPT_OSS_20B_MODEL,
            MISTRAL_SMALL_MODEL,
            NVIDIA_GEMMA_MODEL,
            NVIDIA_QWEN_MODEL,
            NVIDIA_QWEN_NEXT_MODEL,
            NVIDIA_KIMI_MODEL,
        ],
    }


# -- API: stats (the gamified overview) ---------------------------------------------

# Achievement ladder. Each is (key, name, blurb, glyph, predicate(stats-dict)).
# Predicates run against the running tally below — pure thresholds, no I/O.
_ACHIEVEMENTS = [
    ("first_light", "First Light", "Start your first session", "✦",
     lambda s: s["sessions"] >= 1),
    ("first_ship", "Closer", "Ship your first goal", "◉",
     lambda s: s["goals"] >= 1),
    ("centurion", "Centurion", "100 total iterations", "⬡",
     lambda s: s["iterations"] >= 100),
    ("marathon", "Marathoner", "A single run past 50 iterations", "↻",
     lambda s: s["max_run_iters"] >= 50),
    ("streak3", "Streak Keeper", "Code 3 days in a row", "▲",
     lambda s: s["longest_streak"] >= 3),
    ("streak7", "Week Warrior", "A 7-day streak", "★",
     lambda s: s["longest_streak"] >= 7),
    ("polyglot", "Polyglot", "Run 3 different models", "⬢",
     lambda s: s["distinct_models"] >= 3),
    ("nightowl", "Night Owl", "Work between midnight and 5am", "☾",
     lambda s: s["night_owl"]),
    ("fleet", "Fleet Commander", "Keep 5 sessions on record", "⛁",
     lambda s: s["sessions"] >= 5),
    ("sharp", "Sharpshooter", "80%+ pass rate over 20+ iterations", "◎",
     lambda s: s["iterations"] >= 20 and s["passed"] / max(1, s["iterations"]) >= 0.8),
]

# XP weights — what each kind of progress is worth. Tuned so a productive
# overnight run is a satisfying chunk of a level without trivializing goals.
_XP_ITER, _XP_PASS, _XP_TASK, _XP_GOAL = 4, 6, 12, 120
_LEVEL_BASE = 240  # xp for level 2; curve is quadratic (see _level_for)


def _level_for(xp: int) -> dict:
    """Quadratic level curve: cumulative xp for level L is (L-1)^2 * base."""
    level = int((xp / _LEVEL_BASE) ** 0.5) + 1
    floor_xp = (level - 1) ** 2 * _LEVEL_BASE
    next_xp = level ** 2 * _LEVEL_BASE
    span = max(1, next_xp - floor_xp)
    return {
        "level": level,
        "xp": xp,
        "into_level": xp - floor_xp,
        "level_span": span,
        "to_next": next_xp - xp,
        "pct": round(100 * (xp - floor_xp) / span),
    }


def _stat_dt(ts) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()  # local time — streaks/heatmap read in the user's day


def _streaks(active_days: set) -> tuple[int, int]:
    """(current, longest) run of consecutive active calendar days."""
    if not active_days:
        return 0, 0
    days = sorted(active_days)
    longest = run = 1
    for prev, cur in zip(days, days[1:]):
        run = run + 1 if (cur - prev).days == 1 else 1
        longest = max(longest, run)
    today = datetime.now().astimezone().date()
    current = 0
    cursor = today
    if today not in active_days and (today - timedelta(days=1)) in active_days:
        cursor = today - timedelta(days=1)  # today not started yet — yesterday still counts
    while cursor in active_days:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def collect_stats() -> dict:
    """Aggregate every registered run into the gamified overview payload.

    Everything here is derived from real run data (the loop logs, task lists,
    and configs) — no invented numbers. The client renders cards, a heatmap,
    an XP bar, and the achievement shelf from this single document.
    """
    runs = registered_runs()
    iterations = passed = failed = tasks_done = goals = 0
    max_run_iters = 0
    models: Counter = Counter()
    day_counts: Counter = Counter()   # date -> iteration count
    hour_counts: Counter = Counter()  # 0..23 -> iteration count
    active_days: set = set()

    for d in runs:
        try:
            models[load_config(d).model] += 1
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass
        entries = read_entries(d)
        if any(e.get("event") == "finished" for e in entries):
            goals += 1
        try:
            done, _ = load_tasks(d).counts()
            tasks_done += done
        except OSError:
            pass
        run_iters = 0
        for e in entries:
            if e.get("event") != "iteration":
                continue
            iterations += 1
            run_iters += 1
            if e.get("validation_passed"):
                passed += 1
            else:
                failed += 1
            dt = _stat_dt(e.get("timestamp"))
            if dt:
                day = dt.date()
                active_days.add(day)
                day_counts[day] += 1
                hour_counts[dt.hour] += 1
        max_run_iters = max(max_run_iters, run_iters)

    current_streak, longest_streak = _streaks(active_days)
    peak_hour = hour_counts.most_common(1)[0][0] if hour_counts else None
    favorite_model = models.most_common(1)[0][0] if models else "—"

    # 20-week activity heatmap, oldest→newest, padded to whole weeks so the
    # client can lay it out as 7 rows (Sun..Sat) without date math.
    today = datetime.now().astimezone().date()
    span_days = 140
    start = today - timedelta(days=span_days - 1)
    start -= timedelta(days=(start.weekday() + 1) % 7)  # back up to a Sunday
    heatmap = []
    cur = start
    while cur <= today:
        c = day_counts.get(cur, 0)
        lvl = 0 if c == 0 else 1 if c <= 2 else 2 if c <= 5 else 3 if c <= 9 else 4
        heatmap.append({"date": cur.isoformat(), "count": c, "level": lvl})
        cur += timedelta(days=1)

    tally = {
        "sessions": len(runs),
        "iterations": iterations,
        "passed": passed,
        "failed": failed,
        "tasks_done": tasks_done,
        "goals": goals,
        "max_run_iters": max_run_iters,
        "distinct_models": len(models),
        "longest_streak": longest_streak,
        "night_owl": any(h < 5 for h in hour_counts),
    }
    xp = (iterations * _XP_ITER + passed * _XP_PASS
          + tasks_done * _XP_TASK + goals * _XP_GOAL)
    achievements = [
        {"key": k, "name": n, "blurb": b, "glyph": g, "unlocked": pred(tally)}
        for (k, n, b, g, pred) in _ACHIEVEMENTS
    ]

    return {
        **tally,
        "active_days": len(active_days),
        "current_streak": current_streak,
        "pass_rate": round(100 * passed / iterations) if iterations else 0,
        "peak_hour": peak_hour,
        "favorite_model": favorite_model,
        "heatmap": heatmap,
        "progress": _level_for(xp),
        "achievements": achievements,
        "unlocked_count": sum(1 for a in achievements if a["unlocked"]),
    }


# -- API: control -----------------------------------------------------------------

def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def is_running(d: Path) -> bool:
    state = read_state(d)
    return bool(state.get("running")) and _pid_alive(state.get("pid", -1))


def _nvidia_model_for_run(d: Path) -> str:
    try:
        cfg = load_config(d)
    except Exception:
        return ""
    return cfg.model if cfg.model.startswith("nvidia/") else ""


def active_nvidia_run(except_dir: Path | None = None) -> Path | None:
    except_resolved = except_dir.resolve() if except_dir else None
    for other in registered_runs():
        try:
            other_resolved = other.resolve()
        except OSError:
            other_resolved = other
        if except_resolved is not None and other_resolved == except_resolved:
            continue
        if not is_running(other):
            continue
        if _nvidia_model_for_run(other):
            return other
    return None


def start_run(payload: dict) -> dict:
    d = Path(str(payload.get("dir", "")).strip()).expanduser()
    if not str(d) or not d.is_absolute():
        return {"error": "an absolute folder path is required"}
    goal = (payload.get("goal") or "").strip()
    if not (d / CONFIG_FILENAME).exists():
        if not goal:
            return {"error": "a goal is required for a new session"}
        from ninexf.cli import init_project
        try:
            init_project(d, goal, model=payload.get("model") or None,
                         preset=payload.get("preset") or None)
        except (FileExistsError, OSError, ValueError) as e:
            return {"error": str(e)}
    if is_running(d):
        return {"error": "this run is already going"}
    if _nvidia_model_for_run(d):
        active = active_nvidia_run(except_dir=d)
        if active is not None:
            return {"error": f"another NVIDIA-backed run is already active: {active}"}
    if (d / STOP_FILENAME).exists():
        (d / STOP_FILENAME).unlink()

    cmd = [sys.executable, "-m", "ninexf", "run", "--dir", str(d)]
    if payload.get("iterations"):
        cmd += ["--max-iterations", str(int(payload["iterations"]))]
    if payload.get("hours"):
        cmd += ["--hours", str(float(payload["hours"]))]
    if payload.get("delay") is not None:
        cmd += ["--delay", str(float(payload["delay"]))]
    log = (d / "run.out").open("ab")
    try:
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True,
                                env=env)
    except OSError as e:
        return {"error": f"could not start the loop: {e}"}
    finally:
        log.close()  # the child holds its own copy of the fd
    _PROCS[str(d)] = proc
    return {"ok": True, "dir": str(d), "pid": proc.pid}


def stop_run(payload: dict) -> dict:
    d = Path(str(payload.get("dir", "")).strip()).expanduser()
    if not (d / GOAL_FILENAME).exists():
        return {"error": f"not a 9xf run: {d}"}
    (d / STOP_FILENAME).write_text("stop requested via 9xf app\n")
    return {"ok": True}


# -- HTTP plumbing ------------------------------------------------------------------

class AppHandler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str, code: int = 200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(json.dumps(obj).encode(), "application/json", code)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                self._send(APP_PAGE.encode(), "text/html; charset=utf-8")
            elif url.path == "/api/runs":
                self._json(collect_runs())
            elif url.path == "/api/stats":
                self._json(collect_stats())
            elif url.path == "/api/run":
                self._json(run_detail(Path(q.get("dir", "")).expanduser()))
            elif url.path == "/api/diff":
                self._json(commit_diff(Path(q.get("dir", "")).expanduser(),
                                       q.get("commit", "")))
            elif url.path == "/api/export":
                self._json(export_diagnostic_bundle(Path(q.get("dir", "")).expanduser()))
            elif url.path == "/api/browse":
                self._json(browse(q.get("path", "")))
            elif url.path == "/api/models":
                self._json(list_models())
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:  # never let one bad request kill the app
            self._json({"error": str(e)[:300]}, 500)

    def do_POST(self):
        url = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length).decode() or "{}")
            if url.path == "/api/start":
                self._json(start_run(payload))
            elif url.path == "/api/stop":
                self._json(stop_run(payload))
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:
            self._json({"error": str(e)[:300]}, 500)

    def log_message(self, *args):  # quiet
        pass


def make_server(port: int = 0) -> ThreadingHTTPServer:
    """Bound but not yet serving — tests use port 0 and read the real port."""
    return ThreadingHTTPServer(("127.0.0.1", port), AppHandler)


def serve_app(port: int = 9118, open_browser: bool = True):
    server = make_server(port)
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"[9xf] app at {url} (Ctrl+C to quit)")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[9xf] app stopped")
