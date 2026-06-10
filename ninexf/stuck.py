"""Multi-signal stuck detection (v0.3).

v0.2 only compared the proposed subtask against recent ones by string
similarity. That misses oscillation (A-B-A-B), iterations that write nothing,
and the same error recurring under differently-worded subtasks. Each detector
returns a StuckSignal; all fired signals are logged (`stuck_signals`) so the
report can histogram which failure shapes a model exhibits.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

REPEAT_LOOKBACK = 5
OSCILLATION_LOOKBACK = 6
NO_WRITES_WINDOW = 3
SAME_ERROR_WINDOW = 3


@dataclass
class StuckSignal:
    kind: str  # repeat | oscillation | no_writes | same_error
    detail: str


def _similar(a: str, b: str, threshold: float) -> bool:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio() > threshold


def normalize_error(err: str) -> str:
    """Strip digits, quoted strings, and paths so the same underlying error
    matches across iterations even when line numbers or names shift."""
    s = re.sub(r"'[^']*'|\"[^\"]*\"", "_", str(err))
    s = re.sub(r"/\S+", "_", s)
    s = re.sub(r"\d+", "_", s)
    return s.strip().lower()


def find_repeats(subtask: str, entries: list[dict], threshold: float) -> list[str]:
    """v0.2 signal: proposed subtask ~= one of the last N completed subtasks."""
    recent = [e.get("subtask", "") for e in entries[-REPEAT_LOOKBACK:] if e.get("subtask")]
    return [prior for prior in recent if _similar(subtask, prior, threshold)]


def detect_oscillation(subtask: str, entries: list[dict], threshold: float) -> StuckSignal | None:
    """A-B-A pattern: the proposal matches iteration N-2 but not N-1 — the loop
    is bouncing between two intents without converging on either."""
    recent = [e.get("subtask", "") for e in entries[-OSCILLATION_LOOKBACK:] if e.get("subtask")]
    if len(recent) < 2:
        return None
    if _similar(subtask, recent[-2], threshold) and not _similar(subtask, recent[-1], threshold):
        return StuckSignal("oscillation", f"alternating with: {recent[-2]!r}")
    return None


def detect_no_writes(entries: list[dict]) -> StuckSignal | None:
    recent = entries[-NO_WRITES_WINDOW:]
    if len(recent) < NO_WRITES_WINDOW:
        return None
    empty = sum(1 for e in recent if not e.get("files_written"))
    if empty >= 2:
        return StuckSignal("no_writes", f"{empty} of last {NO_WRITES_WINDOW} iterations wrote nothing")
    return None


def detect_same_error(entries: list[dict]) -> StuckSignal | None:
    recent = [e for e in entries[-SAME_ERROR_WINDOW:] if not e.get("validation_passed")]
    if len(recent) < SAME_ERROR_WINDOW:
        return None
    sigs = []
    for e in recent:
        errs = e.get("errors") or []
        if not errs:
            return None
        sigs.append(normalize_error(errs[0]))
    if len(set(sigs)) == 1:
        return StuckSignal("same_error", f"same error for {SAME_ERROR_WINDOW} iterations: "
                                         f"{str(recent[-1]['errors'][0])[:150]}")
    return None


def detect_signals(subtask: str, entries: list[dict], threshold: float) -> list[StuckSignal]:
    """All fired stuck signals for this proposed subtask given iteration history.
    `entries` must be iteration-event log entries, oldest first."""
    signals: list[StuckSignal] = []
    repeats = find_repeats(subtask, entries, threshold)
    if repeats:
        signals.append(StuckSignal("repeat", f"matches recent: {repeats[-1]!r}"))
    for sig in (detect_oscillation(subtask, entries, threshold),
                detect_no_writes(entries),
                detect_same_error(entries)):
        if sig:
            signals.append(sig)
    return signals
