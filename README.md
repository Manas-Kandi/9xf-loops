# 9xf loops v0.2

A research harness for autonomous, self-prompting coding loops. You give it a
one-time goal; it then repeatedly reads its own codebase and history, generates
its own next sub-task, writes code, validates it, and commits — with no human in
the loop. The research artifact is the git history plus `loop_log.jsonl`.

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
   `python -m unittest discover -s tests -t .` if tests exist
7. Commit — **failed attempts are committed too**; failures are research data
8. Append the JSONL log entry (also committed, so log and history stay in sync)
9. Sleep, repeat

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
- `mock` — deterministic scripted backend for testing the harness itself

## Project folder layout (per run)

```
goal.txt              set at init, never modified
9xf.config.json       model, delay, max iterations, budgets
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
  loop.py       the iteration loop + mode scheduler + stuck/regression detection
  backends.py   ollama / anthropic / mock
  prompts.py    planner meta-prompt + executor format contract + mode variants
  parser.py     SUMMARY/FILE-block/RUN_TOOL parsing
  sandbox.py    write-path containment
  validate.py   compile check + entry-point run + unittest discovery
  context.py    codebase snapshot + history windowing (includes regression notices)
  gitops.py     subprocess git wrapper
  looplog.py    JSONL log read/append
  config.py     9xf.config.json load/write
  tools.py      agent-created helper script discovery + execution
  dashboard.py  `9xf watch` — multi-run local dashboard (stdlib http.server)
  report.py     `9xf report` — generates PRD §12 observation report
  registry.py   ~/.9xf/registry.json + per-run state.json heartbeats
```
