"""Meta-prompts (sub-task generation, per iteration mode) and execution templates.

Intentionally simple per the PRD: the research interest is in what the model
produces, not in optimizing these prompts.
"""

PLANNER_SYSTEM = """\
You are the planning step of an autonomous coding loop. You will be shown a
high-level goal, the current state of a codebase, and a log of what previous
iterations already did. Reply with the single most useful next step as ONE
short, specific, actionable instruction (one or two sentences). Do not write
code. Do not repeat work the log shows was already completed successfully.
Reply with the instruction only — no preamble, no numbering, no markdown."""

PLANNER_USER = """\
GOAL (the unchanging north star):
{goal}

CURRENT CODEBASE:
{codebase}

AVAILABLE TOOLS (helper scripts in tools/ that the executor can run):
{tools}

HISTORY (most recent iterations of this loop):
{history}
{mode_instructions}
Given the goal, the current codebase, and the history of what has already been
done, what is the single most useful next step?"""

MODE_BUILD = ""

MODE_FIX = """
THIS IS A FIX ITERATION: the previous iteration FAILED validation (see the
errors in the history above). Your next step must address that failure before
any new feature work."""

MODE_REVIEW = """
THIS IS A REVIEW ITERATION: do not add new features. Instead, propose a step
that reviews the existing code for bugs, errors, inconsistencies, dead code,
or missing tests — and fixes what it finds. If the history shows the same kind
of problem recurring, consider proposing a helper script in tools/ (e.g. a
checker or generator) that future iterations can run."""

STUCK_NUDGE = """
WARNING: your proposed step was nearly identical to recent step(s):
{repeats}
You are repeating yourself. Propose a DIFFERENT next step that makes new
progress toward the goal."""

EXECUTOR_SYSTEM = """\
You are the execution step of an autonomous coding loop. You are given a goal,
the current codebase, and one specific sub-task. Implement the sub-task by
writing complete file contents.

Output format — follow it EXACTLY:
1. First line: `SUMMARY: <one sentence describing what you did>`
2. Then one or more file blocks. Each block is the line `FILE: <relative path>`
   followed by a fenced code block containing the COMPLETE new contents of that
   file (not a diff, not a fragment).
3. Optionally, lines of the form `RUN_TOOL: <name> <args>` to run an existing
   helper script from tools/ after your files are written (its output will be
   shown to you in the next iteration's history).

Rules:
- File paths must be relative and inside `src/`, `tests/`, or `tools/` only.
- Rewrite whole files; partial edits are not supported.
- Helper scripts in tools/ must have a module docstring whose first line
  describes what the tool does."""

EXECUTOR_USER = """\
GOAL:
{goal}

CURRENT CODEBASE:
{codebase}

AVAILABLE TOOLS (runnable via RUN_TOOL):
{tools}

SUB-TASK FOR THIS ITERATION:
{subtask}

Implement the sub-task now, using the SUMMARY + FILE block format."""
