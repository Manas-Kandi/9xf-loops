"""ExecutionMixin: one executor attempt, failure diagnosis, and the repair loop."""

from __future__ import annotations

from ninexf.loop_common import *  # noqa: F401,F403 - shared LoopRunner surface
from ninexf.loop_common import (  # underscore helpers aren't pulled by `import *`
    _fatal_parse_problems, _parse_warnings, _repair_file_dump,
)


class ExecutionMixin:
    def _execute_once(self, iteration: int, subtask: str, executor_user: str,
                      temperature: float | None, log_violations: bool = True,
                      purpose: str = "executor") -> ExecOutcome:
        """One executor call: complete -> parse -> write -> validate.
        log_violations=False during branch exploration, where appending log
        lines would diverge the JSONL across branches."""
        cfg = self.config
        append_activity(self.project_dir, "asking model to write code",
                        iteration=iteration, kind="model")
        raw = self._complete(purpose, EXECUTOR_SYSTEM, executor_user, temperature=temperature)
        parsed = parse_executor_output(raw)
        for attempt in range(max(0, cfg.format_retry_attempts)):
            fatal = _fatal_parse_problems(parsed)
            if not fatal:
                break
            append_activity(self.project_dir,
                            f"format retry {attempt + 1}: executor output was not parseable",
                            iteration=iteration, kind="repair")
            retry_user = executor_user + FORMAT_RETRY_NOTE.format(
                problems="\n".join(f"- {p}" for p in parsed.problems)[:1200])
            raw = self._complete(f"{purpose}_format_retry", EXECUTOR_SYSTEM,
                                 retry_user, temperature=temperature)
            parsed = parse_executor_output(raw)
        if not parsed.summary and parsed.files:
            names = ", ".join(list(parsed.files)[:3])
            parsed.summary = f"updated {names}"
        outcome = ExecOutcome(
            parsed=parsed,
            errors=_fatal_parse_problems(parsed),
            parse_warnings=_parse_warnings(parsed),
        )
        if parsed.files:
            append_activity(self.project_dir,
                            f"model proposed {len(parsed.files)} file write(s)",
                            iteration=iteration)
        for rel_path, content in parsed.files.items():
            try:
                append_activity(self.project_dir, f"writing {rel_path}",
                                iteration=iteration, kind="write")
                outcome.written.append(safe_write(self.project_dir, rel_path, content))
            except ContainmentViolation as v:
                outcome.errors.append(str(v))
                append_activity(self.project_dir, f"rejected write to {v.requested}",
                                iteration=iteration, kind="error")
                if log_violations:
                    append_entry(self.project_dir, LogEntry(
                        iteration=iteration, timestamp=now_iso(), subtask=subtask,
                        summary=f"containment violation: {v.requested!r}", event="violation",
                    ))
        if outcome.written:
            append_activity(self.project_dir,
                            f"validating {len(outcome.written)} written file(s)",
                            iteration=iteration, kind="validate")
            phase = "final" if cfg.control_mode == "strict" else "build"
            result = validate(self.project_dir, outcome.written, cfg.validation_timeout,
                              cfg.allow_network, run_tests=cfg.run_tests, phase=phase)
            outcome.errors.extend(result.errors)
            outcome.validation_warnings.extend(result.warnings)
            outcome.validation_passed = result.passed
            outcome.validation_detail = result.detail
            outcome.tests_ran = result.tests_ran
            outcome.failure_kind = result.failure_kind
            outcome.error_signature = result.error_signature
            outcome.error_excerpt = result.error_excerpt
            append_activity(self.project_dir,
                            "validation passed" if result.passed else
                            f"validation failed: {result.failure_kind or 'error'}",
                            iteration=iteration,
                            kind="validate" if result.passed else "error")
            for warning in result.warnings[:3]:
                append_activity(self.project_dir, f"validation warning: {warning[:140]}",
                                iteration=iteration, kind="warning")
        else:
            outcome.validation_detail = "nothing written"
            if outcome.errors:
                outcome.failure_kind = "parse"
                outcome.error_signature = outcome.errors[0].lower()[:300]
                outcome.error_excerpt = outcome.errors[0]
        return outcome

    def _should_diagnose(self, outcome: ExecOutcome) -> bool:
        if not outcome.errors:
            return False
        if outcome.failure_kind in {"timeout", "slow_test"}:
            return True
        sig = outcome.error_signature
        if not sig:
            return False
        recent = [e for e in read_entries(self.project_dir)
                  if e.get("event") == "iteration" and not e.get("validation_passed")]
        return any(e.get("error_signature") == sig for e in recent[-2:])

    def _diagnose(self, subtask: str, outcome: ExecOutcome,
                  codebase: str, history: str) -> str:
        evidence = "\n".join(outcome.errors[:3])
        if outcome.error_excerpt and outcome.error_excerpt not in evidence:
            evidence += "\n\n" + outcome.error_excerpt
        contract = contract_for_prompt(self.project_dir) or "(none)"
        try:
            return self._complete(
                "diagnosis",
                DIAGNOSIS_SYSTEM,
                DIAGNOSIS_USER.format(
                    goal=self.goal, codebase=codebase, history=history,
                    contract=contract, subtask=subtask, errors=evidence[:5000],
                ),
            ).strip()[:2000]
        except BackendError:
            raise
        except Exception as e:
            return f"CAUSE: diagnosis failed: {e}\nPATCH_PLAN: use validation evidence directly"

    # -- in-iteration repair (overnight) -----------------------------------------

    def _repair_loop(self, iteration: int, subtask: str, executor_user: str,
                     outcome: ExecOutcome) -> tuple[ExecOutcome, list[dict]]:
        """Failed validation gets fixed NOW, not next iteration: re-prompt the
        executor with the broken file contents and the exact errors, up to
        repair_attempts times. A whole-iteration round trip (re-plan, re-snapshot)
        costs minutes on a local model; a repair call costs seconds and targets
        the precise failure — the highest-leverage trade of time for quality."""
        repairs: list[dict] = []
        attempt = 0
        while (attempt < self.config.repair_attempts
               and (not outcome.validation_passed or outcome.errors)):
            attempt += 1
            append_activity(self.project_dir, f"repair attempt {attempt}",
                            iteration=iteration, kind="repair")
            dump = _repair_file_dump(self.project_dir, outcome, REPAIR_FILES_CHARS)
            errors = "\n".join(str(e) for e in outcome.errors)
            if outcome.error_excerpt and outcome.error_excerpt not in errors:
                errors += "\n\n" + outcome.error_excerpt
            errors = errors[:3500] or "(none recorded)"
            repair_user = executor_user + REPAIR_NOTE.format(files=dump, errors=errors)
            new = self._execute_once(iteration, subtask, repair_user, None, purpose="repair")
            if new.written:
                touched = []
                for path in outcome.written + new.written:
                    if path not in touched:
                        touched.append(path)
                phase = "final" if self.config.control_mode == "strict" else "build"
                result = validate(self.project_dir, touched, self.config.validation_timeout,
                                  self.config.allow_network,
                                  run_tests=self.config.run_tests, phase=phase)
                new.validation_passed = result.passed
                new.validation_detail = result.detail
                new.tests_ran = result.tests_ran
                new.failure_kind = result.failure_kind
                new.error_signature = result.error_signature
                new.error_excerpt = result.error_excerpt
                new.validation_warnings = result.warnings
                new.errors = list(result.errors)
                new.written = touched
            repairs.append({
                "attempt": attempt,
                "errors_before": [str(e)[:200] for e in outcome.errors][:5],
                "passed": new.validation_passed and not new.errors,
            })
            logger.info(f"[9xf]   repair {attempt}/{self.config.repair_attempts}: "
                  f"{'ok' if repairs[-1]['passed'] else 'still failing'}"
                  f" — {new.parsed.summary[:80]}")
            if not new.written and not new.parsed.files:
                break  # repair produced nothing usable; keep what we have
            outcome = new
        return outcome, repairs
