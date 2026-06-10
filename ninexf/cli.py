"""CLI: 9xf init | run | status | stop | log"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ninexf import CONFIG_FILENAME, GOAL_FILENAME, STOP_FILENAME, __version__
from ninexf.config import load_config, write_config
from ninexf.gitops import commit_all, init_repo
from ninexf.looplog import read_entries
from ninexf.registry import register_run


def _project_dir(args) -> Path:
    return Path(args.dir).resolve()


def _generate_acceptance_tests(project: Path, goal: str) -> None:
    """One init-time model call writing the held-out acceptance suite.
    Compile-check + one retry; on failure the run degrades gracefully to
    criteria-only verification (logged to stdout, not fatal)."""
    import py_compile
    from ninexf.backends import BackendError, make_backend
    from ninexf.parser import parse_executor_output
    from ninexf.prompts import ACCEPTANCE_TEST_SYSTEM, ACCEPTANCE_TEST_USER

    backend = make_backend(load_config(project))
    target = project / "acceptance" / "test_acceptance.py"
    for attempt in (1, 2):
        try:
            raw = backend.complete(ACCEPTANCE_TEST_SYSTEM,
                                   ACCEPTANCE_TEST_USER.format(goal=goal))
        except BackendError as e:
            print(f"  acceptance-test generation failed (attempt {attempt}): {e}")
            continue
        parsed = parse_executor_output(raw)
        body = (parsed.files.get("acceptance/test_acceptance.py")
                or next(iter(parsed.files.values()), ""))
        if not body:
            print(f"  acceptance-test generation: no file block (attempt {attempt})")
            continue
        target.parent.mkdir(exist_ok=True)
        target.write_text(body)
        try:
            py_compile.compile(str(target), doraise=True)
            print(f"  acceptance tests: {target.relative_to(project)} (held out from the agent)")
            return
        except py_compile.PyCompileError as e:
            print(f"  generated acceptance tests don't compile (attempt {attempt}): {e}")
            target.unlink()
    print("  acceptance tests skipped — verify-done will use criteria only")


def cmd_init(args):
    project = _project_dir(args)
    project.mkdir(parents=True, exist_ok=True)
    if (project / CONFIG_FILENAME).exists() and not args.force:
        sys.exit(f"{CONFIG_FILENAME} already exists in {project} (use --force to overwrite)")

    (project / "src").mkdir(exist_ok=True)
    (project / "tests").mkdir(exist_ok=True)
    (project / "tests" / "__init__.py").touch()
    (project / "tools").mkdir(exist_ok=True)
    (project / GOAL_FILENAME).write_text(args.goal.strip() + "\n")
    write_config(project, {
        "model": args.model,
        "max_iterations": args.max_iterations,
        "delay_seconds": args.delay,
        "allow_network": args.allow_network or None,
        "acceptance_tests": args.acceptance_tests or None,
    })
    (project / ".gitignore").write_text("__pycache__/\n*.pyc\nstate.json\n")
    if args.acceptance_tests:
        _generate_acceptance_tests(project, args.goal.strip())
    if not (project / ".git").exists():
        init_repo(project)
    commit_all(project, "9xf init: goal and config", allow_empty=True)
    register_run(project, args.goal.strip())
    print(f"initialized 9xf project in {project}")
    print(f"  goal:  {args.goal.strip()}")
    print(f"  model: {args.model or 'ollama/qwen2.5-coder:7b (default)'}")
    print(f"run it with: 9xf run --dir {project}")


def cmd_run(args):
    project = _project_dir(args)
    config = load_config(project)
    if not (project / GOAL_FILENAME).exists():
        sys.exit(f"no {GOAL_FILENAME} in {project} — run `9xf init` first")
    if (project / STOP_FILENAME).exists():
        sys.exit(f"a {STOP_FILENAME} file is present — remove it before starting a new run")

    from ninexf.loop import LoopRunner  # late import keeps `init`/`log` fast
    from ninexf.looplog import now_iso
    register_run(project, (project / GOAL_FILENAME).read_text().strip(), started=now_iso())
    try:
        LoopRunner(project, config).run(max_iterations=args.max_iterations, delay=args.delay)
    except KeyboardInterrupt:
        print("\n[9xf] force-quit (second Ctrl+C) — current iteration abandoned")
        sys.exit(130)


def cmd_status(args):
    project = _project_dir(args)
    entries = read_entries(project)
    iters = [e for e in entries if e.get("event") == "iteration"]
    if not entries:
        print("no runs yet")
        return
    last_event = entries[-1]
    print(f"goal: {(project / GOAL_FILENAME).read_text().strip()}")
    print(f"iterations completed: {len(iters)}")
    from ninexf.tasks import load_tasks
    tl = load_tasks(project)
    if tl.tasks:
        done, total = tl.counts()
        deferred = sum(1 for t in tl.tasks if t.status == "!")
        print(f"tasks: {done}/{total} done" + (f" ({deferred} deferred)" if deferred else ""))
    if any(e.get("event") == "finished" for e in entries):
        print("GOAL COMPLETE — verify-done passed")
    if iters:
        last = iters[-1]
        print(f"last sub-task: {last.get('subtask')}")
        print(f"last validation: {'passed' if last.get('validation_passed') else 'FAILED'}"
              f" ({last.get('validation_detail', '')})")
        print(f"last commit: {last.get('commit')}")
    if last_event.get("event") == "shutdown":
        print(f"state: stopped ({last_event.get('summary')})")
    elif last_event.get("event") == "startup":
        print("state: running (or run was force-killed)")
    if (project / STOP_FILENAME).exists():
        print("STOP file present — loop will halt at next iteration boundary")


def cmd_stop(args):
    project = _project_dir(args)
    (project / STOP_FILENAME).write_text("stop requested via `9xf stop`\n")
    print(f"created {project / STOP_FILENAME} — loop will shut down cleanly at the next iteration boundary")


def cmd_log(args):
    project = _project_dir(args)
    entries = read_entries(project)
    if not entries:
        print("no log entries yet")
        return
    for e in entries:
        ev = e.get("event", "iteration")
        if ev == "iteration":
            mark = "✓" if e.get("validation_passed") else "✗"
            flags = "".join([
                " [STUCK]" if e.get("stuck_detected") else "",
                " [REGRESSION]" if e.get("regression") else "",
            ])
            task = f" T{e['task_id']}" if e.get("task_id") else ""
            progress = (f" ({e['tasks_done']}/{e['tasks_total']} tasks)"
                        if e.get("tasks_total") else "")
            print(f"[{e.get('iteration'):>3}] {mark} ({e.get('mode', 'build')}){task}{progress}{flags} "
                  f"{e.get('timestamp', '')}  {e.get('subtask', '')}")
            for tr in e.get("tool_runs", []):
                print(f"       tool {tr.get('name')} {tr.get('args', '')}: {str(tr.get('result', ''))[:120]}")
            if e.get("summary"):
                print(f"       did: {e['summary']}")
            if e.get("files_written"):
                print(f"       wrote: {', '.join(e['files_written'])}")
            if e.get("errors"):
                print(f"       errors: {'; '.join(str(x) for x in e['errors'])[:300]}")
            if e.get("commit"):
                print(f"       commit: {e['commit']}")
        else:
            print(f"[---] ({ev}) {e.get('timestamp', '')}  {e.get('summary', e.get('raw', ''))}")
    if args.raw:
        print("\nraw JSONL:")
        for e in entries:
            print(json.dumps(e))


def cmd_watch(args):
    from ninexf.dashboard import serve
    serve(port=args.port, open_browser=not args.no_browser)


def cmd_report(args):
    from ninexf.report import generate_report
    path = generate_report(_project_dir(args))
    print(f"wrote {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="9xf", description="9xf loops — autonomous coding loop research harness")
    parser.add_argument("--version", action="version", version=f"9xf loops {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_dir(p):
        p.add_argument("--dir", default=".", help="project folder (default: current directory)")

    p = sub.add_parser("init", help="create a new loop project")
    p.add_argument("--goal", required=True, help="the high-level goal (the unchanging north star)")
    p.add_argument("--model", default=None, help="e.g. ollama/qwen2.5-coder:7b, anthropic/claude-sonnet-4-6, mock")
    p.add_argument("--max-iterations", type=int, default=None)
    p.add_argument("--delay", type=float, default=None, help="seconds between iterations")
    p.add_argument("--allow-network", action="store_true",
                   help="opt in to network access for validated code (off by default)")
    p.add_argument("--acceptance-tests", action="store_true",
                   help="generate a held-out acceptance test suite from the goal at init")
    p.add_argument("--force", action="store_true")
    add_dir(p)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("run", help="start the loop")
    p.add_argument("--max-iterations", type=int, default=None, help="override config cap for this run")
    p.add_argument("--delay", type=float, default=None, help="override config delay for this run")
    add_dir(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status", help="show current iteration, last sub-task, validation status")
    add_dir(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("stop", help="create the STOP file (graceful shutdown)")
    add_dir(p)
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("log", help="pretty-print loop_log.jsonl")
    p.add_argument("--raw", action="store_true", help="also dump raw JSONL")
    add_dir(p)
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("watch", help="live dashboard for all registered runs")
    p.add_argument("--port", type=int, default=9119)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_watch)

    p = sub.add_parser("report", help="generate REPORT.md (the written observation report)")
    add_dir(p)
    p.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
