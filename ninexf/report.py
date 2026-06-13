"""`9xf report` — generate the PRD §12 written observation report (REPORT.md)
from loop_log.jsonl + git history. The report is a researcher artifact; it is
excluded from the agent's context (see SKIP_FILES in context.py).
"""

from __future__ import annotations

import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

from ninexf import GOAL_FILENAME
from ninexf.config import load_config
from ninexf.looplog import read_entries
from ninexf.tasks import load_tasks

WINDOW = 5  # iterations per pass-rate window


def _duration(entries: list[dict]) -> str:
    stamps = [e.get("timestamp") for e in entries if e.get("timestamp")]
    if len(stamps) < 2:
        return "n/a"
    try:
        delta = datetime.fromisoformat(stamps[-1]) - datetime.fromisoformat(stamps[0])
        return str(delta).split(".")[0]
    except ValueError:
        return "n/a"


def _verdict(rates: list[float], finished: bool = False) -> str:
    if finished:
        return "FINISHED — verify-done passed (harness validation green + all acceptance criteria)"
    if not rates:
        return "no data"
    if len(rates) == 1:
        return "too short to call — single window"
    first, last = rates[0], rates[-1]
    if last >= 0.8 and last >= first:
        return "PROGRESSING — validation pass rate is high and holding/improving"
    if last < first - 0.2:
        return "REGRESSING — pass rate declined over the run"
    if max(rates) - min(rates) < 0.15 and last < 0.6:
        return "STALLED — pass rate flat and low"
    return "MIXED — see windowed trend below"


def _commit_table(project_dir: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "--reverse", "--format=%h\t%s"],
            cwd=project_dir, capture_output=True, text=True, timeout=30,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return "(git unavailable)"
    rows = ["| commit | message |", "|---|---|"]
    for line in out.strip().splitlines():
        h, _, s = line.partition("\t")
        if s.endswith("log entry"):
            continue  # bookkeeping commits add noise here
        rows.append(f"| `{h}` | {s.replace('|', '\\|')} |")
    return "\n".join(rows)


def generate_report(project_dir: Path) -> Path:
    entries = read_entries(project_dir)
    iters = [e for e in entries if e.get("event") == "iteration"]
    violations = [e for e in entries if e.get("event") == "violation"]
    goal = (project_dir / GOAL_FILENAME).read_text().strip()
    try:
        cfg = load_config(project_dir)
        model = cfg.model
    except FileNotFoundError:
        cfg, model = None, "?"

    n = len(iters)
    passed = [e for e in iters if e.get("validation_passed")]
    failed = [e for e in iters if not e.get("validation_passed")]
    regressions = [e for e in iters if e.get("regression")]
    stuck = [e for e in iters if e.get("stuck_detected")]
    syntax_fails = [
        e for e in iters
        if any("syntax" in str(x).lower() or "SyntaxError" in str(x) for x in e.get("errors", []))
    ]
    modes = Counter(e.get("mode", "build") for e in iters)
    nothing_written = [e for e in iters if not e.get("files_written")]
    model_calls = [c for e in entries for c in (e.get("model_calls") or [])]
    model_call_counts = Counter(c.get("purpose", "?") for c in model_calls)
    model_seconds = sum(float(c.get("latency_s", 0) or 0) for c in model_calls)
    model_errors = [c for c in model_calls if not c.get("ok")]

    windows, rates = [], []
    for i in range(0, n, WINDOW):
        w = iters[i:i + WINDOW]
        rate = sum(1 for e in w if e.get("validation_passed")) / len(w)
        rates.append(rate)
        windows.append(f"| {w[0]['iteration']}–{w[-1]['iteration']} | {rate:.0%} |")

    files = Counter()
    for e in iters:
        for f in e.get("files_written", []):
            files[f] += 1

    tool_creations = sorted({
        f for e in iters for f in e.get("files_written", []) if f.startswith("tools/")
    })
    tool_uses = [(e["iteration"], tr) for e in iters for tr in e.get("tool_runs", [])]

    # v0.3: decomposition / verify-done / finished events + task-list state
    revert_events = [e for e in entries if e.get("event") == "revert"]
    explore_events = [e for e in entries if e.get("event") == "explore"]
    signal_counts = Counter(s for e in iters for s in e.get("stuck_signals", []))
    decompose_events = [e for e in entries if e.get("event") == "decompose"]
    verify_events = [e for e in entries if e.get("event") == "verify"]
    finished_events = [e for e in entries if e.get("event") == "finished"]
    finished = bool(finished_events)
    tl = load_tasks(project_dir)
    tasks_done, tasks_total = tl.counts()
    deferred = [t for t in tl.tasks if t.status == "!"]
    task_drift = [e for e in iters if not e.get("task_id")] if tasks_total else []

    lines = [
        "# 9xf observation report",
        "",
        f"**Goal:** {goal}",
        f"**Model:** {model}  |  **Iterations:** {n}  |  **Wall time:** {_duration(entries)}",
        "",
        f"## Verdict: {_verdict(rates, finished)}",
        "",
        f"- validation passed: {len(passed)}/{n}"
        + (f" ({len(passed)/n:.0%})" if n else ""),
        f"- regressions (working → broken): {len(regressions)}"
        + (f" at iterations {[e['iteration'] for e in regressions]}" if regressions else ""),
        f"- stuck episodes (repeated subtask, nudged): {len(stuck)}"
        + (f" at iterations {[e['iteration'] for e in stuck]}" if stuck else ""),
        f"- containment violations: {len(violations)}",
        f"- iteration modes: " + ", ".join(f"{m}×{c}" for m, c in modes.most_common()),
        "",
        "## Done detection (v0.3)",
        "",
        f"- decomposition: " + (
            f"{decompose_events[0].get('summary', '')}" if decompose_events
            else "not attempted (decompose_enabled off or pre-v0.3 run)"),
        f"- task completion: {tasks_done}/{tasks_total} done"
        + (f", {len(deferred)} deferred ({', '.join('T' + str(t.num) for t in deferred)})"
           if deferred else ""),
        f"- planner task-targeting drift (iterations with no task id): "
        + (f"{len(task_drift)}/{n}" if tasks_total else "n/a (no task list)"),
        f"- verify-done attempts: {len(verify_events) + len(finished_events)}"
        + (f"; failed attempts: " + "; ".join(
            f"iter {e['iteration']} ({e.get('summary', '')})" for e in verify_events)
           if verify_events else ""),
        f"- finished: " + (
            f"YES at iteration {finished_events[0]['iteration']}" if finished
            else "no — run ended without goal completion"),
        "",
        "## Context selection (v0.3)",
        "",
        f"- strategy: {getattr(cfg, 'context_strategy', '?') if cfg else '?'}",
        f"- most-shown files: " + (
            ", ".join(f"`{f}`×{c}" for f, c in Counter(
                f for e in iters for f in e.get("context_files", [])).most_common(8))
            or "n/a (pre-v0.3 log)"),
        f"- notes written: {sum(len(e.get('notes_added', [])) for e in iters)}",
        f"- context overflows (prompt filled num_ctx — silent truncation risk): "
        f"{sum(1 for e in iters if e.get('context_overflow'))}/{n}",
        f"- partial file renders: "
        f"{sum(1 for e in iters for f in e.get('context_files', []) if '(partial)' in f)}",
        "",
        "## Model/backend telemetry",
        "",
        f"- model calls logged: {len(model_calls)}",
        f"- model wall time: {model_seconds:.1f}s",
        f"- average prompt size: "
        + (f"{sum(int(c.get('prompt_chars', 0) or 0) for c in model_calls) // len(model_calls)} chars"
           if model_calls else "n/a"),
        f"- calls by purpose: " + (
            ", ".join(f"{k}×{v}" for k, v in model_call_counts.most_common())
            if model_calls else "n/a"),
        f"- backend/model-call errors: {len(model_errors)}",
        "",
        "## Verification (v0.3)",
        "",
        f"- acceptance suite: " + (
            f"{sum(1 for e in iters if e.get('acceptance_passed'))} green / "
            f"{sum(1 for e in iters if e.get('acceptance_passed') is not None)} runs"
            if any(e.get('acceptance_passed') is not None for e in iters)
            else "not present"),
        f"- critic verdicts: " + (
            ", ".join(f"{v}×{c}" for v, c in Counter(
                e.get("critic_verdict") for e in iters if e.get("critic_verdict")).most_common())
            or "critic off"),
        f"- critic revisions that ended green: "
        f"{sum(1 for e in iters if e.get('critic_revised') and e.get('validation_passed'))}"
        f"/{sum(1 for e in iters if e.get('critic_revised'))}",
        f"- best-of-N iterations: {sum(1 for e in iters if len(e.get('candidates', [])) > 1)}"
        f"; non-first candidate won: "
        f"{sum(1 for e in iters if e.get('chosen_candidate', 0) > 0)}",
        f"- in-iteration repairs: "
        f"{sum(1 for e in iters if e.get('repairs'))} iteration(s) repaired, "
        f"{sum(1 for e in iters if e.get('repairs') and e['repairs'][-1].get('passed'))} "
        f"ended green",
        "",
        "## Recovery events (v0.3)",
        "",
        f"- auto-reverts: {len([e for e in revert_events if e.get('reverted_to')])}"
        + ("".join(f"\n  - iter {e['iteration']}: {e.get('summary', '')}"
                   for e in revert_events) if revert_events else ""),
        f"- stuck-signal histogram: " + (
            ", ".join(f"{k}×{c}" for k, c in signal_counts.most_common())
            if signal_counts else "none fired"),
        f"- best-state restore at shutdown (keep_best): " + (
            "; ".join(e.get("summary", "") for e in entries
                      if e.get("event") == "restore_best") or "not needed"),
        f"- exploration episodes: {len(explore_events)}"
        + ("".join(f"\n  - iter {e['iteration']}: {e.get('summary', '')} "
                   f"(A {'ok' if e.get('explore', {}).get('a', {}).get('passed') else 'failed'}, "
                   f"B {'ok' if e.get('explore', {}).get('b', {}).get('passed') else 'failed'})"
                   for e in explore_events) if explore_events else ""),
        "",
        "## Validation pass rate by window",
        "",
        f"| iterations | pass rate |",
        "|---|---|",
        *windows,
        "",
        "## PRD §11 known-limitation evidence",
        "",
        f"- syntactically invalid code committed: {len(syntax_fails)}/{n} iterations",
        f"- model output unparseable / nothing written: {len(nothing_written)}/{n} iterations",
        f"- broken code confidently committed (any validation failure): {len(failed)}/{n}",
        f"- subtask repetition detected: {len(stuck)} time(s)",
        "",
        "## Self-created tools",
        "",
        ("- created: " + ", ".join(f"`{t}`" for t in tool_creations)) if tool_creations
        else "- none created",
    ]
    for it, tr in tool_uses:
        lines.append(f"- iter {it} ran `{tr.get('name')}` {tr.get('args', '')}: "
                     f"{str(tr.get('result', ''))[:120]}")
    lines += [
        "",
        "## Files touched (write counts)",
        "",
        "| file | writes |",
        "|---|---|",
        *[f"| `{f}` | {c} |" for f, c in files.most_common(20)],
        "",
        "## Commit timeline",
        "",
        _commit_table(project_dir),
        "",
        "## Failures in detail",
        "",
    ]
    for e in failed:
        errs = "; ".join(str(x) for x in e.get("errors", []))[:300]
        lines.append(f"- iter {e['iteration']} ({e.get('mode', 'build')}): "
                     f"{e.get('subtask', '')!r} — {errs}")
    if not failed:
        lines.append("- none")

    out = project_dir / "REPORT.md"
    out.write_text("\n".join(lines) + "\n")
    return out
