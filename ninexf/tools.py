"""Agent-created tools: helper scripts the agent writes into tools/ and can
ask to run in later iterations.

A tool is any tools/*.py file. Its name is the filename stem; its description
is the first line of the module docstring (or a fallback). Tools run in the
same stripped-env / timeout / deny-network subprocess as validation. What the
agent builds for itself, and whether it ever uses it, is research data.
"""

from __future__ import annotations

import ast
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from ninexf.validate import run_sandboxed


@dataclass
class Tool:
    name: str
    path: Path
    description: str


def discover_tools(project_dir: Path) -> list[Tool]:
    tools_dir = project_dir / "tools"
    if not tools_dir.is_dir():
        return []
    tools = []
    for p in sorted(tools_dir.glob("*.py")):
        desc = "(no docstring)"
        try:
            doc = ast.get_docstring(ast.parse(p.read_text()))
            if doc:
                desc = doc.strip().splitlines()[0]
        except (SyntaxError, OSError, UnicodeDecodeError):
            desc = "(unparseable)"
        tools.append(Tool(name=p.stem, path=p, description=desc))
    return tools


def tools_for_prompt(project_dir: Path) -> str:
    tools = discover_tools(project_dir)
    if not tools:
        return "(none yet — you may create helper scripts in tools/ if they would help)"
    return "\n".join(f"- {t.name}: {t.description}" for t in tools)


def run_tool(
    project_dir: Path,
    name: str,
    args: str,
    timeout: float,
    allow_network: bool,
    max_output: int = 2000,
) -> str:
    """Run a named tool with shell-style args. Returns a human-readable result
    string (also fed back into the agent's context next iteration)."""
    tool = next((t for t in discover_tools(project_dir) if t.name == name), None)
    if tool is None:
        return f"tool {name!r} not found"
    try:
        extra = shlex.split(args) if args else []
    except ValueError as e:
        return f"tool {name!r}: bad arguments: {e}"
    rc, out = run_sandboxed(
        project_dir,
        [sys.executable, str(tool.path.relative_to(project_dir)), *extra],
        timeout, allow_network,
    )
    status = "ok" if rc == 0 else f"exit {rc}"
    out = out[-max_output:] if out else "(no output)"
    return f"[{status}] {out}"
