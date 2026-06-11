"""Build the codebase + history context strings fed to the model each iteration.

The snapshot includes src/, tests/, and tools/ contents, trimmed to a character
budget; what gets cut as the project outgrows the budget is one of the research
questions, so trimming is logged in the string itself.

v0.3: a "relevance" strategy scores files against the current subtask and
recent history (see relevance.py) and fills the budget by descending score —
omitted files keep a one-line API stub. The v0.2 directory-order behavior
remains available as context_strategy="brute" for control runs. Also new:
a what-changed-last-iteration git diff section and a persistent NOTES.md.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ninexf import GOAL_FILENAME, LOG_FILENAME, STOP_FILENAME
from ninexf.looplog import read_entries
from ninexf.relevance import score_files, stub_line

SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules"}
SKIP_FILES = {LOG_FILENAME, STOP_FILENAME, "REPORT.md", "state.json",
              "TASKS.md", "ACCEPTANCE.md",  # tasks/criteria get dedicated prompt sections
              "NOTES.md"}  # notes get their own prompt section too
CONTENT_DIRS = ("src", "tests", "tools")
NOTES_FILENAME = "NOTES.md"


def _tree(project_dir: Path) -> list[Path]:
    files = []
    for p in sorted(project_dir.rglob("*")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file() and p.name not in SKIP_FILES:
            files.append(p)
    return files


def build_snapshot(
    project_dir: Path,
    char_budget: int,
    subtask: str = "",
    entries: list[dict] | None = None,
    strategy: str = "brute",
) -> tuple[str, list[str]]:
    """File tree plus file contents up to the budget.
    Returns (snapshot_text, included_relative_paths) — what was actually shown
    to the model is a key research observable, so callers log the list."""
    files = _tree(project_dir)
    rels = [p.relative_to(project_dir) for p in files]

    lines = ["File tree:"]
    lines += [f"  {r}" for r in rels] or ["  (empty)"]
    lines.append("")

    candidates = [(p, str(r)) for p, r in zip(files, rels)
                  if r.parts and r.parts[0] in CONTENT_DIRS]
    if strategy == "relevance" and subtask:
        scored = score_files(candidates, subtask, entries or [])
        ordered = [(s.path, s.rel, s.score) for s in scored]
    else:
        ordered = [(p, r, None) for p, r in candidates]

    used = sum(len(l) + 1 for l in lines)
    included: list[str] = []
    skipped: list[str] = []
    for path, rel, score in ordered:
        try:
            content = path.read_text()
        except (UnicodeDecodeError, OSError):
            skipped.append(f"{rel} (unreadable)")
            continue
        block = f"--- {rel} ---\n{content}\n"
        if used + len(block) > char_budget:
            if score is not None:
                # keep the API surface visible even when the body doesn't fit
                stub = stub_line(path, rel, score)
                lines.append(stub)
                used += len(stub) + 1
            else:
                skipped.append(f"{rel} ({len(content)} chars, over context budget)")
            continue
        lines.append(block)
        used += len(block)
        included.append(rel)

    if skipped:
        lines.append("OMITTED FROM CONTEXT (budget exceeded): " + ", ".join(skipped))
    return "\n".join(lines), included


def snapshot_codebase(
    project_dir: Path,
    char_budget: int,
    subtask: str = "",
    entries: list[dict] | None = None,
    strategy: str = "brute",
) -> str:
    text, _ = build_snapshot(project_dir, char_budget, subtask, entries, strategy)
    return text


def changes_since_last(project_dir: Path, last_commit: str, char_budget: int) -> str:
    """Unified diff of src/tests/tools since the previous iteration's commit —
    cheap orientation so the model doesn't have to re-read whole files."""
    if not last_commit:
        return ""
    try:
        out = subprocess.run(
            ["git", "diff", last_commit, "HEAD", "--unified=2", "--",
             *CONTENT_DIRS],
            cwd=project_dir, capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if not out:
        return ""
    if len(out) > char_budget:
        out = out[:char_budget] + "\n... (diff truncated)"
    return out


# -- persistent notes (NOTES.md) ----------------------------------------------

def append_notes(project_dir: Path, iteration: int, notes: list[str],
                 max_lines: int, source: str = "") -> list[str]:
    """Append one-line notes (FIFO-capped) to the harness-managed NOTES.md.
    Returns the lines actually added."""
    if not notes:
        return []
    path = project_dir / NOTES_FILENAME
    existing = path.read_text().splitlines() if path.exists() else []
    tag = f" {source}:" if source else ""
    added = [f"[iter {iteration}]{tag} {n.strip()}" for n in notes if n.strip()]
    lines = existing + added
    if len(lines) > max_lines:
        lines = lines[-max_lines:]  # oldest dropped
    path.write_text("\n".join(lines) + "\n")
    return added


def notes_for_prompt(project_dir: Path) -> str:
    path = project_dir / NOTES_FILENAME
    if not path.exists():
        return ""
    return path.read_text().strip()


HISTORY_EVENTS = {"iteration", "decompose", "verify", "revert", "restore_best"}


def history_for_context(project_dir: Path, max_entries: int) -> str:
    entries = [e for e in read_entries(project_dir) if e.get("event") in HISTORY_EVENTS]
    if not entries:
        return "(no previous iterations — this is iteration 1)"
    recent = entries[-max_entries:]
    lines = []
    for e in recent:
        if e.get("event") != "iteration":
            note = (" — the failed approach was discarded; try something DIFFERENT"
                    if e.get("event") == "revert" else "")
            lines.append(f"[iter {e.get('iteration')}] HARNESS ACTION ({e.get('event')}): "
                         f"{e.get('summary', '')}{note}")
            continue
        status = "ok" if e.get("validation_passed") else "FAILED"
        if e.get("acceptance_passed") is not None:
            status += (", acceptance ok" if e.get("acceptance_passed")
                       else ", acceptance FAILING")
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
