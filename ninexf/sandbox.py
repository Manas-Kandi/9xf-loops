"""Path containment: the agent may only write inside src/, tests/, and tools/.

Every write path the model produces goes through validate_write_path before
any file is touched. Anything that resolves outside the allowed subtree is
rejected and reported as a containment violation (which the loop logs —
violations are research data, not silent failures).
"""

from __future__ import annotations

from pathlib import Path

WRITABLE_DIRS = ("src", "tests", "tools")
PROTECTED_FILES = ("goal.txt", "9xf.config.json", "loop_log.jsonl", "STOP")


class ContainmentViolation(Exception):
    def __init__(self, requested: str, reason: str):
        self.requested = requested
        self.reason = reason
        super().__init__(f"containment violation: {requested!r} — {reason}")


def validate_write_path(project_dir: Path, requested: str) -> Path:
    """Resolve a model-supplied relative path; raise unless it lands in src/ or tests/."""
    if not requested or requested.strip() == "":
        raise ContainmentViolation(requested, "empty path")

    rel = Path(requested.strip())
    if rel.is_absolute():
        raise ContainmentViolation(requested, "absolute paths are not allowed")

    project_root = project_dir.resolve()
    target = (project_root / rel).resolve()

    # Must stay inside the project folder at all (catches ../ escapes).
    try:
        inside = target.relative_to(project_root)
    except ValueError:
        raise ContainmentViolation(requested, "resolves outside the project folder")

    parts = inside.parts
    if not parts or parts[0] not in WRITABLE_DIRS:
        raise ContainmentViolation(
            requested, f"writes are only permitted under {'/, '.join(WRITABLE_DIRS)}/"
        )
    if inside.name in PROTECTED_FILES:
        raise ContainmentViolation(requested, "protected file")
    if ".git" in parts:
        raise ContainmentViolation(requested, ".git is off-limits")

    # Refuse to write through a symlink that points outside the sandbox.
    for ancestor in [target, *target.parents]:
        if ancestor == project_root:
            break
        if ancestor.is_symlink():
            raise ContainmentViolation(requested, f"symlink in path: {ancestor.name}")

    return target


def safe_write(project_dir: Path, requested: str, content: str) -> Path:
    target = validate_write_path(project_dir, requested)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target
