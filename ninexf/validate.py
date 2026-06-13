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
import ast
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
    failure_kind: str = ""
    error_excerpt: str = ""
    error_signature: str = ""


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
    except subprocess.TimeoutExpired as e:
        pieces = []
        for part in (getattr(e, "stdout", None), getattr(e, "stderr", None),
                     getattr(e, "output", None)):
            if not part:
                continue
            if isinstance(part, bytes):
                pieces.append(part.decode(errors="replace"))
            else:
                pieces.append(str(part))
        excerpt = "\n".join(pieces).strip()
        return -1, (f"timed out after {timeout}s"
                    + (f"\nPartial output:\n{excerpt[-3000:]}" if excerpt else ""))
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


def _tail(text: str, n: int = 8) -> str:
    return " | ".join(text.strip().splitlines()[-n:])


def _failure_excerpt(text: str, max_chars: int = 4000) -> str:
    """Keep the actionable part of unittest/subprocess output."""
    stripped = text.strip()
    if not stripped:
        return ""
    blocks = re.findall(
        r"=+\n(?:ERROR|FAIL): .*?(?=\n=+\n|\n-+\nRan \d+ tests?|\Z)",
        stripped,
        flags=re.S,
    )
    footer = ""
    m = re.search(r"-+\nRan \d+ tests?.*?(?:FAILED .*|OK)\s*$", stripped, flags=re.S)
    if m:
        footer = m.group(0)
    if blocks:
        excerpt = "\n\n".join(blocks[:2] + ([footer] if footer else []))
        return excerpt[-max_chars:]
    return stripped[-max_chars:]


def _signature(text: str) -> str:
    s = re.sub(r"'[^']*'|\"[^\"]*\"", "_", str(text))
    s = re.sub(r"/\S+", "_", s)
    s = re.sub(r"\d+", "_", s)
    return s.strip().lower()[:300]


def _slow_test_errors(project_dir: Path, threshold: float = 0.5) -> list[str]:
    """Static guard for obvious self-defeating tests."""
    errors = []
    for p in sorted((project_dir / "tests").glob("test_*.py")):
        try:
            source = p.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = ""
                if isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                    owner = getattr(node.func.value, "id", "")
                    full = f"{owner}.{name}" if owner else name
                elif isinstance(node.func, ast.Name):
                    full = node.func.id
                else:
                    full = ""
                if full in {"time.sleep", "sleep"}:
                    rel = p.relative_to(project_dir)
                    rendered = ast.get_source_segment(source, node) or f"{full}(...)"
                    errors.append(
                        f"slow_test: {rel} calls {rendered}; tests must not sleep"
                    )
                    continue
                if full in {"time.time", "time.monotonic", "time.perf_counter"}:
                    rel = p.relative_to(project_dir)
                    rendered = ast.get_source_segment(source, node) or f"{full}()"
                    errors.append(
                        f"slow_test: {rel} calls {rendered}; inject a clock or use "
                        "fixed timestamps in tests"
                    )
                    continue
                if isinstance(node.func, ast.Attribute) and node.func.attr in {
                    "assertGreater", "assertGreaterEqual", "assertTrue"
                }:
                    text = ast.get_source_segment(source, node) or ""
                    if any(term in text for term in ("elapsed", "time.time", "seconds")):
                        rel = p.relative_to(project_dir)
                        errors.append(
                            f"slow_test: {rel} asserts wall-clock timing; "
                            "tests must be fast and deterministic"
                        )
    return errors


def _entry_static_errors(project_dir: Path, script: Path) -> list[str]:
    """Fail obvious slow or non-terminating demos before subprocess timeout."""
    try:
        source = script.read_text()
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    rel = script.relative_to(project_dir)
    errors = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                owner = getattr(node.func.value, "id", "")
                full = f"{owner}.{node.func.attr}" if owner else node.func.attr
            elif isinstance(node.func, ast.Name):
                full = node.func.id
            else:
                full = ""
            if full in {"time.sleep", "sleep"}:
                rendered = ast.get_source_segment(source, node) or f"{full}(...)"
                errors.append(
                    f"slow_entry: {rel} calls {rendered}; entry points must "
                    "demonstrate quickly without sleeping"
                )
        elif isinstance(node, ast.While):
            if isinstance(node.test, ast.Constant) and node.test.value is True:
                errors.append(
                    f"slow_entry: {rel} contains while True; entry points must terminate"
                )
    return errors


def _import_check(project_dir: Path, written: list[Path], timeout: float, allow_network: bool) -> list[str]:
    """Execute each written src module in the sandbox (runpy, not __main__).
    Catches what compile-check can't: missing imports, module-level NameErrors,
    broken cross-module imports. Without this, a project with no entry point
    gets zero execution feedback and the loop builds on broken foundations."""
    errors = []
    for p in written:
        if p.suffix != ".py":
            continue
        rel = p.relative_to(project_dir)
        if rel.parts[0] != "src":
            continue
        code = (
            "import sys, runpy; sys.path.insert(0, 'src'); "
            f"runpy.run_path({str(rel)!r})"
        )
        rc, out = run_sandboxed(project_dir, [sys.executable, "-c", code], timeout, allow_network)
        if rc != 0:
            errors.append(f"{rel}: import/exec failed: {_failure_excerpt(out, 1500)}")
    return errors


def _run_entry(project_dir: Path, script: Path, timeout: float, allow_network: bool) -> list[str]:
    rc, out = run_sandboxed(
        project_dir,
        [sys.executable, str(script.relative_to(project_dir))],
        timeout, allow_network,
    )
    if rc != 0:
        return [f"{script.name}: exit {rc}: {_failure_excerpt(out, 1500)}"]
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
        return ran, [f"tests: exit {rc}: {_failure_excerpt(out)}"]
    return ran, []


def run_acceptance(project_dir: Path, timeout: float, allow_network: bool) -> tuple[bool | None, int]:
    """Run the held-out acceptance suite (acceptance/test_*.py), if present.
    Returns (passed, tests_ran); passed=None when there is no suite. Kept
    separate from validate() — acceptance failing mid-build is expected; it
    gates verify_done, not commits."""
    if not list((project_dir / "acceptance").glob("test_*.py")):
        return None, 0
    init_py = project_dir / "acceptance" / "__init__.py"
    if not init_py.exists():
        init_py.touch()
    rc, out = run_sandboxed(
        project_dir,
        [sys.executable, "-m", "unittest", "discover", "-s", "acceptance", "-t", "."],
        timeout, allow_network,
    )
    m = re.search(r"Ran (\d+) tests?", out)
    ran = int(m.group(1)) if m else 0
    return rc == 0, ran


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
        errors = _import_check(project_dir, written_files, timeout, allow_network)
        if any(p.suffix == ".py" and p.relative_to(project_dir).parts[0] == "src"
               for p in written_files):
            detail_parts.append("import-check")
    if not errors:
        entry = _entry_point(project_dir)
        if entry is not None:
            errors = _entry_static_errors(project_dir, entry)
            if not errors:
                errors = _run_entry(project_dir, entry, timeout, allow_network)
            detail_parts.append(f"ran {entry.relative_to(project_dir)}")
        if run_tests:
            slow_errors = _slow_test_errors(project_dir)
            if slow_errors:
                errors.extend(slow_errors)
            else:
                tests_ran, tests_failed = _run_tests(project_dir, timeout, allow_network)
                if tests_ran or tests_failed:
                    detail_parts.append(f"{tests_ran} tests")
                errors.extend(tests_failed)
    first_error = errors[0] if errors else ""
    failure_kind = ""
    if errors:
        if "timed out after" in first_error:
            failure_kind = "timeout"
        elif first_error.startswith("slow_entry:"):
            failure_kind = "slow_entry"
        elif first_error.startswith("slow_test:"):
            failure_kind = "slow_test"
        elif first_error.startswith("tests:"):
            failure_kind = "tests"
        elif "import/exec failed" in first_error:
            failure_kind = "import"
        elif "exit " in first_error:
            failure_kind = "entry"
        else:
            failure_kind = "compile"
    return ValidationResult(
        passed=not errors,
        detail=" + ".join(detail_parts),
        errors=errors,
        tests_ran=tests_ran,
        tests_failed=tests_failed,
        failure_kind=failure_kind,
        error_excerpt=_failure_excerpt(first_error),
        error_signature=_signature(first_error),
    )
