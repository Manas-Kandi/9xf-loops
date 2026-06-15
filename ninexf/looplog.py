"""Append-only JSONL research log: one entry per iteration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ninexf import LOG_FILENAME


@dataclass
class LogEntry:
    iteration: int
    timestamp: str
    subtask: str
    summary: str
    files_written: list[str] = field(default_factory=list)
    validation_passed: bool | None = None
    validation_detail: str = ""
    errors: list[str] = field(default_factory=list)
    soft_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)
    commit: str = ""
    event: str = "iteration"  # iteration | startup | shutdown | violation | decompose | verify | finished | revert | explore | restore_best
    mode: str = "build"  # build | fix | review | verify_done
    stuck_detected: bool = False
    stuck_signals: list[str] = field(default_factory=list)  # repeat | oscillation | no_writes | same_error
    reverted_to: str = ""  # commit hash, on revert events
    regression: bool = False
    tests_ran: int = 0
    tool_runs: list[dict] = field(default_factory=list)  # {name, args, result}
    task_id: int = 0  # which TASKS.md task this iteration targeted (0 = none/unknown)
    tasks_done: int = 0
    tasks_total: int = 0
    context_files: list[str] = field(default_factory=list)  # files shown to the executor
    notes_added: list[str] = field(default_factory=list)
    acceptance_passed: bool | None = None  # held-out suite (None = no suite)
    acceptance_ran: int = 0
    critic_verdict: str = ""  # ACCEPT | REVISE | unparsed | "" (critic off/skipped)
    critic_issues: list[str] = field(default_factory=list)
    critic_revised: bool = False
    candidates: list[dict] = field(default_factory=list)  # best-of-N losers + winner meta
    chosen_candidate: int = 0
    explore: dict = field(default_factory=dict)  # {a: {...}, b: {...}, winner} on explore events
    repairs: list[dict] = field(default_factory=list)  # in-iteration repair attempts {attempt, errors_before, passed}
    model_calls: list[dict] = field(default_factory=list)  # per-call purpose, size, latency, errors
    context_overflow: bool = False  # a prompt filled num_ctx (silent top-truncation risk)
    failure_kind: str = ""  # compile | import | entry | slow_entry | tests | timeout | slow_test | frontend_static | tool | parse
    error_signature: str = ""  # normalized first-error signature for stuck/diagnosis
    error_excerpt: str = ""  # capped actionable validation evidence
    diagnosis: str = ""  # optional no-write diagnosis before repeated repairs
    quality_status: str = ""  # READY | NEEDS_MORE_WORK | ""
    quality_score: int = 0  # summed 0-25 score from quality review
    quality_scores: dict[str, int] = field(default_factory=dict)
    quality_issues: list[str] = field(default_factory=list)
    quality_next_focus: str = ""
    quality_summary: str = ""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_entry(project_dir: Path, entry: LogEntry) -> None:
    path = project_dir / LOG_FILENAME
    with path.open("a") as f:
        f.write(json.dumps(asdict(entry)) + "\n")


def read_entries(project_dir: Path) -> list[dict]:
    path = project_dir / LOG_FILENAME
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            entries.append({"event": "corrupt-line", "raw": line[:200]})
    return entries


def last_iteration_number(project_dir: Path) -> int:
    nums = [e.get("iteration", 0) for e in read_entries(project_dir) if e.get("event") == "iteration"]
    return max(nums, default=0)
