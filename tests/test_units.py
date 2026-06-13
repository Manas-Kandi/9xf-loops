"""Unit tests for the v0.3/v0.4 modules: tasks, stuck, relevance, candidates,
parser, fitness, config presets."""

from __future__ import annotations

import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from ninexf.backends import BackendError, _post_json, context_overflowed
from ninexf.candidates import CandidateResult, parse_critic_output, pick_winner
from ninexf.config import PRESETS, Config, load_config, write_config
from ninexf.contract import contract_for_prompt, save_contract
from ninexf.dashboard import _run_status
from ninexf.fitness import best_state, final_state, fitness_of
from ninexf.loop import ExecOutcome, _repair_file_dump
from ninexf.relevance import render_partial
from ninexf.parser import parse_executor_output
from ninexf.relevance import score_files
from ninexf.stuck import detect_signals, normalize_error
from ninexf.webapp import DIAGNOSTIC_BUNDLE_FILENAME, export_diagnostic_bundle
from ninexf.tasks import (
    Task, TaskList, load_tasks, parse_decomposition, parse_task_ref,
    parse_task_ref_num, parse_verify_output, sanitize_decomposition,
    save_tasks, strip_task_ref, tasks_for_prompt,
)
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

    def test_tasks_prompt_marks_deferred_ineligible(self):
        d = Path(tempfile.mkdtemp())
        save_tasks(d, TaskList(tasks=[Task(1, "open"), Task(2, "later"), Task(3, "blocked", "!")]))
        prompt = tasks_for_prompt(d)
        self.assertIn("Eligible next task", prompt)
        self.assertIn("T1 (open)", prompt)
        self.assertIn("T2 (queued, not eligible yet)", prompt)
        self.assertIn("T3 (deferred, not eligible)", prompt)

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

    def test_contract_for_prompt(self):
        d = Path(tempfile.mkdtemp())
        save_contract(d, "Build a widget", ["Create src/widget.py"], ["tests pass"])
        contract = contract_for_prompt(d)
        self.assertIn("Build a widget", contract)
        self.assertIn("Create src/widget.py", contract)
        self.assertIn("Tests must be deterministic", contract)
        self.assertIn("Entry points and demos must be bounded", contract)

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
        entries = [self._iter("add the parser"), self._iter("add the writer")]
        sig = {s.kind for s in detect_signals("add the parser", entries, 0.85)}
        self.assertIn("repeat", sig)
        self.assertIn("oscillation", sig)  # matches N-2, not N-1

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


class TestBackendAndStatus(unittest.TestCase):
    def test_post_json_timeout_becomes_backend_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(BackendError, "timeout calling"):
                _post_json("http://127.0.0.1:11434/api/chat", {}, {}, timeout=1)

    def test_running_state_with_dead_pid_is_failed(self):
        state = {"running": True, "pid": 12345, "ts": "2026-06-12T03:38:59+00:00"}
        with mock.patch("ninexf.dashboard._pid_alive", return_value=False):
            self.assertEqual(_run_status(state, delay=5, last_iter_ok=None), "failed")


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

    def test_empty(self):
        self.assertIsNone(best_state([]))
        self.assertIsNone(final_state([{"event": "iteration", "commit": ""}]))


class TestPresets(unittest.TestCase):
    def test_overnight_preset(self):
        d = Path(tempfile.mkdtemp())
        write_config(d, {"model": "mock"}, preset="overnight")
        cfg = load_config(d)
        self.assertEqual(cfg.best_of_n, 3)
        self.assertEqual(cfg.best_of_mode, "always")
        self.assertTrue(cfg.critic_enabled)
        self.assertTrue(cfg.explore_enabled)
        self.assertEqual(cfg.repair_attempts, 2)
        self.assertTrue(cfg.keep_best)
        self.assertTrue(cfg.acceptance_tests)
        self.assertEqual(cfg.max_hours, 8)
        self.assertEqual(cfg.model, "mock", "explicit overrides beat the preset")

    def test_unknown_preset_rejected(self):
        with self.assertRaises(ValueError):
            write_config(Path(tempfile.mkdtemp()), preset="nope")

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
