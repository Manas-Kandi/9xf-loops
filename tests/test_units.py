"""Unit tests for the v0.3/v0.4 modules: tasks, stuck, relevance, candidates,
parser, fitness, config presets."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ninexf.candidates import CandidateResult, parse_critic_output, pick_winner
from ninexf.config import PRESETS, load_config, write_config
from ninexf.fitness import best_state, final_state, fitness_of
from ninexf.parser import parse_executor_output
from ninexf.relevance import score_files
from ninexf.stuck import detect_signals, normalize_error
from ninexf.tasks import (
    Task, TaskList, load_tasks, parse_decomposition, parse_task_ref,
    parse_verify_output, save_tasks, strip_task_ref,
)


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
        tl = TaskList(tasks=[Task(3, "x")])
        self.assertEqual(parse_task_ref("TASK T3: do x", tl), 3)
        self.assertEqual(parse_task_ref("TASK 3: do x", tl), 3)
        self.assertEqual(parse_task_ref("TASK T9: unknown", tl), 0)
        self.assertEqual(parse_task_ref("just do x", tl), 0)
        self.assertEqual(strip_task_ref("TASK T3: do x"), "do x")

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


class TestParserNotes(unittest.TestCase):
    def test_notes_unfenced_only(self):
        out = parse_executor_output(
            "SUMMARY: x\nNOTE: keep this\nFILE: src/a.py\n"
            "```python\n# NOTE: not this\nx=1\n```\nNOTE: and this\n")
        self.assertEqual(out.notes, ["keep this", "and this"])


if __name__ == "__main__":
    unittest.main()
