"""LifecycleMixin: the model-call wrapper, signal handling, and shutdown paths."""

from __future__ import annotations

from ninexf.loop_common import *  # noqa: F401,F403 - shared LoopRunner surface


class LifecycleMixin:
    def _max_tokens_for_purpose(self, purpose: str) -> int | None:
        cap = max(1, int(self.config.max_tokens))
        compact = {
            "decompose": min(cap, 2048),
            "decompose_retry": min(cap, 2048),
            "planner": min(cap, 768),
            "planner_stuck_retry": min(cap, 768),
            "planner_task_retry": min(cap, 768),
            "task_check": min(cap, 512),
            "verify_done": min(cap, 1536),
            "reflection": min(cap, 768),
            "diagnosis": min(cap, 1024),
            "critic": min(cap, 1024),
        }
        if purpose.startswith("candidate_"):
            return min(cap, 8192)
        if purpose in {"executor", "repair", "critic_revision"}:
            return min(cap, 8192)
        return compact.get(purpose)

    def _reset_model_calls(self) -> None:
        self._model_calls = []

    def _take_model_calls(self) -> list[dict]:
        calls = self._model_calls
        self._model_calls = []
        return calls

    def _complete(
        self,
        purpose: str,
        system: str,
        user: str,
        temperature: float | None = None,
    ) -> str:
        """Model-call wrapper that records backend cost and failure evidence."""
        started = time.perf_counter()
        max_tokens = self._max_tokens_for_purpose(purpose)
        record = {
            "purpose": purpose,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "prompt_chars": len(system) + len(user),
            "response_chars": 0,
            "latency_s": 0.0,
            "ok": False,
            "error": "",
        }
        try:
            state = read_state(self.project_dir)
            write_state(
                self.project_dir,
                running=True,
                iteration=int(state.get("iteration", 0) or 0),
                mode=state.get("mode", "model") or "model",
                subtask=(
                    f"waiting for model: {purpose} "
                    f"(timeout {self.config.backend_timeout:g}s"
                    + (f", max_tokens {max_tokens}" if max_tokens else "")
                    + ")"
                ),
                ts=now_iso(),
            )
        except Exception:
            pass
        try:
            response = self.backend.complete(
                system,
                user,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            record["response_chars"] = len(response)
            record["ok"] = True
            return response
        except BackendError as e:
            record["error"] = str(e)[:500]
            raise
        finally:
            record["latency_s"] = round(time.perf_counter() - started, 3)
            self._model_calls.append(record)

    # -- shutdown plumbing ----------------------------------------------------

    def _install_sigint(self):
        def handler(signum, frame):
            if self._interrupted:  # second Ctrl+C: give up politely
                raise KeyboardInterrupt
            self._interrupted = True
            logger.info("\n[9xf] Ctrl+C received — finishing this iteration, then shutting down cleanly.")

        signal.signal(signal.SIGINT, handler)

    def _stop_requested(self) -> str | None:
        if (self.project_dir / STOP_FILENAME).exists():
            return "STOP file detected"
        if self._interrupted:
            return "interrupted by Ctrl+C"
        return None

    def _maybe_restore_best(self, iteration: int) -> None:
        """keep_best: if the run ever reached a better-scoring state than the
        one it's ending in, restore that state before shutdown. Overnight runs
        wander; the deliverable should be the best state ever reached, not the
        last. Skipped when the run FINISHED (that state is goal-complete)."""
        if not self.config.keep_best or self._finished:
            return
        entries = read_entries(self.project_dir)
        best, final = best_state(entries), final_state(entries)
        if not best or not final or best.get("commit") == final.get("commit"):
            return
        if fitness_of(best) <= fitness_of(final):
            return
        target = best["commit"]
        summary = (f"restored best state {target} (iteration {best.get('iteration')}, "
                   f"score {fitness_of(best)}) over final state {final.get('commit')} "
                   f"(score {fitness_of(final)})")
        try:
            restore_paths(self.project_dir, target, WRITABLE_DIRS)
        except Exception as e:
            logger.warning(f"[9xf] warning: best-state restore failed: {e}")
            return
        logger.info(f"[9xf] keep_best: {summary}")
        commit_hash = ""
        if has_changes(self.project_dir):
            commit_hash = commit_all(self.project_dir, f"[shutdown] {summary}")
        append_entry(self.project_dir, LogEntry(
            iteration=iteration, timestamp=now_iso(), subtask="", summary=summary,
            commit=commit_hash, event="restore_best", reverted_to=target,
        ))

    def _clean_shutdown(self, iteration: int, reason: str):
        logger.info(f"[9xf] shutting down: {reason}")
        append_activity(self.project_dir, f"shutting down: {reason}", iteration=iteration,
                        kind="shutdown")
        try:
            self._maybe_restore_best(iteration)
        except Exception as e:
            logger.warning(f"[9xf] warning: keep_best check failed: {e}")
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
            logger.warning(f"[9xf] warning: shutdown commit failed: {e}")
