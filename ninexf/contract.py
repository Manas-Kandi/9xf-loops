"""Harness-managed project contract.

The contract is intentionally deterministic. It does not try to invent an API;
it freezes the user's goal, sanitized acceptance criteria, task order, and
engineering rules that keep local-model loops from drifting into test-chasing.
"""

from __future__ import annotations

from pathlib import Path

CONTRACT_FILENAME = "CONTRACT.md"
CONTRACT_HEADER = "# 9xf project contract - managed by the harness"


def contract_path(project_dir: Path) -> Path:
    return project_dir / CONTRACT_FILENAME


def save_contract(
    project_dir: Path,
    goal: str,
    tasks: list[str],
    criteria: list[str],
) -> None:
    lines = [
        CONTRACT_HEADER,
        "",
        "## Goal",
        goal.strip(),
        "",
        "## Engineering Rules",
        "- Source code lives in `src/`; tests live in `tests/`; helper scripts live in `tools/`.",
        "- Use only the Python standard library unless the user goal explicitly says otherwise.",
        "- Keep one canonical implementation for each public class/function; do not duplicate it in `src/main.py` and a module.",
        "- Once a public name, constructor, method, or return type exists, keep it stable unless validation proves it violates the goal.",
        "- Prefer fixing implementation code over weakening tests. Edit tests only when they are wrong, slow, nondeterministic, or contradict this contract.",
        "- Tests must be deterministic: do not call `time.sleep()`, `time.time()`, or `time.monotonic()` in tests; inject clocks or use fixed numeric timestamps.",
        "- Entry points and demos must be bounded and fast: no sleeps, infinite loops, long animations, or waiting for user input unless the goal explicitly asks.",
        "- Do not request external tools such as pytest, flake8, npm, pip, or shell commands.",
        "",
        "## Ordered Work",
    ]
    lines += [f"- T{i}: {text}" for i, text in enumerate(tasks, start=1)] or ["- (none)"]
    lines += ["", "## Acceptance Criteria"]
    lines += [f"- C{i}: {text}" for i, text in enumerate(criteria, start=1)] or ["- (none)"]
    contract_path(project_dir).write_text("\n".join(lines).rstrip() + "\n")


def contract_for_prompt(project_dir: Path) -> str:
    path = contract_path(project_dir)
    if not path.exists():
        return ""
    return path.read_text().strip()
