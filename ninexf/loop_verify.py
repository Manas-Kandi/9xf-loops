"""VerifyMixin: task-completion bookkeeping and the verify_done finish check."""

from __future__ import annotations

from ninexf.loop_common import *  # noqa: F401,F403 - shared LoopRunner surface


class VerifyMixin:
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
        codebase = snapshot_codebase(self.project_dir, self.config.snapshot_budget,
                                     cache=self._file_cache)
        contract = contract_for_prompt(self.project_dir) or "(none)"
        try:
            reply = self._complete(
                "task_check",
                TASK_CHECK_SYSTEM,
                TASK_CHECK_USER.format(codebase=codebase, contract=contract,
                                       num=task.num, text=task.text),
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
        logger.info(f"[9xf] iter {iteration} (verify_done) checking acceptance criteria")
        write_state(self.project_dir, running=True, iteration=iteration, mode="verify_done",
                    subtask="(verifying goal completion)", ts=now_iso())

        all_files = [p for d in ("src", "tests", "tools")
                     for p in sorted((self.project_dir / d).rglob("*")) if p.is_file()]
        result = validate(self.project_dir, all_files, cfg.validation_timeout,
                          cfg.allow_network, run_tests=cfg.run_tests, phase="final")
        errors = list(result.errors)
        acc_passed, acc_ran = run_acceptance(self.project_dir, cfg.validation_timeout,
                                             cfg.allow_network)
        if acc_passed is False:
            errors.append(f"held-out acceptance suite failed ({acc_ran} tests)")

        harness_green = result.passed and acc_passed is not False
        criteria = load_criteria(self.project_dir)
        failed: dict[int, str] = {}
        if harness_green and criteria:
            codebase = snapshot_codebase(self.project_dir, cfg.snapshot_budget,
                                         cache=self._file_cache)
            validation_text = result.detail + (
                "; errors: " + "; ".join(result.errors) if result.errors else " (all green)")
            raw = self._complete(
                "verify_done",
                VERIFY_DONE_SYSTEM,
                VERIFY_DONE_USER.format(goal=self.goal, codebase=codebase,
                                        contract=contract_for_prompt(self.project_dir) or "(none)",
                                        validation=validation_text,
                                        criteria=criteria_for_prompt(self.project_dir)),
            )
            passed_nums, failed = parse_verify_output(raw)
            crit_texts = dict(criteria)
            # strict: a criterion with no verdict counts as failed
            for num in crit_texts:
                if num not in passed_nums and num not in failed:
                    failed[num] = "no verdict from model"

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
            if harness_green:
                summary = (f"verify-done: {len(failed)} criteria failed, "
                           "validation green; "
                           f"added {len(corrective)} corrective task(s)")
            else:
                summary = (f"verify-done: validation "
                           f"{'green' if result.passed else 'FAILED'}; "
                           f"added {len(corrective)} corrective task(s)")
        logger.info(f"[9xf]   {summary}")

        tl = load_tasks(self.project_dir)
        done, total = tl.counts()
        commit_hash = ""
        if has_changes(self.project_dir):
            commit_hash = commit_all(self.project_dir, f"[iter {iteration}] (verify_done) {summary}")
        entry = LogEntry(
            iteration=iteration, timestamp=now_iso(), subtask="(verify goal completion)",
            summary=summary, validation_passed=result.passed,
            validation_detail=result.detail, errors=errors, commit=commit_hash,
            validation_warnings=result.warnings,
            event=event, mode="verify_done", tests_ran=result.tests_ran,
            tasks_done=done, tasks_total=total,
            acceptance_passed=acc_passed, acceptance_ran=acc_ran,
            failure_kind=result.failure_kind,
            error_signature=result.error_signature,
            error_excerpt=result.error_excerpt,
            model_calls=self._take_model_calls(),
            context_overflow=self.backend.take_overflow(),
        )
        append_entry(self.project_dir, entry)
        write_state(self.project_dir, running=True, iteration=iteration, mode="verify_done",
                    subtask=summary, validation_passed=result.passed, ts=now_iso())
        if has_changes(self.project_dir):
            commit_all(self.project_dir, f"[iter {iteration}] log entry")
        return entry
