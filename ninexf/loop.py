"""The loop: read state -> self-generate sub-task -> execute -> validate -> commit -> log.

v0.2 additions: iteration modes (build / fix / review), stuck detection with a
re-plan nudge, regression flagging, agent-created tool runs, and a state.json
heartbeat for the dashboard. Failed iterations are still committed (failed
attempts are research data). Shutdown paths (STOP file, Ctrl+C, iteration cap,
repeated backend failure) all go through the same clean-shutdown sequence.

v0.3 additions: goal decomposition into a harness-managed task list
(TASKS.md + ACCEPTANCE.md), per-task targeting and completion checks, task
deferral after repeated failures, and a verify_done mode that lets a run
FINISH ("goal complete") instead of only hitting the iteration cap.
"""

from __future__ import annotations

import signal
import time
from pathlib import Path

from dataclasses import dataclass, field

from ninexf import GOAL_FILENAME, STOP_FILENAME
from ninexf.backends import Backend, BackendError, make_backend
from ninexf.candidates import (
    CANDIDATE_TEMPERATURES, CandidateResult, best_of_n_active,
    parse_critic_output, pick_winner,
)
from ninexf.config import Config
from ninexf.context import (
    append_notes, build_snapshot, changes_since_last, history_for_context,
    notes_for_prompt, snapshot_codebase,
)
from ninexf.explore import count_explores, should_explore
from ninexf.gitops import (
    checkout_branch, commit_all, create_branch, current_branch, has_changes,
    rename_branch, restore_paths, staged_diff,
)
from ninexf.looplog import LogEntry, append_entry, last_iteration_number, now_iso, read_entries
from ninexf.parser import parse_executor_output
from ninexf.parser import ParsedOutput
from ninexf.prompts import (
    CHANGES_SECTION, CRITIC_SYSTEM, CRITIC_USER, DECOMPOSE_SYSTEM, DECOMPOSE_USER,
    EXECUTOR_SYSTEM, EXECUTOR_USER, EXPLORE_NUDGE_A, EXPLORE_NUDGE_B,
    MODE_BUILD, MODE_FIX, MODE_REVIEW, NO_TESTS_NOTE, NOTES_SECTION,
    PLANNER_SYSTEM, PLANNER_USER, REVISE_NOTE, STUCK_NUDGE,
    TASK_CHECK_SYSTEM, TASK_CHECK_USER, TASKS_SECTION,
    VERIFY_DONE_SYSTEM, VERIFY_DONE_USER,
)
from ninexf.registry import write_state
from ninexf.sandbox import WRITABLE_DIRS, ContainmentViolation, safe_write
from ninexf.stuck import detect_signals
from ninexf.tasks import (
    STATUS_DEFERRED, STATUS_DONE, STATUS_IN_PROGRESS, Task, TaskList,
    criteria_for_prompt, load_criteria, load_tasks, mark_status,
    parse_decomposition, parse_task_ref, parse_verify_output, save_criteria, save_tasks,
    strip_task_ref, tasks_for_prompt, tasks_path, append_tasks,
)
from ninexf.tools import run_tool, tools_for_prompt
from ninexf.validate import run_acceptance, validate

MAX_CONSECUTIVE_BACKEND_FAILURES = 3
MAX_REVERTS_TO_SAME_COMMIT = 2
CRITIC_DIFF_CHARS = 6000


@dataclass
class ExecOutcome:
    """One executor attempt: parsed output, written files, validation result."""
    parsed: ParsedOutput
    written: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    validation_passed: bool = False
    validation_detail: str = ""
    tests_ran: int = 0


class LoopRunner:
    def __init__(self, project_dir: Path, config: Config):
        self.project_dir = project_dir
        self.config = config
        self.backend: Backend = make_backend(config)
        self.goal = (project_dir / GOAL_FILENAME).read_text().strip()
        self._interrupted = False
        self._finished = False  # set when verify_done declares the goal complete

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
        tl = load_tasks(self.project_dir)
        if tl.all_resolved() and self._verify_attempts() < self.config.max_verify_attempts:
            return "verify_done"
        prev = [e for e in read_entries(self.project_dir) if e.get("event") == "iteration"]
        if prev and not prev[-1].get("validation_passed"):
            return "fix"
        if self.config.review_every > 0 and iteration % self.config.review_every == 0:
            return "review"
        return "build"

    def _verify_attempts(self) -> int:
        return sum(1 for e in read_entries(self.project_dir)
                   if e.get("event") in ("verify", "finished"))

    def _planner_base(self, mode: str, codebase: str, history: str, tools: str) -> str:
        mode_instructions = {"build": MODE_BUILD, "fix": MODE_FIX, "review": MODE_REVIEW}[mode]
        has_src = any((self.project_dir / "src").glob("*.py"))
        has_tests = any((self.project_dir / "tests").glob("test_*.py"))
        if has_src and not has_tests:
            mode_instructions += NO_TESTS_NOTE
        tasks = tasks_for_prompt(self.project_dir)
        tasks_section = TASKS_SECTION.format(tasks=tasks) if tasks else ""
        notes = notes_for_prompt(self.project_dir) if self.config.notes_enabled else ""
        notes_section = NOTES_SECTION.format(notes=notes) if notes else ""
        entries = [e for e in read_entries(self.project_dir) if e.get("event") == "iteration"]
        last_commit = entries[-1].get("commit", "") if entries else ""
        changes = changes_since_last(self.project_dir, last_commit, self.config.diff_char_budget)
        changes_section = CHANGES_SECTION.format(changes=changes) if changes else ""
        return PLANNER_USER.format(
            goal=self.goal, codebase=codebase, history=history,
            tools=tools, mode_instructions=mode_instructions,
            tasks_section=tasks_section, notes_section=notes_section,
            changes_section=changes_section,
        )

    def _plan(self, mode: str, codebase: str, history: str, tools: str) -> tuple[str, list[str]]:
        """Generate the sub-task; if stuck signals fire, re-ask once with a
        signal-specific nudge. Returns (subtask, fired_signal_kinds)."""
        base = self._planner_base(mode, codebase, history, tools)
        entries = [e for e in read_entries(self.project_dir) if e.get("event") == "iteration"]
        subtask = self.backend.complete(PLANNER_SYSTEM, base).strip().splitlines()[0][:500]
        signals = detect_signals(subtask, entries, self.config.stuck_similarity)
        if not signals:
            return subtask, []
        nudge = STUCK_NUDGE.format(
            signals="\n".join(f"  - {s.kind}: {s.detail}" for s in signals))
        retry = self.backend.complete(PLANNER_SYSTEM, base + nudge).strip().splitlines()[0][:500]
        # keep the retry even if still similar — one nudge only; persistence is data
        return retry, [s.kind for s in signals]

    # -- auto-revert (v0.3) -------------------------------------------------------

    def _maybe_revert(self, iteration: int) -> None:
        """After N consecutive failures, restore src/tests/tools to the last
        green commit (history stays linear — restore + new commit, no reset).
        Repeated reverts to the same commit defer the failing task instead,
        so the loop can't ping-pong between revert and the same broken fix."""
        cfg = self.config
        if cfg.revert_after_failures <= 0:
            return
        entries = read_entries(self.project_dir)
        iters = [e for e in entries if e.get("event") == "iteration"]
        # a revert (or deferral) event resets the failure streak: only count
        # failures from that iteration onward, so we don't re-trigger every loop
        boundary = max((e.get("iteration", 0) for e in entries
                        if e.get("event") == "revert"), default=0)
        streak = []
        for e in reversed(iters):
            if e.get("validation_passed") or e.get("iteration", 0) < boundary:
                break
            streak.append(e)
        if len(streak) < cfg.revert_after_failures:
            return
        green = next((e for e in reversed(iters)
                      if e.get("validation_passed") and e.get("commit")), None)
        if green is None:
            return  # nothing green to go back to
        target = green["commit"]

        reverts_here = sum(1 for e in entries
                           if e.get("event") == "revert" and e.get("reverted_to") == target)
        if reverts_here >= MAX_REVERTS_TO_SAME_COMMIT:
            # reverting again won't help — defer the task being ground on instead
            task_id = next((e.get("task_id", 0) for e in streak if e.get("task_id")), 0)
            if not task_id:
                tl = load_tasks(self.project_dir)
                task_id = next((t.num for t in tl.tasks
                                if t.status == STATUS_IN_PROGRESS), 0)
            if task_id:
                mark_status(self.project_dir, task_id, STATUS_DEFERRED)
                print(f"[9xf]   revert limit hit — deferring task T{task_id} instead")
                append_entry(self.project_dir, LogEntry(
                    iteration=iteration, timestamp=now_iso(), subtask="",
                    summary=f"revert limit reached for {target}; deferred task T{task_id}",
                    event="revert", reverted_to="",
                ))
                if has_changes(self.project_dir):
                    commit_all(self.project_dir,
                               f"[iter {iteration}] deferred T{task_id} after repeated reverts")
            return

        first_bad = streak[-1]["iteration"]
        print(f"[9xf]   auto-revert: {len(streak)} consecutive failures — "
              f"restoring {'/'.join(WRITABLE_DIRS)} to {target}")
        restore_paths(self.project_dir, target, WRITABLE_DIRS)
        summary = (f"auto-revert to {target} after {len(streak)} consecutive failures "
                   f"(iterations {first_bad}–{streak[0]['iteration']} discarded)")
        if cfg.notes_enabled:
            append_notes(self.project_dir, iteration,
                         [f"HARNESS: reverted to {target}; the approach of iterations "
                          f"{first_bad}–{streak[0]['iteration']} failed — try differently"],
                         cfg.notes_max_lines)
        commit_hash = ""
        if has_changes(self.project_dir):
            commit_hash = commit_all(self.project_dir, f"[iter {iteration}] (revert) {summary}")
        append_entry(self.project_dir, LogEntry(
            iteration=iteration, timestamp=now_iso(), subtask="", summary=summary,
            commit=commit_hash, event="revert", reverted_to=target,
        ))

    # -- branch-and-explore (v0.3) -------------------------------------------------

    def _maybe_explore(self, iteration: int) -> LogEntry | None:
        """Hard-stuck: try two genuinely different approaches on git branches,
        validate both, adopt the winner on the main branch by file checkout.
        Returns the explore LogEntry (consuming this iteration) or None."""
        cfg = self.config
        if not cfg.explore_enabled:
            return None
        entries = read_entries(self.project_dir)
        if count_explores(entries) >= cfg.max_explores_per_run:
            return None
        if not should_explore(entries, cfg.explore_after_stuck):
            return None

        print(f"[9xf] iter {iteration} (explore) hard-stuck — trying two approaches on branches")
        write_state(self.project_dir, running=True, iteration=iteration, mode="explore",
                    subtask="(exploring two approaches)", ts=now_iso())
        prev_entries = [e for e in entries if e.get("event") == "iteration"]
        plan_query = " ".join(t.text for t in load_tasks(self.project_dir).open_tasks())
        codebase = snapshot_codebase(self.project_dir, cfg.context_char_budget,
                                     subtask=plan_query, entries=prev_entries,
                                     strategy=cfg.context_strategy)
        history = history_for_context(self.project_dir, cfg.history_entries_in_context)
        tools = tools_for_prompt(self.project_dir) if cfg.tools_enabled else "(tools disabled)"
        base = self._planner_base("build", codebase, history, tools)

        plan_a = self.backend.complete(
            PLANNER_SYSTEM, base + EXPLORE_NUDGE_A).strip().splitlines()[0][:500]
        plan_b = self.backend.complete(
            PLANNER_SYSTEM, base + EXPLORE_NUDGE_B.format(plan_a=plan_a)
        ).strip().splitlines()[0][:500]

        home = current_branch(self.project_dir)
        results: dict[str, dict] = {}
        for label, plan in (("a", plan_a), ("b", plan_b)):
            branch = f"explore-i{iteration}-{label}"
            create_branch(self.project_dir, branch)
            exec_codebase, _ = build_snapshot(
                self.project_dir, cfg.context_char_budget, subtask=plan,
                entries=prev_entries, strategy=cfg.context_strategy)
            notes = notes_for_prompt(self.project_dir) if cfg.notes_enabled else ""
            executor_user = EXECUTOR_USER.format(
                goal=self.goal, codebase=exec_codebase, subtask=plan, tools=tools,
                notes_section=NOTES_SECTION.format(notes=notes) if notes else "")
            ev = self._execute_once(iteration, plan, executor_user, None,
                                    log_violations=False)
            acc, _ = (run_acceptance(self.project_dir, cfg.validation_timeout,
                                     cfg.allow_network) if ev.written else (None, 0))
            if has_changes(self.project_dir):
                commit_all(self.project_dir, f"[iter {iteration}] (explore/{label}) {plan}")
            results[label] = {
                "plan": plan, "branch": branch, "summary": ev.parsed.summary,
                "passed": ev.validation_passed and not ev.errors,
                "acceptance_passed": acc, "tests_ran": ev.tests_ran,
                "errors_n": len(ev.errors),
            }
            print(f"[9xf]   approach {label.upper()}: "
                  f"{'ok' if results[label]['passed'] else 'FAILED'} — {plan[:80]}")
            checkout_branch(self.project_dir, home)

        def _key(r: dict) -> tuple:
            return (r["passed"], 1 if r["acceptance_passed"] else 0,
                    r["tests_ran"], -r["errors_n"])

        winner = "a" if _key(results["a"]) >= _key(results["b"]) else "b"
        loser = "b" if winner == "a" else "a"
        restore_paths(self.project_dir, results[winner]["branch"], WRITABLE_DIRS)
        rename_branch(self.project_dir, results[loser]["branch"],
                      results[loser]["branch"] + "-rejected")
        summary = (f"explore: adopted approach {winner.upper()} "
                   f"({results[winner]['plan'][:100]}) over {loser.upper()}")
        print(f"[9xf]   {summary}")
        if cfg.notes_enabled:
            append_notes(self.project_dir, iteration,
                         [f"HARNESS: explored two approaches; adopted {winner.upper()} "
                          f"({results[winner]['plan'][:100]})"], cfg.notes_max_lines)
        commit_hash = ""
        if has_changes(self.project_dir):
            commit_hash = commit_all(self.project_dir, f"[iter {iteration}] (explore) {summary}")
        entry = LogEntry(
            iteration=iteration, timestamp=now_iso(),
            subtask=results[winner]["plan"], summary=summary,
            validation_passed=results[winner]["passed"], commit=commit_hash,
            event="explore", mode="explore",
            explore={**results, "winner": winner},
        )
        append_entry(self.project_dir, entry)
        write_state(self.project_dir, running=True, iteration=iteration, mode="explore",
                    subtask=summary, validation_passed=results[winner]["passed"],
                    ts=now_iso())
        if has_changes(self.project_dir):
            commit_all(self.project_dir, f"[iter {iteration}] log entry")
        return entry

    # -- decomposition (v0.3) ---------------------------------------------------

    def _needs_decompose(self) -> bool:
        if not self.config.decompose_enabled:
            return False
        if tasks_path(self.project_dir).exists():
            return False
        # one attempt per run dir: a logged decompose event means we already
        # tried and fell back to v0.2 planning — don't retry forever
        return not any(e.get("event") == "decompose" for e in read_entries(self.project_dir))

    def _run_decompose(self, iteration: int) -> LogEntry:
        """One model call breaking the goal into TASKS.md + ACCEPTANCE.md."""
        print(f"[9xf] iter {iteration} (decompose) breaking the goal into tasks")
        write_state(self.project_dir, running=True, iteration=iteration, mode="decompose",
                    subtask="(decomposing goal)", ts=now_iso())
        raw = self.backend.complete(DECOMPOSE_SYSTEM, DECOMPOSE_USER.format(goal=self.goal))
        task_texts, criteria = parse_decomposition(raw)

        errors: list[str] = []
        if len(task_texts) < 2:
            # never die on a bad decomposition — fall back to v0.2 planning
            errors.append(f"decomposition produced only {len(task_texts)} task(s); "
                          "falling back to plain planning")
            summary = "decomposition failed; continuing without a task list"
        else:
            save_tasks(self.project_dir,
                       TaskList(tasks=[Task(num=i, text=t)
                                       for i, t in enumerate(task_texts, start=1)]))
            save_criteria(self.project_dir, criteria)
            summary = (f"decomposed goal into {len(task_texts)} tasks "
                       f"and {len(criteria)} acceptance criteria")
        print(f"[9xf]   {summary}")

        commit_hash = ""
        if has_changes(self.project_dir):
            commit_hash = commit_all(self.project_dir, f"[iter {iteration}] (decompose) {summary}")
        entry = LogEntry(
            iteration=iteration, timestamp=now_iso(), subtask="(decompose goal)",
            summary=summary, errors=errors, commit=commit_hash,
            event="decompose", mode="decompose",
            tasks_total=len(task_texts) if len(task_texts) >= 2 else 0,
        )
        append_entry(self.project_dir, entry)
        write_state(self.project_dir, running=True, iteration=iteration, mode="decompose",
                    subtask=summary, ts=now_iso())
        if has_changes(self.project_dir):
            commit_all(self.project_dir, f"[iter {iteration}] log entry")
        return entry

    # -- task bookkeeping (v0.3) ------------------------------------------------

    def _task_failures(self, task_id: int) -> int:
        return sum(1 for e in read_entries(self.project_dir)
                   if e.get("event") == "iteration" and e.get("task_id") == task_id
                   and not e.get("validation_passed"))

    def _check_task_done(self, task_id: int, errors: list[str]) -> bool:
        """One cheap YES/NO model call: is task Tn fully complete now?"""
        tl = load_tasks(self.project_dir)
        task = tl.get(task_id)
        if task is None:
            return False
        codebase = snapshot_codebase(self.project_dir, self.config.context_char_budget)
        try:
            reply = self.backend.complete(
                TASK_CHECK_SYSTEM,
                TASK_CHECK_USER.format(codebase=codebase, num=task.num, text=task.text),
            )
        except BackendError as e:
            errors.append(f"task-check call failed: {e}")
            return False
        first = reply.strip().splitlines()[0].strip().upper() if reply.strip() else ""
        return first.startswith("YES")

    # -- verify-done (v0.3) -------------------------------------------------------

    def _run_verify(self, iteration: int) -> LogEntry:
        """All tasks resolved: full-project validation + per-criterion verdicts.
        The model's PASS lines can only block finishing, never force it — the
        harness validation must also be green."""
        cfg = self.config
        print(f"[9xf] iter {iteration} (verify_done) checking acceptance criteria")
        write_state(self.project_dir, running=True, iteration=iteration, mode="verify_done",
                    subtask="(verifying goal completion)", ts=now_iso())

        all_files = [p for d in ("src", "tests", "tools")
                     for p in sorted((self.project_dir / d).rglob("*.py"))]
        result = validate(self.project_dir, all_files, cfg.validation_timeout,
                          cfg.allow_network, run_tests=cfg.run_tests)
        errors = list(result.errors)
        acc_passed, acc_ran = run_acceptance(self.project_dir, cfg.validation_timeout,
                                             cfg.allow_network)
        if acc_passed is False:
            errors.append(f"held-out acceptance suite failed ({acc_ran} tests)")

        criteria = load_criteria(self.project_dir)
        failed: dict[int, str] = {}
        if criteria:
            codebase = snapshot_codebase(self.project_dir, cfg.context_char_budget)
            validation_text = result.detail + (
                "; errors: " + "; ".join(result.errors) if result.errors else " (all green)")
            raw = self.backend.complete(
                VERIFY_DONE_SYSTEM,
                VERIFY_DONE_USER.format(goal=self.goal, codebase=codebase,
                                        validation=validation_text,
                                        criteria=criteria_for_prompt(self.project_dir)),
            )
            passed_nums, failed = parse_verify_output(raw)
            crit_texts = dict(criteria)
            # strict: a criterion with no verdict counts as failed
            for num in crit_texts:
                if num not in passed_nums and num not in failed:
                    failed[num] = "no verdict from model"

        harness_green = result.passed and acc_passed is not False
        if harness_green and not failed:
            summary = "goal complete: harness validation green and all acceptance criteria passed"
            event = "finished"
            self._finished = True
        else:
            event = "verify"
            corrective = []
            crit_texts = dict(criteria)
            for num, reason in sorted(failed.items()):
                text = crit_texts.get(num, f"criterion C{num}")
                corrective.append(f"Fix acceptance criterion C{num} ({text})"
                                  + (f": {reason}" if reason else ""))
            if not result.passed:
                corrective.append("Fix validation failures: " + "; ".join(result.errors)[:300])
            if acc_passed is False:
                corrective.append("Fix the failing held-out acceptance tests "
                                  "(run via the acceptance criteria — the suite itself is read-only)")
            append_tasks(self.project_dir, corrective)
            summary = (f"verify-done: {len(failed)} criteria failed, "
                       f"validation {'green' if result.passed else 'FAILED'}; "
                       f"added {len(corrective)} corrective task(s)")
        print(f"[9xf]   {summary}")

        tl = load_tasks(self.project_dir)
        done, total = tl.counts()
        commit_hash = ""
        if has_changes(self.project_dir):
            commit_hash = commit_all(self.project_dir, f"[iter {iteration}] (verify_done) {summary}")
        entry = LogEntry(
            iteration=iteration, timestamp=now_iso(), subtask="(verify goal completion)",
            summary=summary, validation_passed=result.passed,
            validation_detail=result.detail, errors=errors, commit=commit_hash,
            event=event, mode="verify_done", tests_ran=result.tests_ran,
            tasks_done=done, tasks_total=total,
            acceptance_passed=acc_passed, acceptance_ran=acc_ran,
        )
        append_entry(self.project_dir, entry)
        write_state(self.project_dir, running=True, iteration=iteration, mode="verify_done",
                    subtask=summary, validation_passed=result.passed, ts=now_iso())
        if has_changes(self.project_dir):
            commit_all(self.project_dir, f"[iter {iteration}] log entry")
        return entry

    # -- one executor attempt ----------------------------------------------------

    def _execute_once(self, iteration: int, subtask: str, executor_user: str,
                      temperature: float | None, log_violations: bool = True) -> ExecOutcome:
        """One executor call: complete -> parse -> write -> validate.
        log_violations=False during branch exploration, where appending log
        lines would diverge the JSONL across branches."""
        cfg = self.config
        raw = self.backend.complete(EXECUTOR_SYSTEM, executor_user, temperature=temperature)
        parsed = parse_executor_output(raw)
        outcome = ExecOutcome(parsed=parsed, errors=list(parsed.problems))
        for rel_path, content in parsed.files.items():
            try:
                outcome.written.append(safe_write(self.project_dir, rel_path, content))
            except ContainmentViolation as v:
                outcome.errors.append(str(v))
                if log_violations:
                    append_entry(self.project_dir, LogEntry(
                        iteration=iteration, timestamp=now_iso(), subtask=subtask,
                        summary=f"containment violation: {v.requested!r}", event="violation",
                    ))
        if outcome.written:
            result = validate(self.project_dir, outcome.written, cfg.validation_timeout,
                              cfg.allow_network, run_tests=cfg.run_tests)
            outcome.errors.extend(result.errors)
            outcome.validation_passed = result.passed
            outcome.validation_detail = result.detail
            outcome.tests_ran = result.tests_ran
        else:
            outcome.validation_detail = "nothing written"
        return outcome

    # -- one iteration ---------------------------------------------------------

    def run_iteration(self, iteration: int) -> LogEntry:
        cfg = self.config
        if self._needs_decompose():
            return self._run_decompose(iteration)
        self._maybe_revert(iteration)
        explored = self._maybe_explore(iteration)
        if explored is not None:
            return explored
        prev_entries = [e for e in read_entries(self.project_dir) if e.get("event") == "iteration"]
        prev_passed = bool(prev_entries and prev_entries[-1].get("validation_passed"))

        # planner snapshot: before a subtask exists, the relevance query is the
        # open tasks plus whatever the loop just worked on
        plan_query = " ".join(t.text for t in load_tasks(self.project_dir).open_tasks())
        if prev_entries:
            plan_query = f"{prev_entries[-1].get('subtask', '')} {plan_query}"
        codebase = snapshot_codebase(self.project_dir, cfg.context_char_budget,
                                     subtask=plan_query, entries=prev_entries,
                                     strategy=cfg.context_strategy)
        history = history_for_context(self.project_dir, cfg.history_entries_in_context)
        tools = tools_for_prompt(self.project_dir) if cfg.tools_enabled else "(tools disabled)"
        mode = self._pick_mode(iteration)
        if mode == "verify_done":
            return self._run_verify(iteration)

        # 1. self-generate the sub-task (with one anti-stuck retry)
        subtask, stuck_signals = self._plan(mode, codebase, history, tools)
        stuck_note = f", stuck: {'+'.join(stuck_signals)}" if stuck_signals else ""
        print(f"[9xf] iter {iteration} ({mode}{stuck_note}) subtask: {subtask}")
        write_state(self.project_dir, running=True, iteration=iteration, mode=mode,
                    subtask=subtask, ts=now_iso())

        # which TASKS.md task is this step targeting? (0 = none/unknown — drift is data)
        tl = load_tasks(self.project_dir)
        task_id = parse_task_ref(subtask, tl)
        if task_id and tl.get(task_id).open:
            mark_status(self.project_dir, task_id, STATUS_IN_PROGRESS)

        # 2. execute it — fresh snapshot scored against the actual subtask, and
        # record which files the executor actually saw (a key research observable)
        exec_codebase, context_files = build_snapshot(
            self.project_dir, cfg.context_char_budget, subtask=subtask,
            entries=prev_entries, strategy=cfg.context_strategy)
        notes = notes_for_prompt(self.project_dir) if cfg.notes_enabled else ""
        executor_user = EXECUTOR_USER.format(
            goal=self.goal, codebase=exec_codebase,
            subtask=strip_task_ref(subtask) if task_id else subtask,
            tools=tools,
            notes_section=NOTES_SECTION.format(notes=notes) if notes else "")

        # best-of-N: sample candidates at varied temperatures, validate each
        # (restoring the tree in between), keep the best — validator as judge
        n = best_of_n_active(cfg.best_of_n, cfg.best_of_mode, mode)
        candidates_log: list[dict] = []
        chosen = 0
        if n > 1:
            evals: list[tuple[ExecOutcome, CandidateResult]] = []
            for i in range(n):
                temp = CANDIDATE_TEMPERATURES[i % len(CANDIDATE_TEMPERATURES)]
                ev = self._execute_once(iteration, subtask, executor_user, temp)
                acc, _ = run_acceptance(self.project_dir, cfg.validation_timeout,
                                        cfg.allow_network) if ev.written else (None, 0)
                cr = CandidateResult(
                    index=i, temperature=temp, summary=ev.parsed.summary,
                    passed=ev.validation_passed and not ev.errors,
                    acceptance_passed=acc, tests_ran=ev.tests_ran,
                    errors_n=len(ev.errors), files_n=len(ev.written))
                evals.append((ev, cr))
                candidates_log.append(cr.as_log())
                print(f"[9xf]   candidate {i} (t={temp}): "
                      f"{'ok' if cr.passed else 'FAILED'} — {ev.parsed.summary[:80]}")
                restore_paths(self.project_dir, "HEAD", WRITABLE_DIRS)
            chosen = pick_winner([cr for _, cr in evals])
            outcome = evals[chosen][0]
            # re-write the winner (tree was restored after its evaluation);
            # its validation results are reused — same files, same verdict
            for rel_path, content in outcome.parsed.files.items():
                try:
                    safe_write(self.project_dir, rel_path, content)
                except ContainmentViolation:
                    pass  # already recorded during the candidate's evaluation
            print(f"[9xf]   chose candidate {chosen} of {n}")
        else:
            outcome = self._execute_once(iteration, subtask, executor_user, None)

        # critic pass: review the diff of a *passing* change before commit
        # (a failing change already has validation feedback)
        critic_verdict, critic_issues, critic_revised = "", [], False
        if (cfg.critic_enabled and outcome.validation_passed
                and not outcome.errors and outcome.written):
            diff = staged_diff(self.project_dir, WRITABLE_DIRS)[:CRITIC_DIFF_CHARS]
            raw_verdict = self.backend.complete(
                CRITIC_SYSTEM,
                CRITIC_USER.format(subtask=subtask, diff=diff,
                                   validation=outcome.validation_detail))
            critic_verdict, critic_issues = parse_critic_output(raw_verdict)
            if critic_verdict == "REVISE" and critic_issues and cfg.critic_max_revisions > 0:
                critic_revised = True
                print(f"[9xf]   critic: REVISE — {'; '.join(critic_issues)[:120]}")
                revise_user = executor_user + REVISE_NOTE.format(
                    issues="\n".join(f"- {i}" for i in critic_issues))
                # one revision on top of the first attempt; commit either way
                outcome = self._execute_once(iteration, subtask, revise_user, None)
            elif critic_verdict:
                print(f"[9xf]   critic: {critic_verdict}")

        parsed, written, errors = outcome.parsed, outcome.written, outcome.errors
        validation_passed = outcome.validation_passed
        validation_detail, tests_ran = outcome.validation_detail, outcome.tests_ran

        # 3. run requested tools (agent-created helper scripts; winner only)
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

        # 4. held-out acceptance suite (separate from validation — it gates
        # verify_done, not commits)
        acceptance_passed, acceptance_ran = (
            run_acceptance(self.project_dir, cfg.validation_timeout, cfg.allow_network)
            if written else (None, 0))

        failed = not validation_passed or bool(errors)
        regression = prev_passed and failed

        # task bookkeeping: only the harness marks a task done — green iteration
        # plus a YES from a one-line completion check. Repeated failures defer
        # the task so the loop stops grinding on it.
        if task_id:
            if not failed and self._check_task_done(task_id, errors):
                mark_status(self.project_dir, task_id, STATUS_DONE)
                print(f"[9xf]   task T{task_id} marked done")
            elif failed and self._task_failures(task_id) + 1 >= cfg.max_task_failures:
                mark_status(self.project_dir, task_id, STATUS_DEFERRED)
                errors.append(f"task T{task_id} deferred after "
                              f"{cfg.max_task_failures} failed attempts")
                print(f"[9xf]   task T{task_id} deferred")
                if cfg.notes_enabled:
                    append_notes(self.project_dir, iteration,
                                 [f"HARNESS: task T{task_id} deferred after "
                                  f"{cfg.max_task_failures} failed attempts"],
                                 cfg.notes_max_lines)
        tasks_done, tasks_total = load_tasks(self.project_dir).counts()

        # persist NOTE: lines (and harness observations) to NOTES.md before the
        # commit so the notes land in the same iteration commit
        notes_added: list[str] = []
        if cfg.notes_enabled:
            agent_notes = parsed.notes[: cfg.max_notes_per_iteration]
            if len(parsed.notes) > len(agent_notes):
                errors.append(f"{len(parsed.notes) - len(agent_notes)} note(s) dropped "
                              f"(cap {cfg.max_notes_per_iteration})")
            harness_notes = []
            if regression:
                harness_notes.append(
                    f"HARNESS: iteration {iteration} broke previously-working code "
                    f"({'; '.join(str(x) for x in errors)[:150]})")
            notes_added = append_notes(self.project_dir, iteration,
                                       agent_notes + harness_notes, cfg.notes_max_lines)

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
            stuck_detected=bool(stuck_signals),
            stuck_signals=stuck_signals,
            regression=regression,
            tests_ran=tests_ran,
            tool_runs=tool_runs,
            task_id=task_id,
            tasks_done=tasks_done,
            tasks_total=tasks_total,
            context_files=context_files,
            notes_added=notes_added,
            acceptance_passed=acceptance_passed,
            acceptance_ran=acceptance_ran,
            critic_verdict=critic_verdict,
            critic_issues=critic_issues,
            critic_revised=critic_revised,
            candidates=candidates_log,
            chosen_candidate=chosen,
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
                if entry.event == "iteration":
                    mark = "✓" if entry.validation_passed else "✗"
                else:
                    mark = "•"
                print(f"[9xf] iter {iteration} {mark} {entry.summary or '(no summary)'}"
                      f"  [{entry.commit or 'no commit'}]")
                if self._finished:
                    self._clean_shutdown(iteration, "goal complete")
                    return
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
