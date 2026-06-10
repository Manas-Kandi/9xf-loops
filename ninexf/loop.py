"""The loop: read state -> self-generate sub-task -> execute -> validate -> commit -> log.

v0.2 additions: iteration modes (build / fix / review), stuck detection with a
re-plan nudge, regression flagging, agent-created tool runs, and a state.json
heartbeat for the dashboard. Failed iterations are still committed (failed
attempts are research data). Shutdown paths (STOP file, Ctrl+C, iteration cap,
repeated backend failure) all go through the same clean-shutdown sequence.
"""

from __future__ import annotations

import difflib
import signal
import time
from pathlib import Path

from ninexf import GOAL_FILENAME, STOP_FILENAME
from ninexf.backends import Backend, BackendError, make_backend
from ninexf.config import Config
from ninexf.context import history_for_context, snapshot_codebase
from ninexf.gitops import commit_all, has_changes
from ninexf.looplog import LogEntry, append_entry, last_iteration_number, now_iso, read_entries
from ninexf.parser import parse_executor_output
from ninexf.prompts import (
    EXECUTOR_SYSTEM, EXECUTOR_USER, MODE_BUILD, MODE_FIX, MODE_REVIEW,
    PLANNER_SYSTEM, PLANNER_USER, STUCK_NUDGE,
)
from ninexf.registry import write_state
from ninexf.sandbox import ContainmentViolation, safe_write
from ninexf.tools import run_tool, tools_for_prompt
from ninexf.validate import validate

MAX_CONSECUTIVE_BACKEND_FAILURES = 3
STUCK_LOOKBACK = 5


class LoopRunner:
    def __init__(self, project_dir: Path, config: Config):
        self.project_dir = project_dir
        self.config = config
        self.backend: Backend = make_backend(config)
        self.goal = (project_dir / GOAL_FILENAME).read_text().strip()
        self._interrupted = False

    # -- shutdown plumbing ----------------------------------------------------

    def _install_sigint(self):
        def handler(signum, frame):
            if self._interrupted:  # second Ctrl+C: give up politely
                raise KeyboardInterrupt
            self._interrupted = True
            print("\n[9xf] Ctrl+C received — finishing this iteration, then shutting down cleanly.")

        signal.signal(signal.SIGINT, handler)

    def _stop_requested(self) -> str | None:
        if (self.project_dir / STOP_FILENAME).exists():
            return "STOP file detected"
        if self._interrupted:
            return "interrupted by Ctrl+C"
        return None

    def _clean_shutdown(self, iteration: int, reason: str):
        print(f"[9xf] shutting down: {reason}")
        append_entry(self.project_dir, LogEntry(
            iteration=iteration, timestamp=now_iso(), subtask="", summary=reason,
            event="shutdown",
        ))
        write_state(self.project_dir, running=False, iteration=iteration,
                    stopped_reason=reason, ts=now_iso())
        try:
            if has_changes(self.project_dir):
                commit_all(self.project_dir, f"9xf shutdown: {reason}")
            else:
                commit_all(self.project_dir, f"9xf shutdown: {reason}", allow_empty=True)
        except Exception as e:
            print(f"[9xf] warning: shutdown commit failed: {e}")

    # -- mode scheduling & stuck detection -------------------------------------

    def _pick_mode(self, iteration: int) -> str:
        prev = [e for e in read_entries(self.project_dir) if e.get("event") == "iteration"]
        if prev and not prev[-1].get("validation_passed"):
            return "fix"
        if self.config.review_every > 0 and iteration % self.config.review_every == 0:
            return "review"
        return "build"

    def _recent_subtasks(self) -> list[str]:
        entries = [e for e in read_entries(self.project_dir) if e.get("event") == "iteration"]
        return [e.get("subtask", "") for e in entries[-STUCK_LOOKBACK:] if e.get("subtask")]

    def _find_repeats(self, subtask: str) -> list[str]:
        repeats = []
        for prior in self._recent_subtasks():
            ratio = difflib.SequenceMatcher(None, subtask.lower(), prior.lower()).ratio()
            if ratio > self.config.stuck_similarity:
                repeats.append(prior)
        return repeats

    def _plan(self, mode: str, codebase: str, history: str, tools: str) -> tuple[str, bool]:
        """Generate the sub-task; on repetition, re-ask once with a nudge.
        Returns (subtask, stuck_detected)."""
        mode_instructions = {"build": MODE_BUILD, "fix": MODE_FIX, "review": MODE_REVIEW}[mode]
        base = PLANNER_USER.format(
            goal=self.goal, codebase=codebase, history=history,
            tools=tools, mode_instructions=mode_instructions,
        )
        subtask = self.backend.complete(PLANNER_SYSTEM, base).strip().splitlines()[0][:500]
        repeats = self._find_repeats(subtask)
        if not repeats:
            return subtask, False
        nudge = STUCK_NUDGE.format(repeats="\n".join(f"  - {r!r}" for r in repeats))
        retry = self.backend.complete(PLANNER_SYSTEM, base + nudge).strip().splitlines()[0][:500]
        # keep the retry even if still similar — one nudge only; persistence is data
        return retry, True

    # -- one iteration ---------------------------------------------------------

    def run_iteration(self, iteration: int) -> LogEntry:
        cfg = self.config
        codebase = snapshot_codebase(self.project_dir, cfg.context_char_budget)
        history = history_for_context(self.project_dir, cfg.history_entries_in_context)
        tools = tools_for_prompt(self.project_dir) if cfg.tools_enabled else "(tools disabled)"
        mode = self._pick_mode(iteration)

        prev_entries = [e for e in read_entries(self.project_dir) if e.get("event") == "iteration"]
        prev_passed = bool(prev_entries and prev_entries[-1].get("validation_passed"))

        # 1. self-generate the sub-task (with one anti-repetition retry)
        subtask, stuck = self._plan(mode, codebase, history, tools)
        print(f"[9xf] iter {iteration} ({mode}{', stuck' if stuck else ''}) subtask: {subtask}")
        write_state(self.project_dir, running=True, iteration=iteration, mode=mode,
                    subtask=subtask, ts=now_iso())

        # 2. execute it
        raw = self.backend.complete(
            EXECUTOR_SYSTEM,
            EXECUTOR_USER.format(goal=self.goal, codebase=codebase, subtask=subtask, tools=tools),
        )
        parsed = parse_executor_output(raw)

        errors = list(parsed.problems)
        written: list[Path] = []
        for rel_path, content in parsed.files.items():
            try:
                written.append(safe_write(self.project_dir, rel_path, content))
            except ContainmentViolation as v:
                errors.append(str(v))
                append_entry(self.project_dir, LogEntry(
                    iteration=iteration, timestamp=now_iso(), subtask=subtask,
                    summary=f"containment violation: {v.requested!r}", event="violation",
                ))

        # 3. run requested tools (agent-created helper scripts)
        tool_runs = []
        if cfg.tools_enabled:
            for name, args in parsed.tool_runs[: cfg.max_tool_runs_per_iteration]:
                result = run_tool(self.project_dir, name, args,
                                  cfg.validation_timeout, cfg.allow_network)
                tool_runs.append({"name": name, "args": args, "result": result})
                print(f"[9xf]   tool {name} {args}: {result[:120]}")
            dropped = len(parsed.tool_runs) - len(tool_runs)
            if dropped > 0:
                errors.append(f"{dropped} tool run(s) dropped (cap {cfg.max_tool_runs_per_iteration})")

        # 4. validate
        if written:
            result = validate(self.project_dir, written, cfg.validation_timeout,
                              cfg.allow_network, run_tests=cfg.run_tests)
            errors.extend(result.errors)
            validation_passed, validation_detail = result.passed, result.detail
            tests_ran = result.tests_ran
        else:
            validation_passed, validation_detail, tests_ran = False, "nothing written", 0

        failed = not validation_passed or bool(errors)
        regression = prev_passed and failed

        # 5. commit (failed attempts included — research data)
        status = "failed" if failed else "ok"
        commit_msg = f"[iter {iteration}] ({mode}/{status}) {subtask}\n\n{parsed.summary}"
        commit_hash = ""
        if has_changes(self.project_dir):
            commit_hash = commit_all(self.project_dir, commit_msg)

        entry = LogEntry(
            iteration=iteration,
            timestamp=now_iso(),
            subtask=subtask,
            summary=parsed.summary,
            files_written=[str(p.relative_to(self.project_dir)) for p in written],
            validation_passed=validation_passed,
            validation_detail=validation_detail,
            errors=errors,
            commit=commit_hash,
            mode=mode,
            stuck_detected=stuck,
            regression=regression,
            tests_ran=tests_ran,
            tool_runs=tool_runs,
        )
        append_entry(self.project_dir, entry)
        write_state(self.project_dir, running=True, iteration=iteration, mode=mode,
                    subtask=subtask, validation_passed=validation_passed, ts=now_iso())

        # commit the log line itself so git history and log stay in lockstep
        if has_changes(self.project_dir):
            commit_all(self.project_dir, f"[iter {iteration}] log entry")
        return entry

    # -- the loop ----------------------------------------------------------------

    def run(self, max_iterations: int | None = None, delay: float | None = None):
        cfg = self.config
        cap = max_iterations if max_iterations is not None else cfg.max_iterations
        sleep_s = delay if delay is not None else cfg.delay_seconds
        self._install_sigint()

        start = last_iteration_number(self.project_dir)
        append_entry(self.project_dir, LogEntry(
            iteration=start, timestamp=now_iso(), subtask="",
            summary=f"run started (model={cfg.model}, cap={cap}, delay={sleep_s}s)",
            event="startup",
        ))
        write_state(self.project_dir, running=True, iteration=start, ts=now_iso())
        print(f"[9xf] goal: {self.goal}")
        print(f"[9xf] model: {cfg.model} | starting at iteration {start + 1}, cap {cap}")

        backend_failures = 0
        iteration = start
        while iteration - start < cap:
            reason = self._stop_requested()
            if reason:
                self._clean_shutdown(iteration, reason)
                return

            iteration += 1
            try:
                entry = self.run_iteration(iteration)
                backend_failures = 0
                mark = "✓" if entry.validation_passed else "✗"
                print(f"[9xf] iter {iteration} {mark} {entry.summary or '(no summary)'}"
                      f"  [{entry.commit or 'no commit'}]")
            except BackendError as e:
                backend_failures += 1
                print(f"[9xf] iter {iteration} backend error ({backend_failures}/"
                      f"{MAX_CONSECUTIVE_BACKEND_FAILURES}): {e}")
                append_entry(self.project_dir, LogEntry(
                    iteration=iteration, timestamp=now_iso(), subtask="",
                    summary="backend error", errors=[str(e)], validation_passed=False,
                ))
                if backend_failures >= MAX_CONSECUTIVE_BACKEND_FAILURES:
                    self._clean_shutdown(iteration, "too many consecutive backend failures")
                    return

            reason = self._stop_requested()
            if reason:
                self._clean_shutdown(iteration, reason)
                return
            if iteration - start < cap:
                time.sleep(sleep_s)

        self._clean_shutdown(iteration, f"iteration cap reached ({cap})")
