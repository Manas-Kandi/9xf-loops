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
