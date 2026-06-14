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

This module is the orchestrator. The per-concern behavior lives in mixins
(lifecycle, planning, recovery, decomposition, verification, execution,
reflection) that LoopRunner combines by inheritance — see loop_common.py for the
shared surface. The split is structural only; behavior is unchanged.
"""

from __future__ import annotations

from ninexf.loop_common import *  # noqa: F401,F403 - shared surface for the orchestrator
from ninexf.loop_common import _validation_tool_notice  # not pulled by `import *`
from ninexf.loop_decompose import DecomposeMixin
from ninexf.loop_execution import ExecutionMixin
from ninexf.loop_lifecycle import LifecycleMixin
from ninexf.loop_planning import PlanningMixin
from ninexf.loop_recovery import RecoveryMixin
from ninexf.loop_reflection import ReflectionMixin
from ninexf.loop_verify import VerifyMixin


class LoopRunner(
    LifecycleMixin,
    PlanningMixin,
    DecomposeMixin,
    RecoveryMixin,
    VerifyMixin,
    ExecutionMixin,
    ReflectionMixin,
):
    def __init__(self, project_dir: Path, config: Config):
        self.project_dir = project_dir
        self.config = config
        self.backend: Backend = make_backend(config)
        self.goal = (project_dir / GOAL_FILENAME).read_text().strip()
        self._interrupted = False
        self._finished = False  # set when verify_done declares the goal complete
        self._model_calls: list[dict] = []
        # One file cache for the whole run: context building re-scores the
        # codebase every iteration, but a file's read + AST parse only changes
        # when the file does. mtime-keyed, so git restores invalidate correctly.
        self._file_cache = FileCache()

    # -- one iteration ---------------------------------------------------------

    def run_iteration(self, iteration: int) -> LogEntry:
        self._reset_model_calls()
        cfg = self.config
        if self._needs_decompose():
            return self._run_decompose(iteration)
        self._maybe_revert(iteration)
        explored = self._maybe_explore(iteration)
        if explored is not None:
            return explored
        prev_entries = [e for e in read_entries(self.project_dir) if e.get("event") == "iteration"]
        prev_passed = bool(prev_entries and prev_entries[-1].get("validation_passed"))
        append_activity(self.project_dir, "building context snapshot",
                        iteration=iteration)

        # planner snapshot: before a subtask exists, the relevance query is the
        # open tasks plus whatever the loop just worked on
        plan_query = " ".join(t.text for t in load_tasks(self.project_dir).open_tasks())
        if prev_entries:
            plan_query = f"{prev_entries[-1].get('subtask', '')} {plan_query}"
        codebase = snapshot_codebase(self.project_dir, cfg.snapshot_budget,
                                     subtask=plan_query, entries=prev_entries,
                                     strategy=cfg.context_strategy, cache=self._file_cache)
        history = history_for_context(self.project_dir, cfg.history_entries_in_context)
        tools = tools_for_prompt(self.project_dir) if cfg.tools_enabled else "(tools disabled)"
        mode = self._pick_mode(iteration)
        if mode == "verify_done":
            return self._run_verify(iteration)

        # 1. self-generate the sub-task (with one anti-stuck retry)
        append_activity(self.project_dir, "asking planner for next step",
                        iteration=iteration, kind="model")
        subtask, stuck_signals = self._plan(mode, codebase, history, tools)
        stuck_note = f", stuck: {'+'.join(stuck_signals)}" if stuck_signals else ""
        logger.info(f"[9xf] iter {iteration} ({mode}{stuck_note}) subtask: {subtask}")
        write_state(self.project_dir, running=True, iteration=iteration, mode=mode,
                    subtask=subtask, ts=now_iso())
        append_activity(self.project_dir, f"selected next step: {subtask[:160]}",
                        iteration=iteration, kind="plan")

        # which TASKS.md task(s) is this step targeting? (task_id keeps the
        # first target for backward-compatible logs)
        tl = load_tasks(self.project_dir)
        task_ids = parse_task_refs(subtask, tl, cfg.control_mode)
        task_id = task_ids[0] if task_ids else 0
        for tid in task_ids:
            task = tl.get(tid)
            if task and task.open:
                mark_status(self.project_dir, tid, STATUS_IN_PROGRESS)

        # 2. execute it — fresh snapshot scored against the actual subtask, and
        # record which files the executor actually saw (a key research observable)
        exec_codebase, context_files = build_snapshot(
            self.project_dir, cfg.snapshot_budget, subtask=subtask,
            entries=prev_entries, strategy=cfg.context_strategy, cache=self._file_cache)
        notes = notes_for_prompt(self.project_dir) if cfg.notes_enabled else ""
        contract = contract_for_prompt(self.project_dir)
        contract_section = CONTRACT_SECTION.format(contract=contract) if contract else ""
        executor_user = EXECUTOR_USER.format(
            goal=self.goal, codebase=exec_codebase,
            subtask=strip_task_ref(subtask) if task_id else subtask,
            tools=tools,
            contract_section=contract_section,
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
                ev = self._execute_once(iteration, subtask, executor_user, temp,
                                        purpose=f"candidate_{i}")
                acc, _ = run_acceptance(self.project_dir, cfg.validation_timeout,
                                        cfg.allow_network) if ev.written else (None, 0)
                cr = CandidateResult(
                    index=i, temperature=temp, summary=ev.parsed.summary,
                    passed=ev.validation_passed and not ev.errors,
                    acceptance_passed=acc, tests_ran=ev.tests_ran,
                    errors_n=len(ev.errors), files_n=len(ev.written))
                evals.append((ev, cr))
                candidates_log.append(cr.as_log())
                logger.info(f"[9xf]   candidate {i} (t={temp}): "
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
            logger.info(f"[9xf]   chose candidate {chosen} of {n}")
        else:
            outcome = self._execute_once(iteration, subtask, executor_user, None)

        # in-iteration repair: a failing attempt (including a failing best-of-N
        # winner) gets its errors fed straight back instead of waiting a full
        # re-plan round trip
        repairs: list[dict] = []
        diagnosis = ""
        if cfg.repair_attempts > 0 and (not outcome.validation_passed or outcome.errors):
            if self._should_diagnose(outcome):
                append_activity(self.project_dir, "diagnosing repeated failure before repair",
                                iteration=iteration, kind="diagnosis")
                diagnosis = self._diagnose(subtask, outcome, exec_codebase, history)
                executor_user += "\n\nDIAGNOSIS BEFORE REPAIR:\n" + diagnosis + "\n"
            outcome, repairs = self._repair_loop(iteration, subtask, executor_user, outcome)

        # critic pass: review the diff of a *passing* change before commit
        # (a failing change already has validation feedback)
        critic_verdict, critic_issues, critic_revised = "", [], False
        if (cfg.critic_enabled and outcome.validation_passed
                and not outcome.errors and outcome.written):
            diff = staged_diff(self.project_dir, WRITABLE_DIRS)[:CRITIC_DIFF_CHARS]
            raw_verdict = self._complete(
                "critic",
                CRITIC_SYSTEM,
                CRITIC_USER.format(subtask=subtask, diff=diff,
                                   validation=outcome.validation_detail))
            critic_verdict, critic_issues = parse_critic_output(raw_verdict)
            if critic_verdict == "REVISE" and critic_issues and cfg.critic_max_revisions > 0:
                critic_revised = True
                logger.info(f"[9xf]   critic: REVISE — {'; '.join(critic_issues)[:120]}")
                revise_user = executor_user + REVISE_NOTE.format(
                    issues="\n".join(f"- {i}" for i in critic_issues))
                # one revision on top of the first attempt; commit either way
                outcome = self._execute_once(iteration, subtask, revise_user, None,
                                             purpose="critic_revision")
            elif critic_verdict:
                logger.info(f"[9xf]   critic: {critic_verdict}")

        parsed, written, errors = outcome.parsed, outcome.written, outcome.errors
        validation_passed = outcome.validation_passed
        validation_detail, tests_ran = outcome.validation_detail, outcome.tests_ran

        # 3. run requested tools (agent-created helper scripts; winner only)
        tool_runs = []
        if cfg.tools_enabled:
            dropped = 0
            for name, args in parsed.tool_runs[: cfg.max_tool_runs_per_iteration]:
                append_activity(self.project_dir, f"running tool {name} {args}".strip(),
                                iteration=iteration, kind="tool")
                notice = _validation_tool_notice(name, args)
                if notice:
                    tool_runs.append({"name": name, "args": args, "result": notice})
                    append_activity(self.project_dir, f"ignored RUN_TOOL {name}: validation handles it",
                                    iteration=iteration, kind="tool")
                    logger.info(f"[9xf]   tool {name} {args}: {notice[:120]}")
                    continue
                result = run_tool(self.project_dir, name, args,
                                  cfg.validation_timeout, cfg.allow_network)
                tool_runs.append({"name": name, "args": args, "result": result})
                logger.info(f"[9xf]   tool {name} {args}: {result[:120]}")
                if result.startswith(f"tool {name!r} not found"):
                    msg = f"unknown tool requested: {name!r}; available tools: {tools}"
                    errors.append(msg)
                    validation_passed = False
                    if not outcome.failure_kind:
                        outcome.failure_kind = "tool"
                        outcome.error_signature = msg.lower()[:300]
                        outcome.error_excerpt = msg
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
        files_written_rel = [str(p.relative_to(self.project_dir)) for p in written]

        # task bookkeeping: strict mode preserves the old single-task gate.
        # Hybrid mode checks every open task evidenced by the written files so
        # a coherent multi-file slice can complete multiple adjacent tasks.
        if task_id:
            if not failed:
                done_candidates = list(task_ids)
                if cfg.control_mode in {"hybrid", "freeform"}:
                    for tid in infer_task_ids_for_files(load_tasks(self.project_dir), files_written_rel):
                        if tid not in done_candidates:
                            done_candidates.append(tid)
                current_tasks = load_tasks(self.project_dir)
                for tid in done_candidates:
                    if not task_has_file_evidence(current_tasks.get(tid), files_written_rel, subtask):
                        continue
                    if self._check_task_done(tid, errors):
                        mark_status(self.project_dir, tid, STATUS_DONE)
                        logger.info(f"[9xf]   task T{tid} marked done")
            elif (cfg.control_mode == "strict"
                  and self._task_failures(task_id) + 1 >= cfg.max_task_failures):
                mark_status(self.project_dir, task_id, STATUS_DEFERRED)
                errors.append(f"task T{task_id} deferred after "
                              f"{cfg.max_task_failures} failed attempts")
                logger.info(f"[9xf]   task T{task_id} deferred")
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
            reflection_notes: list[str] = []
            if self._reflection_due(
                iteration,
                failed=failed,
                regression=regression,
                stuck_signals=stuck_signals,
                parse_warnings=outcome.parse_warnings,
                critic_verdict=critic_verdict,
            ):
                reflection_notes = self._reflect(
                    iteration,
                    mode=mode,
                    subtask=subtask,
                    outcome=outcome,
                    files_written=files_written_rel,
                    validation_passed=validation_passed,
                    errors=errors,
                    regression=regression,
                    stuck_signals=stuck_signals,
                    critic_verdict=critic_verdict,
                    diagnosis=diagnosis,
                    codebase=exec_codebase,
                    history=history,
                )
            notes_added = append_notes(
                self.project_dir, iteration, agent_notes + harness_notes,
                cfg.notes_max_lines)
            notes_added += append_notes(
                self.project_dir, iteration, reflection_notes,
                cfg.notes_max_lines, source="reflection")

        # 5. commit (failed attempts included — research data)
        status = "failed" if failed else "ok"
        commit_msg = f"[iter {iteration}] ({mode}/{status}) {subtask}\n\n{parsed.summary}"
        commit_hash = ""
        if has_changes(self.project_dir):
            append_activity(self.project_dir, "committing iteration result",
                            iteration=iteration, kind="git")
            commit_hash = commit_all(self.project_dir, commit_msg)

        entry = LogEntry(
            iteration=iteration,
            timestamp=now_iso(),
            subtask=subtask,
            summary=parsed.summary,
            files_written=files_written_rel,
            validation_passed=validation_passed,
            validation_detail=validation_detail,
            errors=errors,
            validation_warnings=outcome.validation_warnings,
            parse_warnings=outcome.parse_warnings,
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
            repairs=repairs,
            model_calls=self._take_model_calls(),
            context_overflow=self.backend.take_overflow(),
            failure_kind=outcome.failure_kind,
            error_signature=outcome.error_signature,
            error_excerpt=outcome.error_excerpt,
            diagnosis=diagnosis,
        )
        append_entry(self.project_dir, entry)
        write_state(self.project_dir, running=True, iteration=iteration, mode=mode,
                    subtask=subtask, validation_passed=validation_passed, ts=now_iso())

        # commit the log line itself so git history and log stay in lockstep
        if has_changes(self.project_dir):
            append_activity(self.project_dir, "committing loop log entry",
                            iteration=iteration, kind="git")
            commit_all(self.project_dir, f"[iter {iteration}] log entry")
        return entry

    # -- the loop ----------------------------------------------------------------

    def run(self, max_iterations: int | None = None, delay: float | None = None,
            hours: float | None = None):
        cfg = self.config
        cap = max_iterations if max_iterations is not None else cfg.max_iterations
        sleep_s = delay if delay is not None else cfg.delay_seconds
        budget_h = hours if hours is not None else cfg.max_hours
        deadline = time.monotonic() + budget_h * 3600 if budget_h and budget_h > 0 else None
        self._install_sigint()

        start = last_iteration_number(self.project_dir)
        append_entry(self.project_dir, LogEntry(
            iteration=start, timestamp=now_iso(), subtask="",
            summary=f"run started (model={cfg.model}, cap={cap}, delay={sleep_s}s"
                    + (f", time budget {budget_h}h" if deadline else "") + ")",
            event="startup",
        ))
        write_state(self.project_dir, running=True, iteration=start, ts=now_iso())
        append_activity(self.project_dir, f"run started with {cfg.model}",
                        iteration=start, kind="startup")
        logger.info(f"[9xf] goal: {self.goal}")
        logger.info(f"[9xf] model: {cfg.model} | starting at iteration {start + 1}, cap {cap}"
              + (f" | time budget {budget_h}h" if deadline else ""))

        backend_failures = 0
        iteration = start
        while iteration - start < cap:
            reason = self._stop_requested()
            if reason:
                self._clean_shutdown(iteration, reason)
                return
            if deadline is not None and time.monotonic() >= deadline:
                self._clean_shutdown(iteration, f"time budget reached ({budget_h}h)")
                return

            iteration += 1
            try:
                entry = self.run_iteration(iteration)
                backend_failures = 0
                if entry.event == "iteration":
                    mark = "✓" if entry.validation_passed else "✗"
                else:
                    mark = "•"
                logger.info(f"[9xf] iter {iteration} {mark} {entry.summary or '(no summary)'}"
                      f"  [{entry.commit or 'no commit'}]")
                if self._finished:
                    self._clean_shutdown(iteration, "goal complete")
                    return
            except BackendError as e:
                backend_failures += 1
                if getattr(e, "retryable", True):
                    logger.info(f"[9xf] iter {iteration} backend error ({backend_failures}/"
                          f"{MAX_CONSECUTIVE_BACKEND_FAILURES}): {e}")
                else:
                    logger.info(f"[9xf] iter {iteration} non-retryable backend error: {e}")
                append_activity(self.project_dir, f"backend error: {e}",
                                iteration=iteration, kind="error")
                append_entry(self.project_dir, LogEntry(
                    iteration=iteration, timestamp=now_iso(), subtask="",
                    summary="backend error", errors=[str(e)], validation_passed=False,
                    event="backend_error", mode="backend_error",
                    model_calls=self._take_model_calls(),
                    context_overflow=self.backend.take_overflow(),
                ))
                write_state(self.project_dir, running=True, iteration=iteration,
                            mode="backend_error", subtask=f"backend error: {e}",
                            validation_passed=False, ts=now_iso())
                if not getattr(e, "retryable", True):
                    self._clean_shutdown(iteration, "non-retryable backend failure")
                    return
                if backend_failures >= MAX_CONSECUTIVE_BACKEND_FAILURES:
                    self._clean_shutdown(iteration, "too many consecutive backend failures")
                    return

            reason = self._stop_requested()
            if reason:
                self._clean_shutdown(iteration, reason)
                return
            if iteration - start < cap:
                pause = sleep_s
                if deadline is not None:
                    pause = min(pause, max(0.0, deadline - time.monotonic()))
                time.sleep(pause)

        self._clean_shutdown(iteration, f"iteration cap reached ({cap})")
