# 9xf loops v0.4

A research harness for autonomous, self-prompting coding loops. You give it a
one-time goal; it then repeatedly reads its own codebase and history, generates
its own next sub-task, writes code, validates it, and commits — with no human in
the loop. The research artifact is the git history plus `loop_log.jsonl`.

v0.3 shifted the harness from pure observation toward **goal completion**: the
goal is decomposed into a task list, progress is tracked per task, the loop can
recover from regressions (auto-revert) and hard-stuck states (branch-and-explore),
and a run can FINISH — verified against held-out acceptance criteria — instead
of only hitting the iteration cap.

v0.4 turns the harness into an **overnight engine**: the bet is that a small
local model (7B) plus hours of verified search can approach big-model output
quality — trading time, which is free, for API spend, which isn't. New: an
in-iteration repair loop (validation errors fed straight back to the executor),
best-state checkpointing (`keep_best` — the run ships the best state it ever
reached, not the last one), wall-clock budgets (`9xf run --hours 8`), and an
`--preset overnight` that turns every search mechanism on at once. Every
mechanism remains logged and toggleable, so earlier behavior stays reproducible
as the control in A/B runs.

Built per the LoopForge research PRD. Pure Python stdlib — no pip dependencies.

## Quick start

```bash
# install the `9xf` command (or skip and use `python3 -m ninexf` from this repo)
pip install -e .

# create a run (local model via Ollama is the default)
9xf init --goal "Write a CLI tool that organizes files by type" \
         --model ollama/qwen2.5-coder:7b --dir ~/runs/organizer

# start the loop
9xf run --dir ~/runs/organizer --max-iterations 20 --delay 30

# observe
9xf status --dir ~/runs/organizer
9xf log    --dir ~/runs/organizer
9xf watch  # live dashboard for all registered runs (opens browser)
9xf report --dir ~/runs/organizer  # generates REPORT.md
git -C ~/runs/organizer log --oneline

# stop gracefully (or Ctrl+C the running loop — same clean shutdown)
9xf stop --dir ~/runs/organizer
```

## Overnight mode (v0.4)

The democratization thesis: frontier-model quality is mostly *verified search*,
and a harness can supply the search even when the model is small. A 7B model's
first attempt is weak; its hundredth validated, repaired, critic-reviewed,
best-of-N-selected attempt — measured against held-out acceptance tests, with
the best state ever reached checkpointed — is a different animal. You pay in
hours instead of dollars.

```bash
# set it up before bed
9xf init --goal "Write a CLI tool that organizes files by type" \
         --preset overnight --dir ~/runs/organizer

# 8 hours of verified search, then a clean shutdown
9xf run --dir ~/runs/organizer --hours 8

# in the morning: the best state the run ever reached, plus the full story
9xf status --dir ~/runs/organizer
9xf report --dir ~/runs/organizer
```

What `--preset overnight` turns on (each independently configurable):

- **In-iteration repair** (`repair_attempts`, default 1; overnight 2): when an
  executor attempt fails validation, the broken file contents and the exact
  errors are fed straight back to the executor for an immediate fix — seconds,
  instead of a full re-plan round trip. Repairs are logged per iteration
  (`repairs`), so repair efficacy per model is itself research data.
- **Best-state checkpointing** (`keep_best`, default on): every committed state
  is scored — held-out acceptance first, then validation, task progress, test
  count — and at shutdown the working tree is restored to the best-ever state
  if the final one is worse (`restore_best` event). This makes overnight wall
  time strictly additive: a run can wander at 3am without costing you the
  thing it built at 1am.
- **Wall-clock budget** (`max_hours` config or `9xf run --hours 8`): the loop
  stops cleanly at the deadline, whichever comes first against the iteration cap.
- **Maximum search**: best-of-3 candidates on *every* iteration (not just fix
  mode), the critic reviewing every passing diff, branch-and-explore enabled
  with a higher episode cap, and held-out acceptance tests generated at init.

Recommended overnight pairing: `ollama/qwen2.5-coder:7b` with `num_ctx` raised
to 32768 in `9xf.config.json` if you have the RAM — context truncation is the
quiet killer of long runs.

## How an iteration works

1. Read `goal.txt` (never modified by the agent)
2. Snapshot the codebase (file tree + `src/`, `tests/`, and `tools/` contents,
   trimmed to `context_char_budget`; what got trimmed is noted in the prompt)
3. Read recent `loop_log.jsonl` history
4. **Planner call** — the meta-prompt asks for the single most useful next step
5. **Executor call** — the model returns `SUMMARY:` + `FILE:` blocks with
   complete file contents (plain text, not JSON — far more reliable for 7B
   local models). Optionally emits `RUN_TOOL: <name> <args>` to run helper
   scripts from `tools/`.
6. Validate: `py_compile` every written file, run the entry point, then run
   `python -m unittest discover -s tests -t .` if tests exist. A failed
   validation triggers up to `repair_attempts` immediate repair calls — the
   errors and broken file contents go straight back to the executor (v0.4)
7. Commit — **failed attempts are committed too**; failures are research data
8. Append the JSONL log entry (also committed, so log and history stay in sync)
9. Sleep, repeat

## Goal completion (v0.3)

The loop's state machine:

```
init ─► decompose (iter 1, 1 LLM call) ─► build ◄────────────┐
              prev failed: ─► fix                             │
              every review_every: ─► review                   │
   N consec failures ─► [auto-revert to last green] ─► build  │
   hard-stuck ─► [branch-explore, adopt winner] ─► build      │
   all tasks [x]/[!] ─► verify_done ── any FAIL (new tasks) ──┘
                              └── all PASS + harness green ─► FINISHED
```

- **Decomposition**: iteration 1 breaks the goal into `TASKS.md` (checkbox task
  list) and `ACCEPTANCE.md` (observable criteria). Both are harness-managed and
  agent-read-only. The planner names which task each step advances (`TASK Tn:`);
  the harness marks tasks done only after a green iteration plus a YES from a
  one-line completion check. Tasks failing `max_task_failures` times are
  deferred (`[!]`) so the loop stops grinding.
- **Verify-done & FINISHED**: when all tasks are resolved, the harness runs full
  validation + the held-out acceptance suite, then asks the model for a
  per-criterion PASS/FAIL. The model can only *block* finishing, never force it
  — finishing requires the harness checks green too. Failures append corrective
  tasks and the loop resumes building.
- **Auto-revert**: after `revert_after_failures` consecutive failures the
  working dirs are restored to the last green commit (by path checkout — git
  history stays linear). Capped at 2 reverts to the same commit, then the
  failing task is deferred instead.
- **Stuck detection v2**: four signals — `repeat` (similar subtask), 
  `oscillation` (A-B-A), `no_writes`, `same_error` (normalized error signature
  recurring) — each logged in `stuck_signals` and answered with a
  signal-specific re-plan nudge.
- **Smart context**: `context_strategy: "relevance"` scores files against the
  current subtask (mentions, recent errors, recent writes, import-graph
  neighbors, token overlap) and fills the budget by score; over-budget files
  keep a one-line def/class stub. A `WHAT CHANGED LAST ITERATION` git diff and
  a persistent `NOTES.md` (agent `NOTE:` lines + harness observations,
  FIFO-capped) round out the model's memory. `"brute"` restores v0.2 behavior.
- **Held-out acceptance tests**: `9xf init --acceptance-tests` generates
  `acceptance/test_acceptance.py` from the goal at init. The agent can't write
  it and never sees its contents — only the criteria text. It gates
  verify_done, not commits.
- **Critic** (`critic_enabled`): a passing change's diff is reviewed before
  commit (`VERDICT: ACCEPT|REVISE` + `ISSUE:` lines); REVISE triggers one
  re-execution with the issues attached.
- **Best-of-N** (`best_of_n` > 1): sample N executor candidates at varied
  temperatures, validate each (restoring the tree in between), commit the best.
  Defaults to fix-mode only (`best_of_mode: "fix"`) — local-model latency is real.
- **Branch-and-explore** (`explore_enabled`): when stuck signals persist *after*
  a revert, two genuinely different approaches are tried on git branches; the
  winner is adopted on main by file checkout, the loser kept as
  `explore-iN-x-rejected`. The JSONL log is written only on the main branch.

## Smarter loop core (v0.2)

- **Iteration modes**: `build` (default), `fix` (previous iteration failed),
  `review` (every `review_every` iterations, default 5). The mode is passed to
  the planner and prefixed in commit messages.
- **Stuck detection**: compares each new subtask against the last 5 via
  `difflib.SequenceMatcher` (>0.85 similarity = repeat). On repeat, the
  planner is re-asked once with an anti-repetition nudge; the event is logged
  as `stuck_detected: true`.
- **Regression flagging**: if an iteration that previously passed now fails,
  `regression: true` is set and an explicit notice appears in the next
  iteration's history context.
- **Test execution**: if `tests/test_*.py` exist, unittest discovery runs in
  the same sandboxed subprocess as validation. Results appear in the log as
  `tests_ran` and `tests_failed`.

## Self-created tools

The agent can write helper scripts under `tools/` (same sandbox as `src/` and
`tests/`). They are discovered automatically, listed in planner/executor
prompts, and can be invoked via `RUN_TOOL: <name> <args>` lines in the
executor output. Tool runs are capped at `max_tool_runs_per_iteration`
(default 3) and their output tails feed back into the next iteration's
history — so the loop can learn from its own helpers.

## Containment

- Writes are only allowed under `src/`, `tests/`, and `tools/`. Every
  model-supplied path is resolved and checked; escapes (`../`, absolute paths,
  symlinks, `.git/`, protected files) are rejected and logged as `violation`
  events.
- `STOP` file anywhere in the project folder → clean shutdown (commit, log,
  exit) at the next iteration boundary. `Ctrl+C` does the same; a second
  `Ctrl+C` force-quits.
- Iteration cap (default 50) and per-run validation timeout (default 10s).
- Network is off by default for validated code: on macOS the validation
  subprocess is wrapped in `sandbox-exec` with a deny-network profile
  (best-effort — falls back to a stripped-env run if unavailable). Opt in with
  `9xf init --allow-network`. Note: the *model* backend obviously needs to
  reach Ollama/the API; the restriction applies to the code the agent runs.
- Three consecutive backend failures → clean shutdown (so a dead Ollama server
  doesn't spin forever).

## Models

Set in `9xf.config.json` (written at init, never modified by the agent):

- `ollama/<model>` — local, default (`ollama/qwen2.5-coder:7b`); endpoint
  configurable via `endpoint`
- `anthropic/<model>` — API mode for comparison runs; reads the key from the
  env var named by `api_key_env` (default `ANTHROPIC_API_KEY`)
- `mock` — deterministic scripted backend for testing the harness itself.
  Scenario variants drive specific harness paths: `mock/finisher` (runs to
  FINISHED), `mock/regressor` (forces auto-revert), `mock/explorer` (forces
  branch-and-explore), `mock/repairer` (forces the in-iteration repair loop)

## Testing the harness

```bash
python3 -m unittest discover -s tests -t .
```

End-to-end scenario tests run real loops in temp dirs against the mock
scenarios and assert on `loop_log.jsonl` + git; unit tests cover the task-list,
stuck-signal, relevance-scoring, and candidate/critic parsers.

## Project folder layout (per run)

```
goal.txt              set at init, never modified
9xf.config.json       model, delay, max iterations, budgets, v0.3 toggles
TASKS.md              harness-managed task list (agent-read-only)
ACCEPTANCE.md         harness-managed acceptance criteria (agent-read-only)
NOTES.md              persistent notes (agent NOTE: lines + harness events)
acceptance/           held-out acceptance tests (agent can't write or read contents)
loop_log.jsonl        append-only, one entry per iteration
state.json            heartbeat written every iteration (dashboard reads this)
STOP                  create to trigger graceful shutdown
REPORT.md             generated by `9xf report` (excluded from agent context)
src/  tests/  tools/  the only writable dirs for the agent
.git/                 the primary research artifact
```

## Repo layout (the harness)

```
ninexf/
  cli.py        9xf init|run|status|stop|log|watch|report
  loop.py       the iteration loop + state machine (decompose/build/fix/review/
                verify_done) + revert/explore orchestration
  tasks.py      TASKS.md + ACCEPTANCE.md (decomposition, task state, verify parsing)
  stuck.py      multi-signal stuck detection (repeat/oscillation/no_writes/same_error)
  relevance.py  relevance-scored context selection (mentions/errors/imports/overlap)
  candidates.py best-of-N candidate scoring + critic verdict parsing
  explore.py    branch-and-explore trigger logic
  fitness.py    best-state scoring + keep_best restore decision (v0.4)
  backends.py   ollama / anthropic / mock (+ mock/<scenario> variants)
  prompts.py    planner/executor/decompose/verify/critic/acceptance prompts
  parser.py     SUMMARY/FILE-block/RUN_TOOL/NOTE parsing
  sandbox.py    write-path containment
  validate.py   compile check + entry-point run + unittest + acceptance suite
  context.py    codebase snapshot + history windowing + diff context + NOTES.md
  gitops.py     subprocess git wrapper (commits, restore, branches, staged diff)
  looplog.py    JSONL log read/append
  config.py     9xf.config.json load/write
  tools.py      agent-created helper script discovery + execution
  dashboard.py  `9xf watch` — multi-run local dashboard (stdlib http.server)
  report.py     `9xf report` — generates the observation report
  registry.py   ~/.9xf/registry.json + per-run state.json heartbeats
tests/          harness test suite (end-to-end mock scenarios + unit tests)
```
