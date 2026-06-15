"""Shared surface for the LoopRunner mixins.

loop.py used to be a single 1,380-line class. It's now split into concern-focused
mixins (lifecycle, planning, execution, verification, recovery, decomposition,
reflection) that LoopRunner combines by inheritance — behavior is identical, the
file is navigable. This module holds what every mixin needs: the imports,
tunable constants, the small module-level helpers, and the ExecOutcome dataclass.
Mixins do `from ninexf.loop_common import *` (plus the underscore helpers they
name explicitly), keeping each file focused on its own logic.
"""

from __future__ import annotations

import re
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path

from ninexf import GOAL_FILENAME, STOP_FILENAME
from ninexf.backends import Backend, BackendError, is_rate_limit_error, make_backend
from ninexf.candidates import (
    CANDIDATE_TEMPERATURES, CandidateResult, best_of_n_active,
    parse_critic_output, pick_winner,
)
from ninexf.config import Config
from ninexf.contract import contract_for_prompt, save_contract
from ninexf.context import (
    append_notes, build_snapshot, changes_since_last, history_for_context,
    notes_for_prompt, snapshot_codebase,
)
from ninexf.explore import count_explores, should_explore
from ninexf.filecache import FileCache
from ninexf.fitness import best_state, final_state, fitness_of
from ninexf.gitops import (
    checkout_branch, commit_all, create_branch, current_branch, has_changes,
    rename_branch, restore_paths, staged_diff,
)
from ninexf.log import logger
from ninexf.looplog import LogEntry, append_entry, last_iteration_number, now_iso, read_entries
from ninexf.parser import ParsedOutput, parse_executor_output
from ninexf.prompts import (
    BLOCKER_SECTION, CHANGES_SECTION, CRITIC_SYSTEM, CRITIC_USER, DECOMPOSE_RETRY_NOTE,
    DECOMPOSE_SYSTEM, DECOMPOSE_USER, DIAGNOSIS_SYSTEM, DIAGNOSIS_USER,
    EXECUTOR_SYSTEM, EXECUTOR_USER, EXPLORE_NUDGE_A, EXPLORE_NUDGE_B,
    FORMAT_RETRY_NOTE,
    MODE_BUILD, MODE_FIX, MODE_REVIEW, NO_TESTS_NOTE, NOTES_SECTION,
    CONTRACT_SECTION, PLANNER_SYSTEM, PLANNER_USER, REFLECTION_SYSTEM,
    QUALITY_REVIEW_SYSTEM, QUALITY_REVIEW_USER,
    REFLECTION_USER, REPAIR_NOTE, REVISE_NOTE, STUCK_NUDGE,
    TASK_ELIGIBILITY_NUDGE,
    TASK_CHECK_SYSTEM, TASK_CHECK_USER, TASKS_SECTION,
    VERIFY_DONE_SYSTEM, VERIFY_DONE_USER,
)
from ninexf.quality import QualityReview, parse_quality_review, review_summary
from ninexf.registry import append_activity, read_state, write_state
from ninexf.sandbox import WRITABLE_DIRS, ContainmentViolation, safe_write
from ninexf.stuck import detect_signals
from ninexf.tasks import (
    STATUS_DEFERRED, STATUS_DONE, STATUS_IN_PROGRESS, Task, TaskList,
    criteria_for_prompt, load_criteria, load_tasks, mark_status,
    parse_decomposition, parse_task_ref, parse_task_ref_num, parse_verify_output,
    parse_task_refs, infer_task_ids_for_files,
    task_has_any_file_evidence, task_has_file_evidence, task_is_corrective,
    task_is_refinement, task_needs_model_check,
    corrective_task_resolved, refinement_task_resolved,
    canonical_validation_task,
    sanitize_decomposition, save_criteria, save_tasks, strip_task_ref,
    fallback_decomposition,
    tasks_for_prompt, tasks_path, append_tasks,
)
from ninexf.tools import run_tool, tools_for_prompt
from ninexf.validate import run_acceptance, validate

MAX_CONSECUTIVE_BACKEND_FAILURES = 3
MAX_REVERTS_TO_SAME_COMMIT = 2
CRITIC_DIFF_CHARS = 6000
REPAIR_FILES_CHARS = 12000  # how much of the broken files the repair prompt shows
REPAIR_CONTEXT_DIRS = {"src", "tests", "tools"}
VALIDATION_TOOL_NAMES = {"unittest"}
REFLECTION_LINE_RE = re.compile(r"^(LEARN|AVOID|TRY):\s*(?P<text>.+?)\s*$", re.I)


@dataclass
class ExecOutcome:
    """One executor attempt: parsed output, written files, validation result."""
    parsed: ParsedOutput
    written: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    validation_passed: bool = False
    validation_detail: str = ""
    tests_ran: int = 0
    failure_kind: str = ""
    error_signature: str = ""
    error_excerpt: str = ""
    parse_warnings: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)


def _add_repair_path(project_dir: Path, rels: list[str], path: Path) -> None:
    try:
        rel = path.resolve().relative_to(project_dir.resolve())
    except (OSError, ValueError):
        try:
            rel = path.relative_to(project_dir)
        except ValueError:
            return
    if not rel.parts or rel.parts[0] not in REPAIR_CONTEXT_DIRS:
        return
    candidate = project_dir / rel
    if not candidate.is_file():
        return
    rendered = str(rel)
    if rendered not in rels:
        rels.append(rendered)


def _repair_context_paths(project_dir: Path, outcome: ExecOutcome) -> list[str]:
    """Files to show in repair prompts: written files plus traceback paths."""
    rels: list[str] = []
    for path in outcome.written:
        _add_repair_path(project_dir, rels, path)
    evidence = "\n".join([*outcome.errors, outcome.error_excerpt])
    for quoted in re.findall(r'File "([^"]+)"', evidence):
        path = Path(quoted)
        _add_repair_path(project_dir, rels, path if path.is_absolute() else project_dir / path)
    for token in re.findall(r"(?<![\w./-])((?:src|tests|tools)/[A-Za-z0-9_.\-/]+)", evidence):
        _add_repair_path(project_dir, rels, project_dir / token.rstrip(".,:;)]}'\""))
    return rels


def _repair_file_dump(project_dir: Path, outcome: ExecOutcome, max_chars: int) -> str:
    blocks = []
    for rel in _repair_context_paths(project_dir, outcome):
        p = project_dir / rel
        try:
            body = p.read_text(errors="replace")
        except OSError as e:
            body = f"(unreadable: {e})"
        blocks.append(f"--- {rel} ---\n{body}")
    if not blocks and outcome.parsed.files:
        blocks = [f"--- {path} ---\n{body}" for path, body in outcome.parsed.files.items()]
    return ("\n".join(blocks) or "(no parseable FILE blocks in the previous output)")[:max_chars]


def _validation_tool_notice(name: str, args: str) -> str:
    if name in VALIDATION_TOOL_NAMES:
        return (
            "ignored: unittest discovery is run automatically by harness validation; "
            "RUN_TOOL only executes existing helper scripts in tools/"
        )
    return ""


def _fatal_parse_problems(parsed: ParsedOutput) -> list[str]:
    """Problems that make an executor reply unusable."""
    return [p for p in parsed.problems if p.startswith("no FILE blocks")]


def _parse_warnings(parsed: ParsedOutput) -> list[str]:
    """Non-fatal formatting problems worth logging without rejecting good code."""
    return [p for p in parsed.problems if p not in _fatal_parse_problems(parsed)]


def note_contradicted(note: str, errors: list[str], warnings: list[str]) -> bool:
    lowered = note.strip().lower()
    evidence = " ".join([*(e.lower() for e in errors), *(w.lower() for w in warnings)])
    if not lowered or not evidence:
        return False
    if "no visible chart marks" in evidence and any(
        phrase in lowered for phrase in (
            "visible marks", "data points", "tooltips", "chart now includes",
            "labels and tooltips", "clear labels",
        )
    ):
        return True
    if ("does not resolve" in evidence or "no local chart library" in evidence) and any(
        phrase in lowered for phrase in (
            "self-contained", "offline-friendly", "all local asset/runtime references are correctly resolved",
            "fixed any broken local asset", "verified",
        )
    ):
        return True
    if any(term in lowered for term in ("fixed", "resolved", "now includes", "verified")):
        if "still appears" in evidence:
            return True
    return False
