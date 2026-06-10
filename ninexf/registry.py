"""Global registry of run folders (~/.9xf/registry.json) plus per-run
state.json heartbeats — what `9xf watch` reads to show every loop at once.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ninexf import GOAL_FILENAME

REGISTRY_DIR = Path.home() / ".9xf"
REGISTRY_FILE = REGISTRY_DIR / "registry.json"
STATE_FILENAME = "state.json"


def _load() -> list[dict]:
    if not REGISTRY_FILE.exists():
        return []
    try:
        return json.loads(REGISTRY_FILE.read_text())
    except json.JSONDecodeError:
        return []


def register_run(project_dir: Path, goal: str, started: str | None = None) -> None:
    REGISTRY_DIR.mkdir(exist_ok=True)
    entries = [e for e in _load() if e.get("dir") != str(project_dir)]
    entries.append({"dir": str(project_dir), "goal": goal, "last_started": started})
    REGISTRY_FILE.write_text(json.dumps(entries, indent=2))


def registered_runs() -> list[Path]:
    """Registered run dirs that still exist (stale entries pruned)."""
    live, entries = [], _load()
    kept = []
    for e in entries:
        p = Path(e.get("dir", ""))
        if p.is_dir() and (p / GOAL_FILENAME).exists():
            live.append(p)
            kept.append(e)
    if len(kept) != len(entries) and REGISTRY_FILE.exists():
        REGISTRY_FILE.write_text(json.dumps(kept, indent=2))
    return live


def write_state(project_dir: Path, **fields) -> None:
    state = {"pid": os.getpid(), **fields}
    (project_dir / STATE_FILENAME).write_text(json.dumps(state, indent=2))


def read_state(project_dir: Path) -> dict:
    p = project_dir / STATE_FILENAME
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}
