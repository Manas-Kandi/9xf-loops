"""Relevance-based context selection (v0.3).

v0.2 filled the context budget in directory order and dropped whatever came
last — as a project grows, the model loses exactly the files it's working on.
This module scores every project file against the current subtask and recent
history, then fills the budget by descending score. Over-budget files get a
one-line stub with their def/class names (via ast) so the API surface stays
visible even when the body doesn't fit. Pure stdlib.

Scoring signals:
  +10  file path/stem mentioned in the subtask
  + 8  file named in the last 3 iterations' errors
  + 5  recently written (decaying: 5, 3.3, 2.5 over the last 3 iterations)
  + 3  import-graph neighbor of a +10/+8 file (one hop, via ast)
  +0-2 identifier-token overlap between subtask and file head
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

TOKEN_RE = re.compile(r"[a-zA-Z_]\w+")
HEAD_CHARS = 2048  # how much of each file the token-overlap signal samples


@dataclass
class ScoredFile:
    path: Path  # absolute
    rel: str
    score: float
    size: int


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text)}


def _import_names(path: Path) -> set[str]:
    """Module names this file imports (stdlib ast; empty set on parse failure)."""
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _def_names(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    return [n.name for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def stub_line(path: Path, rel: str, score: float) -> str:
    names = _def_names(path)
    api = f" defs: {', '.join(names[:12])}" if names else ""
    return f"--- {rel} (omitted, score {score:.1f}, {path.stat().st_size} chars):{api} ---"


def score_files(
    files: list[tuple[Path, str]],  # (absolute, relative-str) content candidates
    subtask: str,
    recent_entries: list[dict],  # iteration log entries, oldest first
) -> list[ScoredFile]:
    sub_lower = subtask.lower()
    sub_tokens = _tokens(subtask)

    error_files: set[str] = set()
    written_decay: dict[str, float] = {}
    for age, e in enumerate(reversed(recent_entries[-3:])):  # age 0 = most recent
        for err in e.get("errors", []):
            for _, rel in files:
                if Path(rel).name in str(err):
                    error_files.add(rel)
        for rel in e.get("files_written", []):
            written_decay.setdefault(rel, 5.0 / (1 + 0.5 * age))

    scored: dict[str, ScoredFile] = {}
    mentioned: set[str] = set()
    for path, rel in files:
        score = 0.0
        stem = Path(rel).stem.lower()
        if rel.lower() in sub_lower or (len(stem) > 2 and stem in sub_tokens):
            score += 10
            mentioned.add(rel)
        if rel in error_files:
            score += 8
        score += written_decay.get(rel, 0.0)
        try:
            content = path.read_text()
        except (UnicodeDecodeError, OSError):
            content = ""
        score += min(2.0, len(sub_tokens & _tokens(content[:HEAD_CHARS])) * 0.25)
        scored[rel] = ScoredFile(path=path, rel=rel, score=score, size=len(content))

    # import-graph neighbors of high-signal files (one hop, both directions)
    hot = mentioned | error_files
    if hot:
        imports_by_rel = {rel: _import_names(path) for path, rel in files}
        hot_stems = {Path(r).stem for r in hot}
        hot_imports = {name for r in hot for name in imports_by_rel.get(r, set())}
        for _, rel in files:
            if rel in hot:
                continue
            if imports_by_rel[rel] & hot_stems or Path(rel).stem in hot_imports:
                scored[rel].score += 3

    return sorted(scored.values(), key=lambda s: (-s.score, s.rel))
