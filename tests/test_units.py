"""Unit tests for the v0.3/v0.4 modules: tasks, stuck, relevance, candidates,
parser, fitness, config presets."""

from __future__ import annotations

import os
import io
import tempfile
import subprocess
import urllib.error
import unittest
from pathlib import Path
from unittest import mock

from ninexf.backends import (
    BackendError, MistralBackend, NvidiaBackend, OllamaBackend, _post_json,
    context_overflowed, is_rate_limit_error,
)
from ninexf.candidates import CandidateResult, parse_critic_output, pick_winner
from ninexf.config import PRESETS, Config, load_config, load_dotenv, write_config
from ninexf.contract import contract_for_prompt, save_contract
from ninexf.dashboard import _run_status
from ninexf.fitness import best_state, final_state, fitness_of
from ninexf.loop_common import ExecOutcome, _repair_file_dump, note_contradicted
from ninexf.models import (
    DEFAULT_MODEL,
    GPT_OSS_20B_MODEL,
    MISTRAL_SMALL_MODEL,
    NVIDIA_GEMMA_MODEL,
    NVIDIA_KIMI_MODEL,
    NVIDIA_QWEN_NEXT_MODEL,
    model_options,
)
from ninexf.relevance import render_partial
from ninexf.parser import parse_executor_output
from ninexf.prompts import DECOMPOSE_USER, EXECUTOR_SYSTEM, PLANNER_SYSTEM, REPAIR_NOTE
from ninexf.relevance import score_files
from ninexf.stuck import detect_signals, normalize_error
from ninexf.webapp import DIAGNOSTIC_BUNDLE_FILENAME, export_diagnostic_bundle, start_run
from ninexf.tasks import (
    Task, TaskList, load_tasks, parse_decomposition, parse_task_ref,
    parse_task_ref_num, parse_task_refs, parse_verify_output, sanitize_decomposition,
    save_tasks, strip_task_ref, tasks_for_prompt, infer_task_ids_for_files,
    fallback_decomposition,
    task_has_any_file_evidence, task_has_file_evidence, task_is_corrective,
    task_needs_model_check, corrective_task_resolved, refinement_task_resolved,
    append_tasks, canonical_validation_task,
)
from ninexf.tools import tool_result_failed
from ninexf.validate import validate


class TestTasks(unittest.TestCase):
    def test_roundtrip_and_unparsed_preserved(self):
        d = Path(tempfile.mkdtemp())
        tl = TaskList(tasks=[Task(1, "do a"), Task(2, "do b", "x")],
                      unparsed=["some stray line"])
        save_tasks(d, tl)
        back = load_tasks(d)
        self.assertEqual([(t.num, t.text, t.status) for t in back.tasks],
                         [(1, "do a", " "), (2, "do b", "x")])
        self.assertEqual(back.unparsed, ["some stray line"])
        self.assertEqual(back.counts(), (1, 2))
        self.assertFalse(back.all_resolved())

    def test_parse_decomposition_tolerant(self):
        tasks, criteria = parse_decomposition(
            "Here you go:\nTASK: one\n- TASK: two\n1. TASK: three\n"
            "CRITERION: c1\n* CRITERION: c2\nnoise\n")
        self.assertEqual(tasks, ["one", "two", "three"])
        self.assertEqual(criteria, ["c1", "c2"])

    def test_task_ref(self):
        tl = TaskList(tasks=[Task(3, "x"), Task(4, "deferred", "!")])
        self.assertEqual(parse_task_ref("TASK T3: do x", tl), 3)
        self.assertEqual(parse_task_ref("TASK 3: do x", tl), 3)
        self.assertEqual(parse_task_ref("TASK T9: unknown", tl), 0)
        self.assertEqual(parse_task_ref("TASK T4: deferred", tl), 0)
        self.assertEqual(parse_task_ref_num("TASK T4: deferred"), 4)
        self.assertEqual(parse_task_ref("just do x", tl), 0)
        self.assertEqual(strip_task_ref("TASK T3: do x"), "do x")

    def test_task_ref_rejects_queued_tasks(self):
        tl = TaskList(tasks=[Task(1, "first"), Task(2, "second")])
        self.assertEqual(parse_task_ref("TASK T2: second", tl), 0)
        self.assertEqual(parse_task_ref("TASK T1: first", tl), 1)

    def test_hybrid_task_refs_allow_adjacent_slice(self):
        tl = TaskList(tasks=[Task(1, "Create src/index.html"),
                             Task(2, "Create src/styles.css"),
                             Task(3, "Create src/script.js")])
        self.assertEqual(parse_task_refs("TASK T1-T3: build the UI slice", tl, "hybrid"),
                         [1, 2, 3])
        self.assertEqual(parse_task_refs("TASK T2: create CSS", tl, "strict"), [])

    def test_tasks_prompt_marks_deferred_ineligible(self):
        d = Path(tempfile.mkdtemp())
        save_tasks(d, TaskList(tasks=[Task(1, "open"), Task(2, "later"), Task(3, "blocked", "!")]))
        prompt = tasks_for_prompt(d)
        self.assertIn("Eligible next task", prompt)
        self.assertIn("T1 (open)", prompt)
        self.assertIn("T2 (queued, not eligible yet)", prompt)
        self.assertIn("T3 (deferred, not eligible)", prompt)

    def test_hybrid_tasks_prompt_is_a_roadmap(self):
        d = Path(tempfile.mkdtemp())
        save_tasks(d, TaskList(tasks=[Task(1, "Create src/index.html"), Task(2, "Create src/styles.css")]))
        prompt = tasks_for_prompt(d, "hybrid")
        self.assertIn("Task roadmap", prompt)
        self.assertIn("may span adjacent open tasks", prompt)

    def test_infer_task_ids_for_written_files(self):
        tl = TaskList(tasks=[Task(1, "Create src/index.html"),
                             Task(2, "Create src/styles.css"),
                             Task(3, "Create tests/test_dashboard.py")])
        self.assertEqual(infer_task_ids_for_files(tl, ["src/index.html", "src/styles.css"]),
                         [1, 2])

    def test_task_done_requires_written_file_evidence(self):
        task = Task(2, "Add the feature module.")
        self.assertTrue(task_has_file_evidence(
            task, ["src/feature.py"], "TASK T2: Add the feature module in src/feature.py."))
        self.assertFalse(task_has_file_evidence(
            task, ["src/main.py"], "TASK T2: Add the feature module in src/feature.py."))
        self.assertFalse(task_has_file_evidence(
            Task(4, "Refine src/index.html, src/styles.css, and src/script.js."),
            ["src/index.html"],
            "TASK T4: Refine src/index.html, src/styles.css, and src/script.js.",
        ))
        self.assertTrue(task_has_any_file_evidence(
            Task(4, "Refine src/index.html, src/styles.css, and src/script.js."),
            ["src/index.html"],
            "TASK T4: Refine src/index.html, src/styles.css, and src/script.js.",
        ))
        self.assertTrue(task_has_file_evidence(
            Task(4, "Refine src/index.html, src/styles.css, and src/script.js."),
            ["src/index.html", "src/styles.css", "src/script.js"],
            "TASK T4: Refine src/index.html, src/styles.css, and src/script.js.",
        ))
        self.assertTrue(task_has_file_evidence(
            Task(3, "Fix the acceptance assertion."), ["tests/test_main.py"],
            "TASK T3: Fix the acceptance assertion."))

    def test_task_needs_model_check_only_when_evidence_is_weak(self):
        self.assertFalse(task_needs_model_check(
            Task(1, "Create src/main.py with a greeting."),
            ["src/main.py"],
            "TASK T1: Create src/main.py with a greeting.",
        ))
        self.assertFalse(task_needs_model_check(
            Task(6, "Fix validation failures: frontend_static"),
            ["src/index.html", "src/script.js"],
            "TASK T6: Fix the chart rendering bug in src/script.js.",
        ))
        self.assertFalse(task_needs_model_check(
            Task(4, "Polish the dashboard interactions."),
            ["src/script.js"],
            "TASK T4: Improve the interactions.",
        ))

    def test_refinement_task_resolves_after_green_file_evidence(self):
        task = Task(4, "Refine src/index.html, src/styles.css, and src/script.js.")
        self.assertTrue(refinement_task_resolved(
            task,
            ["src/index.html"],
            [],
            [],
            "TASK T4: Improve src/index.html.",
        ))
        self.assertFalse(refinement_task_resolved(
            task,
            ["src/index.html"],
            [],
            ["product_warning: frontend_static: visible chart missing"],
            "TASK T4: Improve src/index.html.",
        ))

    def test_task_is_corrective(self):
        self.assertTrue(task_is_corrective(Task(6, "Fix validation failures: compile-check")))
        self.assertTrue(task_is_corrective(Task(8, "Resolve blocker frontend_static in src/index.html: missing stylesheet")))
        self.assertTrue(task_is_corrective(Task(7, "Fix acceptance criterion C1 (something)")))
        self.assertFalse(task_is_corrective(Task(2, "Create src/main.py")))

    def test_corrective_task_resolution_uses_current_validation_evidence(self):
        task = Task(6, "Fix validation failures: frontend_static: src/index.html: chart/graph language is present but no visible chart marks")
        self.assertFalse(corrective_task_resolved(
            task,
            [],
            ["frontend_static: src/index.html: chart/graph language is present but no visible chart marks"],
        ))
        self.assertTrue(corrective_task_resolved(
            task,
            [],
            ["product_warning: frontend_static: src/index.html: script src 'script.js' does not resolve"],
        ))

    def test_corrective_task_resolution_handles_resolve_blocker(self):
        task = Task(9, "Resolve blocker frontend_static in src/index.html: chart/graph language is present but no visible chart marks")
        self.assertFalse(corrective_task_resolved(
            task,
            [],
            ["frontend_static: src/index.html: chart/graph language is present but no visible chart marks"],
        ))
        self.assertTrue(corrective_task_resolved(
            task,
            [],
            ["product_warning: frontend_static: src/index.html: script src 'script.js' does not resolve"],
        ))

    def test_append_tasks_dedupes_open_task_text(self):
        d = Path(tempfile.mkdtemp())
        save_tasks(d, TaskList(tasks=[Task(1, "Fix validation failures: x", "~")]))
        nums = append_tasks(d, ["Fix validation failures: x"])
        self.assertEqual(nums, [1])
        self.assertEqual(len(load_tasks(d).tasks), 1)

    def test_canonical_validation_task_frontend_static(self):
        self.assertEqual(
            canonical_validation_task(
                "frontend_static: src/index.html: chart/graph language is present but no visible chart marks",
                "frontend_static",
            ),
            "Resolve blocker frontend_static in src/index.html: chart/graph language is present but no visible chart marks",
        )

    def test_sanitize_bad_decomposition(self):
        tasks, criteria, rejected = sanitize_decomposition(
            "Python progress bar",
            [
                "Create src/main.py",
                "Initialize a virtual environment in the project root",
                "Update `.gitignore`",
                "Add tests/test_main.py",
            ],
            [
                "Running `flake8 src` passes",
                "The file `src/main.py` is created and empty",
                "Running unittest discovery passes",
            ],
        )
        self.assertEqual(tasks, ["Create src/main.py", "Add tests/test_main.py"])
        self.assertEqual(criteria, ["Running unittest discovery passes"])
        self.assertGreaterEqual(len(rejected), 3)

    def test_sanitize_allows_commands_against_writable_paths(self):
        tasks, criteria, rejected = sanitize_decomposition(
            "Python progress bar",
            ["Create src/main.py"],
            ["Running `python src/main.py` exits with code 0"],
        )
        self.assertEqual(tasks, ["Create src/main.py"])
        self.assertEqual(criteria, ["Running `python src/main.py` exits with code 0"])
        self.assertEqual(rejected, [])

    def test_sanitize_ignores_slash_separated_chart_alternatives(self):
        tasks, criteria, rejected = sanitize_decomposition(
            "Write a single html css javascript dashboard with charts",
            [
                "Create src/index.html with metric cards and visible SVG chart marks.",
                "Add a second chart type (e.g., pie/donut or area chart) using SVG in src/dashboard.js, driven by sample data.",
                "Create src/styles.css with responsive grid layout and polished dashboard card styling.",
            ],
            [
                "Generated dashboard shows at least three visible metric cards with numeric values.",
                "Generated dashboard includes SVG bar/point chart marks and a pie/donut chart with visible data.",
                "Generated dashboard loads local CSS with responsive grid layout and distinct metric-card colors.",
                "Moving the mouse over either chart highlights the nearest bar/point and displays a tooltip.",
            ],
        )
        self.assertEqual(len(tasks), 3)
        self.assertEqual(len(criteria), 4)
        self.assertFalse(any("non-writable/root path" in r for r in rejected), rejected)

    def test_sanitize_still_rejects_root_level_ui_paths(self):
        tasks, criteria, rejected = sanitize_decomposition(
            "Write a dashboard",
            ["Create index.html, styles.css, and script.js in the repo."],
            [
                "Dashboard shows three numeric metric values.",
                "Dashboard includes visible SVG chart marks.",
                "Dashboard uses responsive CSS grid layout.",
            ],
        )
        self.assertEqual(tasks, [])
        self.assertTrue(any("non-writable/root path" in r for r in rejected), rejected)

    def test_dashboard_scaffold_decomposition_is_rejected(self):
        tasks, criteria, rejected = sanitize_decomposition(
            "Write a simple HTML page that shows a pretty dashboard with charts, "
            "graphs, clean visuals, data, and metrics.",
            [
                "Create a new directory named src in the project root.",
                "Create src/dashboard.html.",
                "Add a <body> section with a container div.",
                "Add a <div> inside the main section for charts and graphs.",
                "Add a <footer> with copyright text.",
            ],
            [
                "The dashboard.html file contains a basic HTML structure.",
                "The CSS file contains basic styling.",
                "There is a div with class charts-and-graphs.",
            ],
        )
        self.assertEqual(tasks, [])
        self.assertEqual(criteria, [])
        self.assertTrue(any("FRONTEND" in r for r in rejected), rejected)

    def test_dashboard_fallback_decomposition_prefers_in_place_refinement(self):
        tasks, criteria = fallback_decomposition(
            "Create a good internal customer intelligence corporate dashboard"
        )
        self.assertGreaterEqual(len(tasks), 5)
        self.assertIn("src/index.html", tasks[0])
        self.assertTrue(any("local visual primitives" in task for task in tasks))
        self.assertTrue(any("Refine the existing" in task for task in tasks))
        self.assertTrue(any("harness-reported validation blockers" in task for task in tasks))
        self.assertTrue(any("without adding backend servers" in criterion.lower()
                            for criterion in criteria))

    def test_contract_for_prompt(self):
        d = Path(tempfile.mkdtemp())
        save_contract(d, "Build a widget", ["Create src/widget.py"], ["tests pass"])
        contract = contract_for_prompt(d)
        self.assertIn("Build a widget", contract)
        self.assertIn("Create src/widget.py", contract)
        self.assertIn("Tests must be deterministic", contract)
        self.assertIn("Entry points and demos must be bounded", contract)

    def test_dashboard_contract_includes_frontend_quality_rules(self):
        d = Path(tempfile.mkdtemp())
        save_contract(
            d,
            "Build an HTML dashboard with charts and metrics",
            ["Build src/dashboard.html"],
            ["Visible metrics and charts"],
        )
        contract = contract_for_prompt(d)
        self.assertIn("complete visible first screen", contract)
        self.assertIn("Local stylesheet/script links must resolve", contract)
        self.assertIn("at least three visible metric values", contract)
        self.assertIn("empty chart", contract)

    def test_verify_output(self):
        passed, failed = parse_verify_output(
            "PASS: C1\nFAIL: C2 — files copied not moved\npass: c3\nFAIL C4\n")
        self.assertEqual(passed, {1, 3})
        self.assertEqual(failed[2], "files copied not moved")
        self.assertIn(4, failed)


class TestStuck(unittest.TestCase):
    def _iter(self, subtask, passed=True, errors=(), files=("src/a.py",)):
        return {"event": "iteration", "subtask": subtask, "validation_passed": passed,
                "errors": list(errors), "files_written": list(files)}

    def test_repeat_and_oscillation(self):
        entries = [
            self._iter("add the parser", passed=False, errors=("SyntaxError",), files=()),
            self._iter("add the writer", passed=False, errors=("SyntaxError",), files=()),
        ]
        sig = {s.kind for s in detect_signals("add the parser", entries, 0.85)}
        self.assertIn("repeat", sig)
        self.assertIn("oscillation", sig)  # matches N-2, not N-1

    def test_productive_refinement_is_not_flagged_as_repeat(self):
        entries = [self._iter("refine src/index.html"), self._iter("refine src/styles.css")]
        sig = {s.kind for s in detect_signals("refine src/index.html", entries, 0.85)}
        self.assertNotIn("repeat", sig)
        self.assertNotIn("oscillation", sig)

    def test_no_writes(self):
        entries = [self._iter("a", files=()), self._iter("b"), self._iter("c", files=())]
        sig = {s.kind for s in detect_signals("totally new step", entries, 0.85)}
        self.assertIn("no_writes", sig)

    def test_same_error_normalization(self):
        self.assertEqual(normalize_error("foo.py:12: NameError: name 'x'"),
                         normalize_error("foo.py:99: NameError: name 'y'"))
        errs = ["main.py: line 4: SyntaxError"]
        entries = [self._iter(f"s{i}", passed=False, errors=errs) for i in range(3)]
        sig = {s.kind for s in detect_signals("different step entirely", entries, 0.85)}
        self.assertIn("same_error", sig)

    def test_same_warning_signal(self):
        entries = [
            {"event": "iteration", "subtask": "a", "validation_passed": True,
             "validation_warnings": ["product_warning: frontend_static: no visible chart marks"],
             "files_written": ["src/index.html"]},
            {"event": "iteration", "subtask": "b", "validation_passed": True,
             "validation_warnings": ["product_warning: frontend_static: no visible chart marks"],
             "files_written": ["src/styles.css"]},
            {"event": "iteration", "subtask": "c", "validation_passed": True,
             "validation_warnings": ["product_warning: frontend_static: no visible chart marks"],
             "files_written": ["src/script.js"]},
        ]
        sig = {s.kind for s in detect_signals("fix chart marks", entries, 0.85)}
        self.assertIn("same_warning", sig)


class TestBackendAndStatus(unittest.TestCase):
    def test_detect_rate_limit_error(self):
        self.assertTrue(is_rate_limit_error("HTTP 429 from provider: Too Many Requests"))
        self.assertFalse(is_rate_limit_error("HTTP 403 forbidden"))

    def test_post_json_timeout_becomes_backend_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(BackendError, "timeout calling"):
                _post_json("http://127.0.0.1:11434/api/chat", {}, {}, timeout=1)

    def test_post_json_auth_failure_is_not_retryable(self):
        http_error = urllib.error.HTTPError(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            403,
            "Forbidden",
            {},
            io.BytesIO(b'{"detail":"Authorization failed"}'),
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaisesRegex(BackendError, "check the provider API key") as cm:
                _post_json("https://integrate.api.nvidia.com/v1/chat/completions", {}, {})
        self.assertFalse(cm.exception.retryable)

    def test_post_json_rate_limit_carries_retry_after(self):
        http_error = urllib.error.HTTPError(
            "https://integrate.api.nvidia.com/v1/chat/completions",
            429,
            "Too Many Requests",
            {"Retry-After": "42"},
            io.BytesIO(b'{"status":429,"title":"Too Many Requests"}'),
        )
        with mock.patch("urllib.request.urlopen", side_effect=http_error):
            with self.assertRaisesRegex(BackendError, "HTTP 429") as cm:
                _post_json("https://integrate.api.nvidia.com/v1/chat/completions", {}, {})
        self.assertTrue(cm.exception.retryable)
        self.assertEqual(cm.exception.retry_after, 42)

    def test_ollama_backend_uses_configured_timeout(self):
        cfg = Config(model="ollama/test:latest", backend_timeout=123)
        backend = OllamaBackend(cfg)
        with mock.patch(
            "ninexf.backends._post_json",
            return_value={"message": {"content": "ok"}, "prompt_eval_count": 12},
        ) as post:
            self.assertEqual(backend.complete("system", "user"), "ok")
        self.assertEqual(post.call_args.kwargs["timeout"], 123)

    def test_nvidia_backend_uses_chat_completions_payload(self):
        cfg = Config(
            model=NVIDIA_KIMI_MODEL,
            backend_timeout=123,
            temperature=1.0,
            top_p=1.0,
            max_tokens=16384,
        )
        with mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}):
            backend = NvidiaBackend(cfg)
        with mock.patch(
            "ninexf.backends._post_json",
            return_value={"choices": [{"message": {"content": "ok"}}]},
        ) as post:
            self.assertEqual(backend.complete("system", "user"), "ok")
        url, payload = post.call_args.args[:2]
        self.assertEqual(url, "https://integrate.api.nvidia.com/v1/chat/completions")
        self.assertEqual(payload["model"], "moonshotai/kimi-k2.6")
        self.assertEqual(payload["temperature"], 1.0)
        self.assertEqual(payload["top_p"], 1.0)
        self.assertEqual(payload["max_tokens"], 16384)
        self.assertEqual(post.call_args.kwargs["timeout"], 123)

    def test_nvidia_gemma_payload_uses_single_user_message_without_thinking_flag(self):
        cfg = Config(
            model=NVIDIA_GEMMA_MODEL,
            temperature=1.0,
            top_p=0.95,
            max_tokens=16384,
        )
        with mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "test-key"}):
            backend = NvidiaBackend(cfg)
        with mock.patch(
            "ninexf.backends._post_json",
            return_value={"choices": [{"message": {"content": "ok"}}]},
        ) as post:
            self.assertEqual(
                backend.complete("system instructions", "user prompt", max_tokens=2048),
                "ok",
            )
        payload = post.call_args.args[1]
        self.assertEqual(payload["model"], "google/gemma-4-31b-it")
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertNotIn("chat_template_kwargs", payload)
        self.assertEqual(len(payload["messages"]), 1)
        self.assertEqual(payload["messages"][0]["role"], "user")
        self.assertIn("system instructions", payload["messages"][0]["content"])
        self.assertIn("user prompt", payload["messages"][0]["content"])

    def test_mistral_backend_uses_direct_chat_completions_payload(self):
        cfg = Config(
            model=MISTRAL_SMALL_MODEL,
            backend_timeout=123,
            temperature=0.6,
            top_p=0.7,
            max_tokens=16384,
        )
        with mock.patch.dict("os.environ", {"MISTRAL_API_KEY": "test-key"}):
            backend = MistralBackend(cfg)
        with mock.patch(
            "ninexf.backends._post_json",
            return_value={"choices": [{"message": {"content": "ok"}}]},
        ) as post:
            self.assertEqual(
                backend.complete("system instructions", "user prompt", max_tokens=4096),
                "ok",
            )
        url, payload = post.call_args.args[:2]
        self.assertEqual(url, "https://api.mistral.ai/v1/chat/completions")
        self.assertEqual(payload["model"], "mistral-small-2603")
        self.assertEqual(payload["max_tokens"], 4096)
        self.assertEqual(payload["temperature"], 0.6)
        self.assertEqual(payload["top_p"], 0.7)
        self.assertEqual(payload["response_format"], {"type": "text"})
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["role"], "user")
        self.assertEqual(post.call_args.kwargs["timeout"], 123)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-key")

    def test_nvidia_backend_defaults_to_nvidia_api_key_env(self):
        cfg = Config(model=NVIDIA_KIMI_MODEL)
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(BackendError, "NVIDIA_API_KEY"):
                NvidiaBackend(cfg)

    def test_mistral_backend_defaults_to_mistral_api_key_env(self):
        cfg = Config(model=MISTRAL_SMALL_MODEL)
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(BackendError, "MISTRAL_API_KEY"):
                MistralBackend(cfg)

    def test_running_state_with_dead_pid_is_failed(self):
        state = {"running": True, "pid": 12345, "ts": "2026-06-12T03:38:59+00:00"}
        with mock.patch("ninexf.dashboard._pid_alive", return_value=False):
            self.assertEqual(_run_status(state, delay=5, last_iter_ok=None), "failed")

    def test_tool_result_failed_detects_nonzero_exit(self):
        self.assertTrue(tool_result_failed("[exit 1] traceback"))
        self.assertFalse(tool_result_failed("[ok] done"))

    def test_note_filter_drops_claim_contradicted_by_warning(self):
        self.assertTrue(note_contradicted(
            "The chart now includes visible marks such as data points.",
            [],
            ["product_warning: frontend_static: src/index.html: chart/graph language is present but no visible chart marks"],
        ))
        self.assertFalse(note_contradicted(
            "Use teal for the revenue card accent.",
            [],
            ["product_warning: frontend_static: src/index.html: chart/graph language is present but no visible chart marks"],
        ))


class TestRelevance(unittest.TestCase):
    def test_scoring_order(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        (d / "src/parser.py").write_text("import helpers\ndef parse(): pass\n")
        (d / "src/helpers.py").write_text("def helper(): pass\n")
        (d / "src/unrelated.py").write_text("x = 1\n")
        files = [(d / "src" / f, f"src/{f}")
                 for f in ("parser.py", "helpers.py", "unrelated.py")]
        scored = score_files(files, "Fix the bug in src/parser.py",
                             [{"errors": ["helpers.py: NameError"], "files_written": []}])
        self.assertEqual(scored[0].rel, "src/parser.py")
        self.assertEqual(scored[1].rel, "src/helpers.py")
        self.assertGreater(scored[0].score, scored[1].score)
        self.assertLess(scored[2].score, 1)


class TestCandidates(unittest.TestCase):
    def _cr(self, i, **kw):
        base = dict(index=i, temperature=0.4, summary="", passed=False,
                    acceptance_passed=None, tests_ran=0, errors_n=0, files_n=1)
        base.update(kw)
        return CandidateResult(**base)

    def test_pick_winner(self):
        self.assertEqual(pick_winner([self._cr(0), self._cr(1, passed=True)]), 1)
        self.assertEqual(pick_winner([self._cr(0, passed=True),
                                      self._cr(1, passed=True, tests_ran=2)]), 1)
        # tie -> lowest index (lowest temperature)
        self.assertEqual(pick_winner([self._cr(0, passed=True),
                                      self._cr(1, passed=True)]), 0)

    def test_critic_parse(self):
        self.assertEqual(parse_critic_output("VERDICT: ACCEPT"), ("ACCEPT", []))
        v, issues = parse_critic_output("VERDICT: REVISE\nISSUE: a\nISSUE: b\n")
        self.assertEqual(v, "REVISE")
        self.assertEqual(issues, ["a", "b"])
        self.assertEqual(parse_critic_output("looks good to me")[0], "unparsed")


class TestFitness(unittest.TestCase):
    def _e(self, commit, **kw):
        base = {"event": "iteration", "commit": commit, "validation_passed": False,
                "acceptance_passed": None, "tasks_done": 0, "tests_ran": 0,
                "errors": [], "iteration": 1}
        base.update(kw)
        return base

    def test_ordering(self):
        # held-out acceptance dominates everything else
        self.assertGreater(
            fitness_of(self._e("a", acceptance_passed=True)),
            fitness_of(self._e("b", validation_passed=True, tasks_done=5, tests_ran=20)))
        # then validation, then task progress, then tests
        self.assertGreater(
            fitness_of(self._e("a", validation_passed=True)),
            fitness_of(self._e("b", tasks_done=9)))
        self.assertGreater(
            fitness_of(self._e("a", validation_passed=True, tasks_done=2)),
            fitness_of(self._e("b", validation_passed=True, tasks_done=1)))

    def test_best_state_prefers_latest_tie(self):
        entries = [
            self._e("c1", validation_passed=True, iteration=1),
            self._e("c2", validation_passed=True, iteration=2),
            self._e("c3", iteration=3),
            {"event": "shutdown", "summary": "x"},  # ignored: not scoreable
        ]
        self.assertEqual(best_state(entries)["commit"], "c2")
        self.assertEqual(final_state(entries)["commit"], "c3")

    def test_soft_errors_do_not_hurt_best_state(self):
        entries = [
            self._e("c1", validation_passed=True, tasks_done=1, iteration=1),
            self._e("c2", validation_passed=True, tasks_done=1, iteration=2,
                    soft_errors=["task-check skipped: HTTP 429"]),
        ]
        self.assertEqual(best_state(entries)["commit"], "c2")

    def test_empty(self):
        self.assertIsNone(best_state([]))
        self.assertIsNone(final_state([{"event": "iteration", "commit": ""}]))


class TestPresets(unittest.TestCase):
    def test_model_catalog_includes_gpt_oss_20b(self):
        options = model_options([])
        self.assertEqual(options[0], DEFAULT_MODEL)
        self.assertIn(GPT_OSS_20B_MODEL, options)
        self.assertIn(MISTRAL_SMALL_MODEL, options)
        self.assertIn(NVIDIA_GEMMA_MODEL, options)
        self.assertIn(NVIDIA_QWEN_NEXT_MODEL, options)

    def test_model_catalog_prefers_installed_ollama_models(self):
        options = model_options(["gpt-oss:20b", "custom:latest"])
        self.assertEqual(options[:2], [GPT_OSS_20B_MODEL, "ollama/custom:latest"])
        self.assertEqual(options.count(GPT_OSS_20B_MODEL), 1)

    def test_webapp_model_list_includes_recommended_models(self):
        from ninexf.webapp import list_models
        with mock.patch("ninexf.interactive._ollama_models", return_value=[]):
            models = list_models()
        self.assertEqual(models["default"], DEFAULT_MODEL)
        self.assertIn(GPT_OSS_20B_MODEL, models["models"])
        self.assertIn(GPT_OSS_20B_MODEL, models["recommended"])
        self.assertIn(MISTRAL_SMALL_MODEL, models["models"])
        self.assertIn(MISTRAL_SMALL_MODEL, models["recommended"])
        self.assertIn(NVIDIA_GEMMA_MODEL, models["models"])
        self.assertIn(NVIDIA_GEMMA_MODEL, models["recommended"])
        self.assertIn(NVIDIA_QWEN_NEXT_MODEL, models["models"])
        self.assertIn(NVIDIA_QWEN_NEXT_MODEL, models["recommended"])

    def test_overnight_preset(self):
        d = Path(tempfile.mkdtemp())
        write_config(d, {"model": "mock"}, preset="overnight")
        cfg = load_config(d)
        self.assertEqual(cfg.best_of_n, 3)
        self.assertEqual(cfg.best_of_mode, "always")
        self.assertTrue(cfg.critic_enabled)
        self.assertTrue(cfg.explore_enabled)
        self.assertEqual(cfg.repair_attempts, 2)
        self.assertEqual(cfg.format_retry_attempts, 2)
        self.assertEqual(cfg.backend_timeout, 1200)
        self.assertTrue(cfg.reflection_enabled)
        self.assertEqual(cfg.reflection_every, 1)
        self.assertEqual(cfg.reflection_max_notes, 4)
        self.assertTrue(cfg.keep_best)
        self.assertTrue(cfg.acceptance_tests)
        self.assertEqual(cfg.max_hours, 8)
        self.assertEqual(cfg.model, "mock", "explicit overrides beat the preset")


class TestPhaseTokenCaps(unittest.TestCase):
    def test_phase_caps_reduce_non_executor_budgets(self):
        from ninexf.loop import LoopRunner
        d = Path(tempfile.mkdtemp())
        (d / "goal.txt").write_text("test goal")
        cfg = Config(model="mock", max_tokens=16384)
        runner = LoopRunner(d, cfg)
        self.assertEqual(runner._max_tokens_for_purpose("decompose"), 2048)
        self.assertEqual(runner._max_tokens_for_purpose("planner"), 768)
        self.assertEqual(runner._max_tokens_for_purpose("verify_done"), 1536)
        self.assertEqual(runner._max_tokens_for_purpose("executor"), 8192)

    def test_phase_caps_respect_lower_config_cap(self):
        from ninexf.loop import LoopRunner
        d = Path(tempfile.mkdtemp())
        (d / "goal.txt").write_text("test goal")
        cfg = Config(model="mock", max_tokens=600)
        runner = LoopRunner(d, cfg)
        self.assertEqual(runner._max_tokens_for_purpose("decompose"), 600)
        self.assertEqual(runner._max_tokens_for_purpose("planner"), 600)
        self.assertEqual(runner._max_tokens_for_purpose("executor"), 600)


class TestDecomposeFallback(unittest.TestCase):
    def test_retryable_backend_error_installs_fallback_decomposition(self):
        from ninexf.loop import LoopRunner
        d = Path(tempfile.mkdtemp())
        (d / "goal.txt").write_text("well designed dashboard")
        cfg = Config(model="mock")
        runner = LoopRunner(d, cfg)
        runner._complete = mock.Mock(side_effect=BackendError("timeout calling nvidia"))
        with mock.patch("ninexf.loop_decompose.has_changes", return_value=False):
            entry = runner._run_decompose(1)
        self.assertEqual(entry.event, "decompose")
        self.assertIn("fallback roadmap", entry.summary)
        self.assertTrue((d / "TASKS.md").exists())
        self.assertTrue((d / "ACCEPTANCE.md").exists())
        self.assertTrue((d / "CONTRACT.md").exists())
        self.assertTrue(any("backend failed" in e for e in entry.errors))

    def test_default_control_mode_is_hybrid(self):
        self.assertEqual(Config().control_mode, "hybrid")

    def test_default_continues_after_goal_complete(self):
        self.assertFalse(Config().stop_on_goal_complete)

    def test_unknown_preset_rejected(self):
        with self.assertRaises(ValueError):
            write_config(Path(tempfile.mkdtemp()), preset="nope")

    def test_load_dotenv_reads_project_env_without_overriding(self):
        d = Path(tempfile.mkdtemp())
        (d / ".env").write_text(
            "NVIDIA_API_KEY=from-file\n"
            "export QUOTED_KEY=\"quoted value\"\n"
            "COMMENTED=value # comment\n"
        )
        with mock.patch.dict("os.environ", {"NVIDIA_API_KEY": "from-env"}, clear=True):
            load_dotenv(d)
            self.assertEqual(os.environ["NVIDIA_API_KEY"], "from-env")
            self.assertEqual(os.environ["QUOTED_KEY"], "quoted value")
            self.assertEqual(os.environ["COMMENTED"], "value")

    def test_nvidia_config_writes_provider_defaults(self):
        d = Path(tempfile.mkdtemp())
        write_config(d, {"model": NVIDIA_KIMI_MODEL})
        cfg = load_config(d)
        self.assertEqual(cfg.api_key_env, "NVIDIA_API_KEY")
        self.assertEqual(cfg.endpoint, "https://integrate.api.nvidia.com/v1")

    def test_mistral_config_writes_provider_defaults(self):
        d = Path(tempfile.mkdtemp())
        write_config(d, {"model": MISTRAL_SMALL_MODEL})
        cfg = load_config(d)
        self.assertEqual(cfg.api_key_env, "MISTRAL_API_KEY")
        self.assertEqual(cfg.endpoint, "https://api.mistral.ai/v1")

    def test_start_run_blocks_second_active_nvidia_run(self):
        active = Path(tempfile.mkdtemp())
        target = Path(tempfile.mkdtemp())
        (active / "goal.txt").write_text("active")
        (target / "goal.txt").write_text("target")
        write_config(active, {"model": NVIDIA_KIMI_MODEL})
        write_config(target, {"model": NVIDIA_GEMMA_MODEL})

        def running_only_active(path: Path) -> bool:
            return path == active

        with mock.patch("ninexf.webapp.registered_runs", return_value=[active]), \
                mock.patch("ninexf.webapp.is_running", side_effect=running_only_active), \
                mock.patch("ninexf.webapp.subprocess.Popen") as popen:
            result = start_run({"dir": str(target), "goal": "target"})

        self.assertIn("another NVIDIA-backed run is already active", result["error"])
        popen.assert_not_called()

    def test_presets_only_use_known_keys(self):
        from ninexf.config import DEFAULTS
        for name, values in PRESETS.items():
            self.assertTrue(set(values) <= set(DEFAULTS), name)


class TestContextSafety(unittest.TestCase):
    def test_snapshot_budget_derived_from_num_ctx(self):
        auto = Config(context_char_budget=0, num_ctx=16384)
        self.assertEqual(auto.snapshot_budget, int((16384 - 2048) * 4 * 0.6))
        bigger = Config(context_char_budget=0, num_ctx=32768)
        self.assertGreater(bigger.snapshot_budget, auto.snapshot_budget)
        explicit = Config(context_char_budget=24000, num_ctx=16384)
        self.assertEqual(explicit.snapshot_budget, 24000)

    def test_overflow_detection(self):
        self.assertTrue(context_overflowed(16380, 16384))
        self.assertTrue(context_overflowed(16384, 16384))
        self.assertFalse(context_overflowed(8000, 16384))
        self.assertFalse(context_overflowed(None, 16384))

    def test_prompts_prevent_future_module_imports_in_entry_point(self):
        self.assertIn("src/index.html", PLANNER_SYSTEM)
        self.assertIn("validation-green", DECOMPOSE_USER)
        self.assertIn("must not import modules that do not exist yet", DECOMPOSE_USER)
        self.assertIn("not already present in CURRENT CODEBASE", EXECUTOR_SYSTEM)
        self.assertIn("do not write root-level", EXECUTOR_SYSTEM)
        self.assertIn("do not use package-relative", EXECUTOR_SYSTEM)
        self.assertIn("Do not \"fix\" `python src/main.py`", REPAIR_NOTE)

    def test_render_partial(self):
        d = Path(tempfile.mkdtemp())
        f = d / "mover.py"
        f.write_text(
            "import shutil\n\n"
            "LIMIT = 5\n\n"
            "def move_files(src, dst):\n"
            "    shutil.move(src, dst)\n"
            "    return dst\n\n"
            "def unrelated_helper():\n"
            "    x = 1\n"
            "    y = 2\n"
            "    return x + y\n"
        )
        out = render_partial(f, "Fix the bug in move_files for the mover", 5000)
        self.assertIsNotNone(out)
        self.assertIn("import shutil", out, "header preserved")
        self.assertIn("shutil.move(src, dst)", out, "relevant body kept in full")
        self.assertIn("def unrelated_helper(...):", out)
        self.assertNotIn("return x + y", out, "irrelevant body collapsed")
        self.assertIn("body omitted", out)
        # too small a budget -> can't render
        self.assertIsNone(render_partial(f, "move_files", 10))
        # files with no defs aren't worth partial-rendering
        g = d / "flat.py"
        g.write_text("x = 1\ny = 2\n")
        self.assertIsNone(render_partial(g, "anything", 5000))


class TestParserNotes(unittest.TestCase):
    def test_notes_unfenced_only(self):
        out = parse_executor_output(
            "SUMMARY: x\nNOTE: keep this\nFILE: src/a.py\n"
            "```python\n# NOTE: not this\nx=1\n```\nNOTE: and this\n")
        self.assertEqual(out.notes, ["keep this", "and this"])


class TestValidationEvidence(unittest.TestCase):
    def test_entry_point_sleep_is_rejected_before_timeout(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        src = d / "src" / "main.py"
        src.write_text(
            "import time\n\n"
            "def main():\n"
            "    time.sleep(1)\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        result = validate(d, [src], timeout=5, allow_network=True)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_kind, "slow_entry")
        self.assertIn("slow_entry", result.errors[0])

    def test_unittest_error_excerpt_keeps_traceback(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        (d / "tests").mkdir()
        (d / "tests" / "__init__.py").write_text("")
        (d / "src" / "progress.py").write_text(
            "class ProgressBar:\n"
            "    def update(self, increment=1):\n"
            "        return increment\n"
        )
        test = d / "tests" / "test_progress.py"
        test.write_text(
            "import unittest\n"
            "from src.progress import ProgressBar\n\n"
            "class TestProgress(unittest.TestCase):\n"
            "    def test_update_percentage_and_elapsed(self):\n"
            "        ProgressBar().update(new_percentage=75)\n"
        )
        result = validate(d, [test], timeout=5, allow_network=True)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_kind, "tests")
        self.assertIn("test_update_percentage_and_elapsed", result.errors[0])
        self.assertIn("TypeError", result.errors[0])
        self.assertIn("unexpected keyword argument", result.error_excerpt)

    def test_slow_test_guard_fails_before_timeout(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        (d / "tests").mkdir()
        (d / "tests" / "__init__.py").write_text("")
        src = d / "src" / "main.py"
        src.write_text("def main():\n    return 0\n")
        test = d / "tests" / "test_slow.py"
        test.write_text(
            "import time\nimport unittest\n\n"
            "class TestSlow(unittest.TestCase):\n"
            "    def test_slow(self):\n"
            "        time.sleep(1)\n"
            "        self.assertTrue(True)\n"
        )
        result = validate(d, [test], timeout=5, allow_network=True)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_kind, "slow_test")
        self.assertIn("slow_test", result.errors[0])

    def test_any_sleep_in_tests_is_rejected(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        (d / "tests").mkdir()
        (d / "tests" / "__init__.py").write_text("")
        test = d / "tests" / "test_sleep.py"
        test.write_text(
            "import time\nimport unittest\n\n"
            "class TestSleep(unittest.TestCase):\n"
            "    def test_short_sleep(self):\n"
            "        time.sleep(0.1)\n"
            "        self.assertTrue(True)\n"
        )
        result = validate(d, [test], timeout=5, allow_network=True)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_kind, "slow_test")
        self.assertIn("must not sleep", result.errors[0])

    def test_wall_clock_calls_in_tests_are_rejected(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        (d / "tests").mkdir()
        (d / "tests" / "__init__.py").write_text("")
        test = d / "tests" / "test_time.py"
        test.write_text(
            "import time\nimport unittest\n\n"
            "class TestTime(unittest.TestCase):\n"
            "    def test_now(self):\n"
            "        self.assertGreaterEqual(time.time(), 0)\n"
        )
        result = validate(d, [test], timeout=5, allow_network=True)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_kind, "slow_test")
        self.assertIn("wall-clock", "\n".join(result.errors))

    def test_dashboard_with_broken_stylesheet_and_empty_chart_fails(self):
        d = Path(tempfile.mkdtemp())
        (d / "src" / "css").mkdir(parents=True)
        html = d / "src" / "dashboard.html"
        css = d / "src" / "css" / "styles.css"
        css.write_text("body { font-family: Arial, sans-serif; }\n")
        html.write_text(
            "<!doctype html><html><head><title>Pretty Dashboard</title>"
            "<link rel='stylesheet' href='../css/styles.css'></head>"
            "<body><h1>Dashboard</h1><h2>Metrics & Graphs</h2>"
            "<div class='charts-and-graphs'></div>"
            "<footer>(c) 2023 Pretty Dashboard</footer></body></html>"
        )
        result = validate(d, [html, css], timeout=5, allow_network=True)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_kind, "frontend_static")
        joined = "\n".join(result.errors)
        self.assertIn("stylesheet link", joined)
        self.assertIn("empty placeholders", joined)
        self.assertIn("numeric value", joined)

    def test_static_dashboard_with_resolved_css_data_and_chart_passes(self):
        d = Path(tempfile.mkdtemp())
        (d / "src" / "css").mkdir(parents=True)
        html = d / "src" / "dashboard.html"
        css = d / "src" / "css" / "styles.css"
        css.write_text(
            "body { font-family: Arial, sans-serif; background: #f7f8fb; }"
            ".metric { display: inline-block; padding: 12px; }"
        )
        html.write_text(
            "<!doctype html><html><head><title>Ops Dashboard</title>"
            "<link rel='stylesheet' href='css/styles.css'></head><body>"
            "<main class='dashboard'>"
            "<section class='metrics'>"
            "<article class='metric'><strong>$128K</strong><span>Revenue</span></article>"
            "<article class='metric'><strong>42%</strong><span>Conversion</span></article>"
            "<article class='metric'><strong>18,400</strong><span>Visitors</span></article>"
            "</section>"
            "<svg class='chart' viewBox='0 0 120 50' aria-label='Revenue chart'>"
            "<rect x='4' y='20' width='12' height='26'></rect>"
            "<rect x='24' y='12' width='12' height='34'></rect>"
            "<rect x='44' y='6' width='12' height='40'></rect>"
            "<text x='4' y='48'>Q1</text>"
            "</svg>"
            "</main></body></html>"
        )
        result = validate(d, [html, css], timeout=5, allow_network=True)
        self.assertTrue(result.passed, result.errors)
        self.assertIn("frontend-static", result.detail)

    def test_svg_chart_rejects_negative_rect_height(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        html = d / "src" / "dashboard.html"
        css = d / "src" / "styles.css"
        css.write_text("body { font-family: Arial, sans-serif; }.metric{padding:8px}\n")
        html.write_text(
            "<!doctype html><html><head><title>Ops Dashboard</title>"
            "<link rel='stylesheet' href='styles.css'></head><body>"
            "<main class='dashboard'>"
            "<article class='metric'>$128K</article>"
            "<article class='metric'>42%</article>"
            "<article class='metric'>18,400</article>"
            "<svg class='chart' viewBox='0 0 120 50' aria-label='Revenue chart'>"
            "<rect x='4' y='20' width='12' height='26'></rect>"
            "<rect x='24' y='42' width='12' height='-10'></rect>"
            "<rect x='44' y='6' width='12' height='40'></rect>"
            "<text x='4' y='48'>Q1</text>"
            "</svg>"
            "</main></body></html>"
        )
        result = validate(d, [html, css], timeout=5, allow_network=True)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_kind, "frontend_static")
        self.assertIn("negative height", "\n".join(result.errors))

    def test_build_validation_warns_for_canvas_charts_planned_later(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        html = d / "src" / "index.html"
        css = d / "src" / "styles.css"
        css.write_text("body{display:grid}.metric{background:white}\n")
        html.write_text(
            "<!doctype html><html><head><link rel='stylesheet' href='styles.css'></head>"
            "<body><main class='dashboard'>"
            "<section class='metrics'><div>$120K</div><div>42%</div><div>8,901</div></section>"
            "<section class='chart'><h2>Customer chart</h2><canvas id='chart'></canvas></section>"
            "<script src='script.js'></script>"
            "</main></body></html>"
        )
        build = validate(d, [html, css], timeout=5, allow_network=True, phase="build")
        self.assertTrue(build.passed, build.errors)
        self.assertTrue(build.warnings)
        self.assertIn("product warning", build.detail)
        final = validate(d, [html, css], timeout=5, allow_network=True, phase="final")
        self.assertFalse(final.passed)
        self.assertEqual(final.failure_kind, "frontend_static")

    def test_build_validation_hard_fails_empty_dashboard_placeholders(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        html = d / "src" / "index.html"
        html.write_text(
            "<!doctype html><html><head><style>.dashboard{display:grid}</style></head>"
            "<body><main class='dashboard'><div class='chart'></div>"
            "<p>$1</p><p>2%</p><p>3</p></main></body></html>"
        )
        result = validate(d, [html], timeout=5, allow_network=True, phase="build")
        self.assertFalse(result.passed)
        self.assertIn("empty placeholders", "\n".join(result.errors))

    def test_final_validation_accepts_canvas_chart_with_local_drawing_code(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        html = d / "src" / "index.html"
        css = d / "src" / "styles.css"
        js = d / "src" / "script.js"
        html.write_text(
            "<!doctype html><html><head><link rel='stylesheet' href='styles.css'></head>"
            "<body><main class='dashboard'><div>$120K</div><div>42%</div><div>8,901</div>"
            "<canvas id='chart'></canvas><script src='script.js'></script></main></body></html>"
        )
        css.write_text("body{font-family:Arial}.dashboard{display:grid}\n")
        js.write_text(
            "const ctx = document.getElementById('chart').getContext('2d');\n"
            "ctx.beginPath();\nctx.moveTo(0, 50);\nctx.lineTo(50, 10);\nctx.stroke();\n"
        )
        result = validate(d, [html, css, js], timeout=5, allow_network=True, phase="final")
        self.assertTrue(result.passed, result.errors)

    def test_chartjs_without_loaded_library_fails_validation(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        html = d / "src" / "index.html"
        css = d / "src" / "styles.css"
        js = d / "src" / "script.js"
        html.write_text(
            "<!doctype html><html><head><link rel='stylesheet' href='styles.css'></head>"
            "<body><main class='dashboard'><div>$120K</div><div>42%</div><div>8,901</div>"
            "<canvas id='chart'></canvas><script src='script.js'></script></main></body></html>"
        )
        css.write_text("body{font-family:Arial}.dashboard{display:grid}\n")
        js.write_text(
            "const ctx = document.getElementById('chart').getContext('2d');\n"
            "new Chart(ctx, {type:'line', data:{labels:['Jan'], datasets:[{data:[1]}]}});\n"
        )
        result = validate(d, [html, css, js], timeout=5, allow_network=True, phase="final")
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_kind, "frontend_static")
        self.assertIn("instantiates Chart", "\n".join(result.errors))

    def test_dashboard_quality_warnings_flag_sparse_nonresponsive_css(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        html = d / "src" / "index.html"
        css = d / "src" / "styles.css"
        html.write_text(
            "<!doctype html><html><head><link rel='stylesheet' href='styles.css'></head>"
            "<body><main class='dashboard'><section class='metrics'>"
            "<div class='metric'>$120K</div><div class='metric'>42%</div><div class='metric'>8,901</div>"
            "</section><svg class='chart'><rect x='0' y='0' width='10' height='10'></rect>"
            "<rect x='12' y='0' width='10' height='12'></rect><rect x='24' y='0' width='10' height='14'></rect>"
            "</svg></main></body></html>"
        )
        css.write_text("body{font-family:Arial}.metric{padding:4px}\n")
        result = validate(d, [html, css], timeout=5, allow_network=True, phase="final")
        self.assertTrue(result.passed, result.errors)
        joined = "\n".join(result.warnings)
        self.assertIn("responsive layout cues", joined)
        self.assertIn("visually sparse", joined)


class TestRepairEvidence(unittest.TestCase):
    def test_repair_dump_includes_traceback_referenced_files(self):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        (d / "tests").mkdir()
        main = d / "src" / "main.py"
        progress = d / "src" / "progress_bar.py"
        test = d / "tests" / "test_progress_bar.py"
        main.write_text("from progress_bar import ProgressBar\n")
        progress.write_text("class ProgressBar:\n    pass\n")
        test.write_text("from src.progress_bar import ProgressBar\n")
        parsed = parse_executor_output(
            "SUMMARY: added demo\n"
            "FILE: src/main.py\n"
            "```python\nfrom progress_bar import ProgressBar\n```\n"
        )
        outcome = ExecOutcome(
            parsed=parsed,
            written=[main],
            errors=[
                f'File "{progress}", line 2, in write\n'
                "AttributeError: bad\n"
                "tests/test_progress_bar.py: failed assertion"
            ],
        )
        dump = _repair_file_dump(d, outcome, 10000)
        self.assertIn("--- src/main.py ---", dump)
        self.assertIn("--- src/progress_bar.py ---", dump)
        self.assertIn("--- tests/test_progress_bar.py ---", dump)


class TestDiagnosticExport(unittest.TestCase):
    def test_export_saves_bundle_file(self):
        d = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q"], cwd=d, check=True)
        (d / "goal.txt").write_text("Build a thing\n")
        (d / "state.json").write_text(
            '{"activity":[{"ts":"now","iteration":1,"kind":"write","message":"writing src/main.py"}]}'
        )
        bundle = export_diagnostic_bundle(d)
        saved = d / DIAGNOSTIC_BUNDLE_FILENAME
        self.assertEqual(bundle["path"], str(saved))
        self.assertTrue(saved.exists())
        text = saved.read_text()
        self.assertIn("9XF DIAGNOSTIC BUNDLE", text)
        self.assertIn("live activity stream", text)
        exclude = (d / ".git" / "info" / "exclude").read_text()
        self.assertIn(f"/{DIAGNOSTIC_BUNDLE_FILENAME}", exclude)


if __name__ == "__main__":
    unittest.main()
