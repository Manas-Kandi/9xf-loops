"""Build the codebase + history context strings fed to the model each iteration.

The snapshot includes src/, tests/, and tools/ contents, trimmed to a character
budget; what gets cut as the project outgrows the budget is one of the research
questions, so trimming is logged in the string itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from ninexf import GOAL_FILENAME, LOG_FILENAME, STOP_FILENAME
from ninexf.looplog import read_entries

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
SKIP_FILES = {LOG_FILENAME, STOP_FILENAME, "REPORT.md", "state.json"}
CONTENT_DIRS = ("src", "tests", "tools")


def _tree(project_dir: Path) -> list[Path]:
    files = []
    for p in sorted(project_dir.rglob("*")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and p.name not in SKIP_FILES:
            files.append(p)
    return files


def snapshot_codebase(project_dir: Path, char_budget: int) -> str:
    """File tree plus contents of src/ and tests/, truncated to the budget."""
    files = _tree(project_dir)
    rels = [p.relative_to(project_dir) for p in files]

    lines = ["File tree:"]
    lines += [f"  {r}" for r in rels] or ["  (empty)"]
    lines.append("")

    used = sum(len(l) + 1 for l in lines)
    skipped = []
    for p, r in zip(files, rels):
        if r.parts and r.parts[0] not in CONTENT_DIRS and r.name != GOAL_FILENAME:
            continue
        if r.name == GOAL_FILENAME:
            continue  # goal is passed separately
        try:
            content = p.read_text()
        except (UnicodeDecodeError, OSError):
            skipped.append(f"{r} (unreadable)")
            continue
        block = f"--- {r} ---\n{content}\n"
        if used + len(block) > char_budget:
            skipped.append(f"{r} ({len(content)} chars, over context budget)")
            continue
        lines.append(block)
        used += len(block)

    if skipped:
        lines.append("OMITTED FROM CONTEXT (budget exceeded): " + ", ".join(skipped))
    return "\n".join(lines)


def history_for_context(project_dir: Path, max_entries: int) -> str:
    entries = [e for e in read_entries(project_dir) if e.get("event") == "iteration"]
    if not entries:
        return "(no previous iterations — this is iteration 1)"
    recent = entries[-max_entries:]
    lines = []
    for e in recent:
        status = "ok" if e.get("validation_passed") else "FAILED"
        flags = []
        if e.get("regression"):
            flags.append("REGRESSION: this broke previously-working code")
        if e.get("stuck_detected"):
            flags.append("repeated a recent subtask")
        flag_str = f" [{'; '.join(flags)}]" if flags else ""
        lines.append(
            f"[iter {e.get('iteration')}] ({e.get('mode', 'build')}, {status}){flag_str}"
            f" subtask: {e.get('subtask', '')!r} — did: {e.get('summary', '')}"
        )
        if e.get("errors"):
            lines.append(f"    errors: {json.dumps(e['errors'])[:300]}")
        for tr in e.get("tool_runs", []):
            lines.append(
                f"    tool {tr.get('name')} {tr.get('args', '')}: {tr.get('result', '')[:300]}"
            )
    if len(entries) > max_entries:
        lines.insert(0, f"(showing last {max_entries} of {len(entries)} iterations)")
    return "\n".join(lines)
