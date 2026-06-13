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
{contract_section}
{tasks_section}{notes_section}
CURRENT CODEBASE:
{codebase}
{changes_section}
AVAILABLE TOOLS (helper scripts in tools/ that the executor can run):
{tools}

HISTORY (most recent iterations of this loop):
{history}
{mode_instructions}
Given the goal, the current codebase, and the history of what has already been
done, what is the single most useful next step?"""

TASKS_SECTION = """
TASK LIST (work through the open tasks; the harness marks them done):
{tasks}

Begin your reply with `TASK Tn:` naming which open task this step advances,
then the instruction. Example: `TASK T3: Implement the move logic in src/mover.py`
Only choose the eligible next task. Do not choose queued, done, or deferred tasks.
"""

CONTRACT_SECTION = """
PROJECT CONTRACT (stable source of truth):
{contract}
"""

NOTES_SECTION = """
NOTES (persistent observations from earlier iterations):
{notes}
"""

CHANGES_SECTION = """
WHAT CHANGED LAST ITERATION (git diff):
{changes}
"""

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

NO_TESTS_NOTE = """
NOTE: the project currently has NO tests. Untested code keeps accumulating
errors. Strongly consider making the next step (or a near-future step) writing
tests in tests/ for the existing code."""

STUCK_NUDGE = """
WARNING: the loop appears stuck. Detected pattern(s):
{signals}
Propose a DIFFERENT next step that breaks this pattern and makes new
progress toward the goal."""

TASK_ELIGIBILITY_NUDGE = """

The proposed step targeted an ineligible or unknown task:
{reason}

Choose exactly one eligible open task from the task list and begin with
`TASK Tn:`. Do not target queued, done, or deferred tasks.
"""

DIAGNOSIS_SYSTEM = """\
You are the diagnosis step of an autonomous coding loop. Do not write code.
Given the current codebase, recent history, the failed sub-task, and validation
evidence, identify the root cause and the smallest safe patch plan. Reply with
exactly two lines:
CAUSE: <one concrete root cause>
PATCH_PLAN: <one concrete implementation plan>"""

DIAGNOSIS_USER = """\
GOAL:
{goal}

CURRENT CODEBASE:
{codebase}

PROJECT CONTRACT:
{contract}

HISTORY:
{history}

FAILED SUB-TASK:
{subtask}

VALIDATION EVIDENCE:
{errors}

If the failure is a timeout or slow test, the patch plan must make tests fast
and deterministic: avoid multi-second sleeps, inject clocks/sleep functions
where useful, and test rendering/update behavior separately from animation
timing.

Diagnose now."""

EXPLORE_NUDGE_A = """
THE LOOP IS HARD-STUCK: recent iterations keep failing the same way and a
rollback did not help. Ignore the failed approach entirely. Propose ONE next
step that takes a genuinely different approach to the current problem."""

EXPLORE_NUDGE_B = """
THE LOOP IS HARD-STUCK: recent iterations keep failing the same way and a
rollback did not help. Another planner already proposed this approach:
  {plan_a}
Propose ONE next step that takes a GENUINELY DIFFERENT approach from both the
failed history and the proposal above."""

DECOMPOSE_SYSTEM = """\
You are the decomposition step of an autonomous coding loop. You will be shown
a high-level goal. Break it into a short ordered list of concrete coding tasks
and a list of observable acceptance criteria. Do not write code. Reply with
only TASK: and CRITERION: lines — no preamble, no markdown headings."""

DECOMPOSE_USER = """\
GOAL:
{goal}

Break this goal down. Reply using EXACTLY this line format:

TASK: <one concrete coding step, one line>
CRITERION: <one observable, checkable statement about the finished program>

Rules:
- 5 to 12 TASK lines, in build order. Each must be small enough for one
  iteration of work (one or two files).
- The first task should create the program's entry point in src/.
- 3 to 8 CRITERION lines. Each must be checkable by running the program or
  its tests (e.g. "running `python src/main.py --help` exits 0 and prints usage").
- Tasks and criteria must stay within the harness sandbox: source in src/,
  tests in tests/, helper scripts in tools/. Do not require virtualenvs,
  activation, package installs, root-level files, flake8, pytest, npm, pip,
  or any unavailable external tool unless the goal explicitly asks for it.
- Do not require generated files to be empty; useful entry points and modules
  should contain behavior.
- Entry points and demos must be bounded and fast: no sleeps, infinite loops,
  long animations, or waiting for user input unless the goal explicitly asks.
- One line per task/criterion. No other text."""

DECOMPOSE_RETRY_NOTE = """

Your previous decomposition included work the harness cannot safely execute:
{rejections}

Try again. Replace those items with concrete stdlib-only coding or unittest
tasks inside src/, tests/, or tools/. Do not mention the rejected setup/tooling.
"""

TASK_CHECK_SYSTEM = """\
You are a strict completion checker for an autonomous coding loop. You will be
shown a codebase and one task. Decide if the task is FULLY complete in the
code shown. First line of your reply must be exactly YES or NO, then one
sentence of reasoning."""

TASK_CHECK_USER = """\
CURRENT CODEBASE:
{codebase}

PROJECT CONTRACT:
{contract}

TASK:
T{num}: {text}

Is this task fully complete in the codebase above? First line: YES or NO.
Then one sentence why."""

ACCEPTANCE_TEST_SYSTEM = """\
You write held-out acceptance tests for an autonomous coding loop. You will be
shown a goal. Write ONE complete unittest file that checks the finished
program's observable behavior by running it as a subprocess (the program's
entry point will be src/main.py). Reply with exactly one file block:

FILE: acceptance/test_acceptance.py
```python
<complete file contents>
```

Rules:
- Plain `unittest` + `subprocess` + stdlib only.
- Run the program via `[sys.executable, 'src/main.py', ...]` with
  capture_output=True; never import src modules directly.
- Tests must be specific to the goal's observable behavior, but tolerant of
  reasonable implementation choices (exact wording, ordering).
- 3 to 6 test methods. Use temp dirs for any file fixtures."""

ACCEPTANCE_TEST_USER = """\
GOAL:
{goal}

Write the acceptance test file now."""

CRITIC_SYSTEM = """\
You are the review step of an autonomous coding loop. You will be shown the
sub-task that was attempted, the diff it produced, and the validation result.
Judge whether the change should be accepted as-is. Reply with EXACTLY:

VERDICT: ACCEPT
or
VERDICT: REVISE
ISSUE: <one concrete problem, one line>          (1 to 3 ISSUE lines)

Only answer REVISE for real defects (wrong behavior, lost functionality,
broken contract with the rest of the code) — not style preferences."""

CRITIC_USER = """\
SUB-TASK ATTEMPTED:
{subtask}

DIFF PRODUCED:
{diff}

VALIDATION RESULT:
{validation}

Judge the change now (VERDICT line, then ISSUE lines only if REVISE)."""

REPAIR_NOTE = """

YOUR PREVIOUS ATTEMPT AT THIS SUB-TASK FAILED VALIDATION.

Files relevant to this failure (current contents; includes traceback-referenced files):
{files}

Validation errors:
{errors}

Fix exactly these errors now while preserving the PROJECT CONTRACT. Prefer
implementation fixes over weakening tests. Edit tests only if they are
nondeterministic, contradict the contract, or assert the wrong behavior.
The PROJECT CONTRACT overrides any test expectation that contradicts it.
Rewrite the broken file(s) completely, changing as little else as possible.
Same output format (SUMMARY + FILE blocks)."""

REVISE_NOTE = """

A REVIEWER FLAGGED PROBLEMS with your previous attempt at this sub-task:
{issues}
Redo the sub-task fixing these issues. Same output format."""

VERIFY_DONE_SYSTEM = """\
You are the final verification step of an autonomous coding loop. You will be
shown a goal, the codebase, validation results, and a list of acceptance
criteria. For EACH criterion, reply with exactly one line:
PASS: Cn
or
FAIL: Cn — <one short reason>
No other text."""

VERIFY_DONE_USER = """\
GOAL:
{goal}

CURRENT CODEBASE:
{codebase}

PROJECT CONTRACT:
{contract}

HARNESS VALIDATION RESULT:
{validation}

ACCEPTANCE CRITERIA:
{criteria}

For each criterion, one PASS/FAIL line. Be strict: if you cannot see clear
evidence in the code that a criterion is met, mark it FAIL."""

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
4. Optionally, up to two lines of the form `NOTE: <one line worth remembering>`
   — these persist across iterations (e.g. design decisions, gotchas found).

Rules:
- File paths must be relative and inside `src/`, `tests/`, or `tools/` only.
- Rewrite whole files; partial edits are not supported.
- Helper scripts in tools/ must have a module docstring whose first line
  describes what the tool does.
- RUN_TOOL may only name an existing listed helper script exactly. Never use
  external commands such as pytest, flake8, npm, pip, or shell commands as
  RUN_TOOL names.
- Tests must be fast, deterministic, stdlib-only unittest tests. Do not write
  tests that call time.sleep(), time.time(), or time.monotonic(); inject clocks
  or use fixed numeric timestamps. Do not require pytest/flake8 or assert
  wall-clock timing.
- Entry points and demos must terminate quickly. Do not use time.sleep(),
  infinite loops, long animations, or interactive input unless the goal
  explicitly requires them.
- Follow the PROJECT CONTRACT. Do not duplicate canonical implementations.
- Prefer implementation fixes over weakening tests. Edit tests only when they
  are nondeterministic, contradict the contract, or assert the wrong behavior.
  The PROJECT CONTRACT overrides contradictory expected values in tests."""

EXECUTOR_USER = """\
GOAL:
{goal}
{contract_section}
{notes_section}
CURRENT CODEBASE:
{codebase}

AVAILABLE TOOLS (runnable via RUN_TOOL):
{tools}

SUB-TASK FOR THIS ITERATION:
{subtask}

Implement the sub-task now, using the SUMMARY + FILE block format."""
