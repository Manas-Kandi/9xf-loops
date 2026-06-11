"""End-to-end loop tests: one mock scenario per v0.3 phase, run as real loops
in temp dirs, asserting on loop_log.jsonl + git state."""

from __future__ import annotations

import unittest

from tests.helpers import cleanup, events, git, iteration_entries, make_run, run_loop


class TestFinisher(unittest.TestCase):
    """Phase 1: decompose -> build -> verify_done (one FAIL, corrective task)
    -> FINISHED before the iteration cap."""

    def setUp(self):
        self.project = make_run("Greeting tool", "mock/finisher")

    def tearDown(self):
        cleanup(self.project)

    def test_finishes_before_cap(self):
        entries = run_loop(self.project, max_iterations=10)

        self.assertEqual(len(events(entries, "decompose")), 1)
        finished = events(entries, "finished")
        self.assertEqual(len(finished), 1, "run should FINISH")
        self.assertLess(finished[0]["iteration"], 10, "finish before the cap")

        # the first verify intentionally fails one criterion -> corrective task
        verify = events(entries, "verify")
        self.assertEqual(len(verify), 1)
        self.assertIn("corrective", verify[0]["summary"])

        tasks_md = (self.project / "TASKS.md").read_text()
        self.assertEqual(tasks_md.count("[x]"), 3, tasks_md)
        self.assertNotIn("[ ]", tasks_md.splitlines()[1:], "no open tasks left")

        shutdown = events(entries, "shutdown")
        self.assertIn("goal complete", shutdown[-1]["summary"])

        # task targeting: build iterations carried task ids
        iters = iteration_entries(entries)
        self.assertTrue(all(e.get("task_id") for e in iters))


class TestRegressor(unittest.TestCase):
    """Phase 2: green commit, then repeated failures -> stuck signals fire and
    the harness auto-reverts to the green commit (history stays linear)."""

    def setUp(self):
        self.project = make_run("Greeting tool", "mock/regressor")

    def tearDown(self):
        cleanup(self.project)

    def test_auto_revert(self):
        entries = run_loop(self.project, max_iterations=10)

        reverts = [e for e in events(entries, "revert") if e.get("reverted_to")]
        self.assertGreaterEqual(len(reverts), 1, "auto-revert should fire")
        green = reverts[0]["reverted_to"]

        # the revert commit's src tree matches the green commit exactly
        revert_commits = [l for l in git(self.project, "log", "--format=%h %s").splitlines()
                          if "auto-revert" in l]
        self.assertTrue(revert_commits)
        revert_hash = revert_commits[-1].split()[0]  # oldest = first revert
        self.assertEqual(git(self.project, "ls-tree", "--name-only", revert_hash, "--", "src"),
                         git(self.project, "ls-tree", "--name-only", green, "--", "src"))

        # repeated identical failures produce same_error stuck signals
        signals = {s for e in iteration_entries(entries) for s in e.get("stuck_signals", [])}
        self.assertIn("repeat", signals)
        self.assertIn("same_error", signals)

        # never more than 2 reverts to the same commit
        self.assertLessEqual(sum(1 for e in reverts if e["reverted_to"] == green), 2)


class TestExplorer(unittest.TestCase):
    """Phase 5: hard-stuck (stuck signals + failed revert) -> two approaches on
    branches; winner adopted on main, loser kept as *-rejected."""

    def setUp(self):
        self.project = make_run("Greeting tool", "mock/explorer",
                                {"explore_enabled": True})

    def tearDown(self):
        cleanup(self.project)

    def test_branch_explore(self):
        entries = run_loop(self.project, max_iterations=9)

        explores = events(entries, "explore")
        self.assertEqual(len(explores), 1)
        exp = explores[0]["explore"]
        self.assertEqual(exp["winner"], "b", "working approach should win")
        self.assertFalse(exp["a"]["passed"])
        self.assertTrue(exp["b"]["passed"])

        branches = git(self.project, "branch", "--list", "--format=%(refname:short)")
        self.assertIn("-a-rejected", branches, "loser branch kept, renamed")
        self.assertIn("-b", branches)

        # winner's file content was adopted on main at the explore commit
        commit = explores[0]["commit"]
        self.assertIn("beta", git(self.project, "show", f"{commit}:src/feature.py"))

        # the JSONL stayed linear and valid (no per-branch log lines)
        self.assertFalse(events(entries, "corrupt-line"))


class TestRepairer(unittest.TestCase):
    """Overnight v0.4: a failing executor attempt is repaired in the same
    iteration — errors fed straight back — instead of waiting for a fix mode
    round trip the next iteration."""

    def setUp(self):
        self.project = make_run("Greeting tool", "mock/repairer")

    def tearDown(self):
        cleanup(self.project)

    def test_in_iteration_repair(self):
        entries = run_loop(self.project, max_iterations=6)

        iters = iteration_entries(entries)
        self.assertTrue(iters, "should have at least one build iteration")
        first = iters[0]
        self.assertEqual(len(first.get("repairs", [])), 1, first)
        self.assertTrue(first["repairs"][0]["passed"], "repair should end green")
        self.assertTrue(first["validation_passed"],
                        "the iteration's final verdict is the repaired attempt")
        # the broken first attempt never needed a fix-mode iteration
        self.assertEqual(len(events(entries, "finished")), 1)


class TestKeepBest(unittest.TestCase):
    """Overnight v0.4: a run that degrades after a green state ships the best
    state it ever reached, restored at shutdown."""

    def setUp(self):
        # repair can't save the regressor (it always re-emits broken code), so
        # the run ends in a failing state — exactly what keep_best is for
        self.project = make_run("Greeting tool", "mock/regressor")

    def tearDown(self):
        cleanup(self.project)

    def test_best_state_restored_at_shutdown(self):
        entries = run_loop(self.project, max_iterations=8)

        restores = events(entries, "restore_best")
        self.assertEqual(len(restores), 1, "keep_best should fire on a degraded run")
        self.assertTrue(restores[0]["reverted_to"])

        # final working tree is the green state: main.py present, broken
        # feature.py gone
        self.assertTrue((self.project / "src" / "main.py").exists())
        self.assertFalse((self.project / "src" / "feature.py").exists(),
                         "broken file should not survive shutdown")

    def test_keep_best_off_preserves_final_state(self):
        cfg_path = self.project / "9xf.config.json"
        import json as _json
        cfg = _json.loads(cfg_path.read_text())
        cfg["keep_best"] = False
        cfg_path.write_text(_json.dumps(cfg, indent=2) + "\n")
        entries = run_loop(self.project, max_iterations=8)
        self.assertFalse(events(entries, "restore_best"))


class TestTimeBudget(unittest.TestCase):
    """Overnight v0.4: a wall-clock budget ends the run cleanly."""

    def test_zero_budget_stops_immediately(self):
        project = make_run("Greeting tool", "mock/finisher",
                           {"max_hours": 0.0000001})
        try:
            entries = run_loop(project, max_iterations=10)
            shutdown = events(entries, "shutdown")
            self.assertTrue(shutdown)
            self.assertIn("time budget", shutdown[-1]["summary"])
            self.assertFalse(iteration_entries(entries),
                             "no iterations should run on an expired budget")
        finally:
            cleanup(project)


class TestAcceptanceAndDefaultMock(unittest.TestCase):
    """Phase 4 acceptance generation + the v0.2 default mock still works."""

    def test_acceptance_generation(self):
        project = make_run("Greeting tool", "mock/finisher")
        try:
            from ninexf.cli import _generate_acceptance_tests
            _generate_acceptance_tests(project, "Greeting tool")
            suite = project / "acceptance" / "test_acceptance.py"
            self.assertTrue(suite.exists())
            entries = run_loop(project, max_iterations=10)
            finished = events(entries, "finished")
            self.assertEqual(len(finished), 1)
            self.assertTrue(finished[0]["acceptance_passed"],
                            "finish requires the held-out suite green")
        finally:
            cleanup(project)

    def test_default_mock_script(self):
        project = make_run("Greeting tool", "mock")
        try:
            entries = run_loop(project, max_iterations=6)
            iters = iteration_entries(entries)
            self.assertGreaterEqual(len(iters), 5)
            # the scripted broken iteration then the fix
            self.assertFalse(iters[1]["validation_passed"])
            self.assertTrue(iters[2]["validation_passed"])
            self.assertTrue(any(e.get("regression") for e in iters))
        finally:
            cleanup(project)


if __name__ == "__main__":
    unittest.main()
