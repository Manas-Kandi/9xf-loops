"""QualityMixin: anti-complacency review passes and quality-derived tasks."""

from __future__ import annotations

from ninexf.loop_common import *  # noqa: F401,F403 - shared LoopRunner surface


class QualityMixin:
    def _latest_quality_review(self) -> dict | None:
        for entry in reversed(read_entries(self.project_dir)):
            if entry.get("quality_status"):
                return entry
        return None

    def _quality_blocker(self) -> str:
        latest = self._latest_quality_review()
        if not latest:
            return ""
        if latest.get("quality_status") != "NEEDS_MORE_WORK":
            return ""
        issues = latest.get("quality_issues") or []
        focus = latest.get("quality_next_focus") or ""
        if issues:
            return "quality review still sees: " + " | ".join(str(i) for i in issues[:2])
        if focus:
            return "quality review next focus: " + focus
        return ""

    def _quality_tasks(self, review: QualityReview) -> list[str]:
        tasks: list[str] = []
        for issue in review.issues[:2]:
            clean = issue.strip().rstrip(".")
            if clean:
                tasks.append(f"Quality pass: address this remaining weakness: {clean}.")
        if not tasks and review.next_focus:
            tasks.append(f"Quality pass: {review.next_focus.strip().rstrip('.')}.")
        return tasks

    def _review_quality(
        self,
        *,
        purpose: str,
        subtask: str,
        validation_detail: str,
        validation_warnings: list[str],
        acceptance_passed: bool | None,
    ) -> tuple[QualityReview, str]:
        if not self.config.quality_review_enabled:
            return QualityReview(), ""
        append_activity(self.project_dir, "reviewing artifact quality",
                        iteration=int(read_state(self.project_dir).get("iteration", 0) or 0),
                        kind="quality")
        codebase = snapshot_codebase(
            self.project_dir,
            self.config.snapshot_budget,
            subtask=subtask,
            entries=[e for e in read_entries(self.project_dir) if e.get("event") == "iteration"],
            strategy=self.config.context_strategy,
            cache=self._file_cache,
        )
        raw = self._complete(
            purpose,
            QUALITY_REVIEW_SYSTEM,
            QUALITY_REVIEW_USER.format(
                goal=self.goal,
                contract=contract_for_prompt(self.project_dir) or "(none)",
                subtask=subtask,
                codebase=codebase,
                diff=staged_diff(self.project_dir, WRITABLE_DIRS)[:CRITIC_DIFF_CHARS] or "(no diff)",
                validation=validation_detail or "(none)",
                warnings=" | ".join(validation_warnings) if validation_warnings else "(none)",
                acceptance=acceptance_passed,
                criteria=criteria_for_prompt(self.project_dir) or "(none)",
            ),
        )
        return parse_quality_review(raw), raw
