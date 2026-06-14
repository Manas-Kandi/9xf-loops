"""PlanningMixin: mode scheduling, sub-task generation, and task-reference guardrails."""

from __future__ import annotations

from ninexf.loop_common import *  # noqa: F401,F403 - shared LoopRunner surface


class PlanningMixin:
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
        tasks = tasks_for_prompt(self.project_dir, self.config.control_mode)
        tasks_section = TASKS_SECTION.format(tasks=tasks) if tasks else ""
        contract = contract_for_prompt(self.project_dir)
        contract_section = CONTRACT_SECTION.format(contract=contract) if contract else ""
        notes = notes_for_prompt(self.project_dir) if self.config.notes_enabled else ""
        notes_section = NOTES_SECTION.format(notes=notes) if notes else ""
        entries = [e for e in read_entries(self.project_dir) if e.get("event") == "iteration"]
        last_commit = entries[-1].get("commit", "") if entries else ""
        changes = changes_since_last(self.project_dir, last_commit, self.config.diff_char_budget)
        changes_section = CHANGES_SECTION.format(changes=changes) if changes else ""
        return PLANNER_USER.format(
            goal=self.goal, codebase=codebase, history=history,
            tools=tools, mode_instructions=mode_instructions,
            contract_section=contract_section,
            tasks_section=tasks_section, notes_section=notes_section,
            changes_section=changes_section,
        )

    def _plan(self, mode: str, codebase: str, history: str, tools: str) -> tuple[str, list[str]]:
        """Generate the sub-task; if stuck signals fire, re-ask once with a
        signal-specific nudge. Returns (subtask, fired_signal_kinds)."""
        base = self._planner_base(mode, codebase, history, tools)
        entries = [e for e in read_entries(self.project_dir) if e.get("event") == "iteration"]
        subtask = self._complete("planner", PLANNER_SYSTEM, base).strip().splitlines()[0][:500]
        signals = detect_signals(subtask, entries, self.config.stuck_similarity)
        if not signals:
            return self._ensure_eligible_plan(base, subtask), []
        nudge = STUCK_NUDGE.format(
            signals="\n".join(f"  - {s.kind}: {s.detail}" for s in signals))
        retry = self._complete(
            "planner_stuck_retry", PLANNER_SYSTEM, base + nudge,
        ).strip().splitlines()[0][:500]
        # keep the retry even if still similar — one nudge only; persistence is data
        return self._ensure_eligible_plan(base, retry), [s.kind for s in signals]

    def _task_ref_problem(self, subtask: str) -> str:
        if self.config.control_mode == "freeform":
            return ""
        tl = load_tasks(self.project_dir)
        if not tl.tasks:
            return ""
        open_tasks = tl.open_tasks()
        if not open_tasks:
            return ""
        eligible = tl.eligible_task()
        num = parse_task_ref_num(subtask)
        if not num:
            if self.config.control_mode == "hybrid":
                return ""
            return f"planner did not name the eligible task T{eligible.num}" if eligible else ""
        task = tl.get(num)
        if task is None:
            return f"T{num} is not in TASKS.md"
        if self.config.control_mode == "hybrid":
            return "" if task.open else f"T{num} is deferred or already resolved"
        if not eligible or task.num != eligible.num:
            if not task.open:
                return f"T{num} is deferred or already resolved"
            return f"T{num} is queued; the eligible next task is T{eligible.num}"
        return ""

    def _ensure_eligible_plan(self, base: str, subtask: str) -> str:
        """Planner guardrail: don't execute unknown/deferred task references."""
        problem = self._task_ref_problem(subtask)
        if not problem:
            return subtask
        retry = self._complete(
            "planner_task_retry",
            PLANNER_SYSTEM,
            base + TASK_ELIGIBILITY_NUDGE.format(reason=problem),
        ).strip().splitlines()[0][:500]
        if not self._task_ref_problem(retry):
            return retry
        tl = load_tasks(self.project_dir)
        open_tasks = tl.open_tasks()
        if open_tasks:
            t = tl.eligible_task() or open_tasks[0]
            if not parse_task_ref_num(retry):
                instruction = strip_task_ref(retry or subtask)
                return f"TASK T{t.num}: {instruction}"
            return f"TASK T{t.num}: {t.text}"
        return retry
