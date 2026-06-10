"""Shallow validation: does the code parse, does the entry point run, do the tests pass.

Per the PRD this is intentionally not semantic. Runs happen in a subprocess
with a stripped environment and a timeout. On macOS, when allow_network is
false, the run is wrapped in sandbox-exec with a deny-network profile
(best-effort: falls back to an unwrapped run if sandbox-exec is unavailable).
"""

from __future__ import annotations

import py_compile
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

DENY_NETWORK_PROFILE = '(version 1)(allow default)(deny network*)'


@dataclass
class ValidationResult:
    passed: bool
    detail: str = ""
    errors: list[str] = field(default_factory=list)
    tests_ran: int = 0
    tests_failed: list[str] = field(default_factory=list)


def run_sandboxed(
    project_dir: Path,
    cmd: list[str],
    timeout: float,
    allow_network: bool,
) -> tuple[int, str]:
    """Run a command in the project dir with a stripped env, timeout, and
    (on macOS, best-effort) no network. Returns (returncode, combined output).
    Used by both validation and agent-created tool runs. -1 means timeout."""
    if not allow_network and sys.platform == "darwin":
        sandboxed = ["sandbox-exec", "-p", DENY_NETWORK_PROFILE, *cmd]
        probe = subprocess.run(
            ["sandbox-exec", "-p", DENY_NETWORK_PROFILE, "true"],
            capture_output=True, cwd=project_dir,
        )
        if probe.returncode == 0:
            cmd = sandboxed
    env = {"PATH": "/usr/bin:/bin", "HOME": str(project_dir)}
    try:
        result = subprocess.run(
            cmd, cwd=project_dir, env=env,
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return -1, f"timed out after {timeout}s"
    output = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
    return result.returncode, output


def _compile_check(paths: list[Path]) -> list[str]:
    errors = []
    for p in paths:
        if p.suffix != ".py":
            continue
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{p.name}: {e.msg.strip().splitlines()[-1] if e.msg else 'syntax error'}")
        except Exception as e:  # unreadable file etc.
            errors.append(f"{p.name}: {e}")
    return errors


def _entry_point(project_dir: Path) -> Path | None:
    for candidate in ("src/main.py", "src/app.py", "src/cli.py"):
        p = project_dir / candidate
        if p.exists():
            return p
    return None


def _tail(text: str, n: int = 5) -> str:
    return " | ".join(text.strip().splitlines()[-n:])


def _run_entry(project_dir: Path, script: Path, timeout: float, allow_network: bool) -> list[str]:
    rc, out = run_sandboxed(
        project_dir,
        [sys.executable, str(script.relative_to(project_dir))],
        timeout, allow_network,
    )
    if rc != 0:
        return [f"{script.name}: exit {rc}: {_tail(out)}"]
    return []


def _run_tests(project_dir: Path, timeout: float, allow_network: bool) -> tuple[int, list[str]]:
    """Run unittest discovery over tests/. Returns (tests_ran, failures)."""
    if not list((project_dir / "tests").glob("test_*.py")):
        return 0, []
    # unittest discovery needs the start dir to be importable
    init_py = project_dir / "tests" / "__init__.py"
    if not init_py.exists():
        init_py.touch()
    rc, out = run_sandboxed(
        project_dir,
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        timeout, allow_network,
    )
    m = re.search(r"Ran (\d+) tests?", out)
    ran = int(m.group(1)) if m else 0
    if rc != 0:
        return ran, [f"tests: exit {rc}: {_tail(out)}"]
    return ran, []


def validate(
    project_dir: Path,
    written_files: list[Path],
    timeout: float,
    allow_network: bool,
    run_tests: bool = True,
) -> ValidationResult:
    errors = _compile_check(written_files)
    detail_parts = ["compile-check"]
    tests_ran, tests_failed = 0, []
    if not errors:
        entry = _entry_point(project_dir)
        if entry is not None:
            errors = _run_entry(project_dir, entry, timeout, allow_network)
            detail_parts.append(f"ran {entry.relative_to(project_dir)}")
        if run_tests:
            tests_ran, tests_failed = _run_tests(project_dir, timeout, allow_network)
            if tests_ran or tests_failed:
                detail_parts.append(f"{tests_ran} tests")
            errors.extend(tests_failed)
    return ValidationResult(
        passed=not errors,
        detail=" + ".join(detail_parts),
        errors=errors,
        tests_ran=tests_ran,
        tests_failed=tests_failed,
    )
