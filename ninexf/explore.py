"""Branch-and-explore trigger logic (v0.3).

When the loop is hard-stuck — stuck signals keep firing AND a revert already
failed to unstick it — the harness tries two genuinely different approaches on
separate git branches, validates both, and adopts the winner on the main
branch by file checkout (no merges, no conflicts by construction). The losing
branch is kept (renamed *-rejected) as a research artifact.

This module holds the trigger decision; the orchestration lives in
LoopRunner._maybe_explore (it needs the backend and the executor plumbing).
"""

from __future__ import annotations

EXPLORE_STUCK_WINDOW = 5


def count_explores(entries: list[dict]) -> int:
    return sum(1 for e in entries if e.get("event") == "explore")


def should_explore(entries: list[dict], explore_after_stuck: int) -> bool:
    """Hard-stuck = stuck signals in >= explore_after_stuck of the last 5
    iterations AND a revert has already happened since the last green
    iteration (cheap recovery was tried and didn't help)."""
    last_explore = max((e.get("iteration", 0) for e in entries
                        if e.get("event") == "explore"), default=0)
    iters = [e for e in entries if e.get("event") == "iteration"
             and e.get("iteration", 0) > last_explore]  # an explore resets the window
    recent = iters[-EXPLORE_STUCK_WINDOW:]
    stuck_count = sum(1 for e in recent if e.get("stuck_signals") or e.get("stuck_detected"))
    if stuck_count < explore_after_stuck:
        return False
    last_green = max((e.get("iteration", 0) for e in iters if e.get("validation_passed")),
                     default=0)
    return any(e.get("event") == "revert" and e.get("iteration", 0) >= last_green
               for e in entries)
