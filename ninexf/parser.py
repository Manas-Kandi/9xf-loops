"""Parse the executor's SUMMARY + FILE-block output format.

Local models are unreliable at strict JSON, so the contract is plain text:

    SUMMARY: did a thing
    FILE: src/foo.py
    ```python
    ...complete file contents...
    ```

The parser is deliberately forgiving about whitespace, fence language tags,
and stray prose between blocks — malformed output is itself research data,
so parse failures are reported, not crashed on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FILE_BLOCK_RE = re.compile(
    r"FILE:\s*(?P<path>[^\n`]+?)\s*\n+\s*```[a-zA-Z0-9_+-]*\n(?P<body>.*?)\n?```",
    re.DOTALL,
)
SUMMARY_RE = re.compile(r"SUMMARY:\s*(?P<summary>[^\n]+)")
RUN_TOOL_RE = re.compile(r"^RUN_TOOL:\s*(?P<name>[\w.-]+)\s*(?P<args>[^\n]*)$", re.MULTILINE)


@dataclass
class ParsedOutput:
    summary: str = ""
    files: dict[str, str] = field(default_factory=dict)
    tool_runs: list[tuple[str, str]] = field(default_factory=list)  # (name, args)
    problems: list[str] = field(default_factory=list)


def parse_executor_output(text: str) -> ParsedOutput:
    out = ParsedOutput()

    m = SUMMARY_RE.search(text)
    out.summary = m.group("summary").strip() if m else ""
    if not out.summary:
        out.problems.append("no SUMMARY line found")

    for m in FILE_BLOCK_RE.finditer(text):
        path = m.group("path").strip().strip("'\"")
        body = m.group("body")
        if path in out.files:
            out.problems.append(f"duplicate FILE block for {path}; last one wins")
        out.files[path] = body + ("\n" if not body.endswith("\n") else "")

    # RUN_TOOL lines outside code fences (strip fenced regions before scanning,
    # so tool source code mentioning RUN_TOOL doesn't trigger runs)
    unfenced = FILE_BLOCK_RE.sub("", text)
    for m in RUN_TOOL_RE.finditer(unfenced):
        out.tool_runs.append((m.group("name").strip(), m.group("args").strip()))

    if not out.files and not out.tool_runs:
        out.problems.append("no FILE blocks found in model output")

    return out
