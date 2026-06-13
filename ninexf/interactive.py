"""Interactive mode (v0.5): run bare `9xf` anywhere and drive everything from
menus — no paths, no flags, no remembering subcommands.

Design constraints: stdlib only (numbered menus + input(), no termios/curses,
so it works in every terminal), and every action routes through the same code
paths as the flag-based CLI — interactive mode is a front-end, not a fork.

Flows:
  bare `9xf` in a run folder   -> that run's menu (continue/status/log/report/stop)
  bare `9xf` anywhere else     -> home menu (new run / arena / open a run / dashboard)
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

from ninexf import CONFIG_FILENAME, GOAL_FILENAME, STOP_FILENAME
from ninexf.looplog import read_entries
from ninexf.models import (
    DEFAULT_MODEL,
    GPT_OSS_20B_MODEL,
    model_options,
    ollama_model_id,
)
from ninexf.registry import read_state, registered_runs


# -- tiny presentation helpers --------------------------------------------------

def _tty() -> bool:
    return sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _tty() else text


def _bold(t: str) -> str: return _c("1", t)
def _dim(t: str) -> str: return _c("2", t)
def _cyan(t: str) -> str: return _c("36", t)
def _green(t: str) -> str: return _c("32", t)
def _red(t: str) -> str: return _c("31", t)


def _header(title: str) -> None:
    print()
    print(_bold(_cyan(f"── {title} " + "─" * max(1, 56 - len(title)))))


class _Quit(Exception):
    pass


def _ask(prompt: str, default: str = "") -> str:
    suffix = _dim(f" [{default}]") if default else ""
    try:
        raw = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise _Quit
    return raw or default


def _choose(title: str, options: list[tuple[str, str]], allow_back: bool = False) -> str:
    """options = [(key, label)]. Returns the chosen key ('b' for back, raises
    _Quit on q/Ctrl+C). Re-asks on anything unrecognized."""
    _header(title)
    for key, label in options:
        print(f"  {_bold(key)}) {label}")
    extras = ("b) back  " if allow_back else "") + "q) quit"
    print(_dim(f"  {extras}"))
    valid = {k for k, _ in options} | ({"b"} if allow_back else set()) | {"q"}
    while True:
        choice = _ask("choose").lower()
        if choice == "q":
            raise _Quit
        if choice in valid:
            return choice
        print(_dim(f"  (pick one of: {', '.join(sorted(valid))})"))


def _slug(goal: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", goal.lower()).strip("-")
    return (s[:40] or "run").rstrip("-")


def _ollama_models(endpoint: str = "http://localhost:11434") -> list[str]:
    """Locally installed Ollama models, best-effort (empty list if unreachable)."""
    try:
        with urllib.request.urlopen(f"{endpoint}/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode())
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def _pick_model() -> str:
    models = _ollama_models()
    installed = {ollama_model_id(name) for name in models}
    choices = model_options(models[:8])
    options = []
    for i, model in enumerate(choices, start=1):
        suffix = ""
        if model not in installed:
            suffix = " (recommended; install with `ollama pull gpt-oss:20b`)" if model == GPT_OSS_20B_MODEL else " (recommended)"
        options.append((str(i), f"{model}{suffix}"))
    options.append(("0", "type something else (e.g. nvidia/moonshotai/kimi-k2.6)"))
    title = "Pick a model"
    if models:
        title += " (installed Ollama models first)"
    else:
        title += " (recommended local models)"
    choice = _choose(title, options)
    if choice == "0":
        return _ask("model", DEFAULT_MODEL)
    return choices[int(choice) - 1]


# -- run summaries ----------------------------------------------------------------

def _is_project(d: Path) -> bool:
    return (d / CONFIG_FILENAME).exists() and (d / GOAL_FILENAME).exists()


def _summary_line(d: Path) -> str:
    goal = (d / GOAL_FILENAME).read_text().strip() if (d / GOAL_FILENAME).exists() else "?"
    entries = read_entries(d)
    iters = sum(1 for e in entries if e.get("event") == "iteration")
    state = read_state(d)
    if any(e.get("event") == "finished" for e in entries):
        status = _green("FINISHED")
    elif state.get("running"):
        status = _cyan("running")
    else:
        status = _dim("stopped")
    return f"{goal[:48]:<50} {status}  {_dim(f'{iters} iters')}"


def _print_project_summary(d: Path) -> None:
    goal = (d / GOAL_FILENAME).read_text().strip()
    entries = read_entries(d)
    iters = [e for e in entries if e.get("event") == "iteration"]
    print(f"  {_bold('goal:')} {goal}")
    print(f"  {_bold('dir:')}  {d}")
    if any(e.get("event") == "finished" for e in entries):
        print(f"  {_green('● GOAL COMPLETE — verify-done passed')}")
    if iters:
        last = iters[-1]
        ok = last.get("validation_passed")
        print(f"  {_bold('last:')} iter {last.get('iteration')} "
              f"{_green('✓') if ok else _red('✗')} {last.get('subtask', '')[:60]}")
    from ninexf.tasks import load_tasks
    tl = load_tasks(d)
    if tl.tasks:
        done, total = tl.counts()
        print(f"  {_bold('tasks:')} {done}/{total} done")


def _tail_log(d: Path, n: int = 12) -> None:
    entries = read_entries(d)
    if not entries:
        print(_dim("  no log entries yet"))
        return
    for e in entries[-n:]:
        ev = e.get("event", "iteration")
        if ev == "iteration":
            mark = _green("✓") if e.get("validation_passed") else _red("✗")
            print(f"  [{e.get('iteration'):>3}] {mark} ({e.get('mode', 'build')}) "
                  f"{e.get('subtask', '')[:70]}")
            if e.get("errors"):
                print(_dim(f"        errors: {'; '.join(str(x) for x in e['errors'])[:90]}"))
        else:
            print(_dim(f"  [---] ({ev}) {e.get('summary', '')[:80]}"))


# -- actions ----------------------------------------------------------------------

def _start_loop(d: Path) -> None:
    mode = _choose("How long should it run?", [
        ("1", "until done or config cap (just go)"),
        ("2", "a number of iterations"),
        ("3", "a wall-clock budget in hours (overnight)"),
    ], allow_back=True)
    if mode == "b":
        return
    iters = hours = None
    if mode == "2":
        iters = int(_ask("iterations", "20") or "20")
    elif mode == "3":
        hours = float(_ask("hours", "8") or "8")
    from ninexf.config import load_config
    from ninexf.loop import LoopRunner
    from ninexf.looplog import now_iso
    from ninexf.registry import register_run
    register_run(d, (d / GOAL_FILENAME).read_text().strip(), started=now_iso())
    if (d / STOP_FILENAME).exists():
        (d / STOP_FILENAME).unlink()
        print(_dim("  (removed leftover STOP file)"))
    print(_dim("  Ctrl+C once = clean stop at the iteration boundary; twice = force quit\n"))
    try:
        LoopRunner(d, load_config(d)).run(max_iterations=iters, hours=hours)
    except KeyboardInterrupt:
        print("\n[9xf] force-quit — current iteration abandoned")


def _new_run_wizard(base: Path) -> Path | None:
    _header("New run")
    try:
        goal = _ask("goal (one sentence — the unchanging north star)")
        if not goal:
            print(_dim("  a goal is required"))
            return None
        mode = _choose("Mode", [
            ("1", "regular — sensible defaults, good for watching it work"),
            ("2", "overnight — maximum verified search (best-of-N, critic, "
                  "explore, repair, held-out acceptance tests, keep-best)"),
        ], allow_back=True)
        if mode == "b":
            return None
        model = _pick_model()
        folder = _ask("folder", str(base / _slug(goal)))
    except _Quit:
        raise
    from ninexf.cli import main as cli_main
    argv = ["init", "--goal", goal, "--model", model, "--dir", folder]
    if mode == "2":
        argv += ["--preset", "overnight"]
    cli_main(argv)
    d = Path(folder).resolve()
    if _choose("Start it now?", [("1", "yes"), ("2", "not yet")]) == "1":
        _start_loop(d)
    return d


def _new_arena_wizard(base: Path) -> None:
    _header("New arena (tournament)")
    print(_dim("  K seed runs race in short bursts; the best one gets the rest\n"
               "  of the budget. Same total compute as one long run — diversity\n"
               "  early, depth late."))
    try:
        goal = _ask("goal (one sentence)")
        if not goal:
            print(_dim("  a goal is required"))
            return
        seeds = int(_ask("seeds", "3") or "3")
        hours = float(_ask("total hours", "8") or "8")
        model = _pick_model()
        folder = _ask("folder", str(base / f"arena-{_slug(goal)}"))
    except _Quit:
        raise
    from ninexf.arena import run_arena
    print(_dim("  Ctrl+C once = clean stop; the arena scores whatever ran\n"))
    try:
        run_arena(Path(folder).resolve(), goal, model=model, seeds=seeds, hours=hours)
    except KeyboardInterrupt:
        print("\n[9xf] arena force-quit")


def _open_run_menu() -> Path | None:
    runs = registered_runs()
    if not runs:
        print(_dim("  no registered runs yet — start one first"))
        return None
    options = [(str(i), _summary_line(d)) for i, d in enumerate(runs[:20], start=1)]
    choice = _choose("Registered runs", options, allow_back=True)
    if choice == "b":
        return None
    return runs[int(choice) - 1]


def _project_menu(d: Path) -> None:
    while True:
        _header(f"run: {d.name}")
        _print_project_summary(d)
        choice = _choose("What now?", [
            ("1", "run / continue the loop"),
            ("2", "recent log"),
            ("3", "full status"),
            ("4", "generate REPORT.md"),
            ("5", "live dashboard (browser)"),
            ("6", "request stop (create STOP file)"),
        ], allow_back=True)
        if choice == "b":
            return
        from types import SimpleNamespace
        from ninexf import cli
        if choice == "1":
            _start_loop(d)
        elif choice == "2":
            _tail_log(d)
        elif choice == "3":
            cli.cmd_status(SimpleNamespace(dir=str(d)))
        elif choice == "4":
            cli.cmd_report(SimpleNamespace(dir=str(d)))
        elif choice == "5":
            cli.cmd_watch(SimpleNamespace(port=9119, no_browser=False))
        elif choice == "6":
            cli.cmd_stop(SimpleNamespace(dir=str(d)))


def _home_menu(cwd: Path) -> None:
    while True:
        choice = _choose("9xf — what do you want to do?", [
            ("1", "start a new run"),
            ("2", "start an arena (tournament of seed runs)"),
            ("3", "open one of my runs"),
            ("4", "live dashboard (browser)"),
            ("5", "chat app UI (browser — sessions, live chat, diffs)"),
        ])
        if choice == "1":
            d = _new_run_wizard(cwd)
            if d is not None:
                _project_menu(d)
        elif choice == "2":
            _new_arena_wizard(cwd)
        elif choice == "3":
            d = _open_run_menu()
            if d is not None:
                _project_menu(d)
        elif choice == "4":
            from types import SimpleNamespace
            from ninexf import cli
            cli.cmd_watch(SimpleNamespace(port=9119, no_browser=False))
        elif choice == "5":
            from ninexf.webapp import serve_app
            serve_app()


def interactive() -> None:
    from ninexf import __version__
    cwd = Path.cwd()
    print(_bold(_cyan(f"\n  9xf loops v{__version__}")) +
          _dim("  — autonomous coding loops on your own machine"))
    print(_dim(f"  folder: {cwd}"))
    try:
        if _is_project(cwd):
            print(_dim("  (this folder is a 9xf run)"))
            _project_menu(cwd)
            _home_menu(cwd)
        else:
            _home_menu(cwd)
    except _Quit:
        pass
    print(_dim("\n  bye\n"))
