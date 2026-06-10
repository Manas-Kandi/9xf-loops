"""Thin git wrapper via subprocess. The git history is the primary research artifact."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    pass


def _git(project_dir: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def init_repo(project_dir: Path) -> None:
    _git(project_dir, "init", "-q")
    # Identity local to this repo so runs work on machines without global config.
    _git(project_dir, "config", "user.name", "9xf-loop-agent")
    _git(project_dir, "config", "user.email", "agent@9xf.local")


def commit_all(project_dir: Path, message: str, allow_empty: bool = False) -> str:
    """Stage everything and commit. Returns the short hash."""
    _git(project_dir, "add", "-A")
    args = ["commit", "-q", "-m", message]
    if allow_empty:
        args.append("--allow-empty")
    _git(project_dir, *args)
    return _git(project_dir, "rev-parse", "--short", "HEAD").strip()


def has_changes(project_dir: Path) -> bool:
    return bool(_git(project_dir, "status", "--porcelain").strip())


def current_branch(project_dir: Path) -> str:
    return _git(project_dir, "rev-parse", "--abbrev-ref", "HEAD").strip()


def create_branch(project_dir: Path, name: str) -> None:
    """Create (or reset) a branch at HEAD and switch to it."""
    _git(project_dir, "checkout", "-q", "-B", name)


def checkout_branch(project_dir: Path, name: str) -> None:
    _git(project_dir, "checkout", "-q", name)


def rename_branch(project_dir: Path, old: str, new: str) -> None:
    _git(project_dir, "branch", "-M", old, new)


def staged_diff(project_dir: Path, paths: tuple[str, ...]) -> str:
    """Stage everything and return the diff vs HEAD for the given paths —
    what the critic reviews before the iteration commit."""
    _git(project_dir, "add", "-A")
    return _git(project_dir, "diff", "--cached", "--unified=2", "--", *paths)


def restore_paths(project_dir: Path, ref: str, paths: tuple[str, ...]) -> None:
    """Make the given dirs exactly match their state at `ref`, leaving history
    linear (this is how v0.3 auto-revert works; never `git reset`).

    checkout alone doesn't delete files added since `ref`, so: drop everything
    tracked under the dirs, restore the ref's tree, then clean untracked
    leftovers — scoped strictly to the given dirs, never the project root."""
    _git(project_dir, "rm", "-rqf", "--ignore-unmatch", "--", *paths)
    for p in paths:
        try:
            _git(project_dir, "checkout", ref, "--", p)
        except GitError:
            pass  # path didn't exist at ref (e.g. empty tools/) — that's fine
    _git(project_dir, "clean", "-fdq", "--", *paths)
