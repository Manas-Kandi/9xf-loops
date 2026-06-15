"""Best-state tracking: score every committed state, restore the best at shutdown.

A long unattended run can wander — build something that passes, then spend
hours breaking it. v0.2/v0.3 delivered whatever state the run *ended* in.
With keep_best, the deliverable is the best state the run ever reached, ranked
by a fitness tuple (held-out acceptance first — it's the truest signal — then
harness validation, task progress, test coverage, error count). This makes
overnight wall time strictly additive: more iterations can only ever improve
the final artifact, never degrade it.

The score is recomputed from loop_log.jsonl, so it survives stop/resume and
needs no extra state files.
"""

from __future__ import annotations

# events whose log entries describe a committed, validated tree state
SCOREABLE_EVENTS = {"iteration", "explore", "verify", "finished"}


def fitness_of(entry: dict) -> tuple:
    """Higher is better, compared lexicographically."""
    return (
        1 if entry.get("acceptance_passed") else 0,
        1 if entry.get("validation_passed") else 0,
        1 if entry.get("quality_status") == "READY" else 0,
        entry.get("quality_score", 0),
        entry.get("tasks_done", 0),
        entry.get("tests_ran", 0),
        -len(entry.get("errors") or []),
    )


def scoreable(entries: list[dict]) -> list[dict]:
    return [e for e in entries
            if e.get("event") in SCOREABLE_EVENTS and e.get("commit")]


def best_state(entries: list[dict]) -> dict | None:
    """The best-scoring committed entry (ties go to the most recent — prefer
    the newest equivalent state). None if nothing was ever committed."""
    candidates = scoreable(entries)
    if not candidates:
        return None
    best = candidates[0]
    for e in candidates[1:]:
        if fitness_of(e) >= fitness_of(best):
            best = e
    return best


def final_state(entries: list[dict]) -> dict | None:
    candidates = scoreable(entries)
    return candidates[-1] if candidates else None
