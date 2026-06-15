"""End-to-end tests for the `9xf app` server: start a session through the
HTTP API with a mock model, watch it run to FINISHED, fetch the chat feed and
a commit diff — the same calls the web/Electron UI makes."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from ninexf.webapp import make_server
from ninexf.looplog import LogEntry, append_entry, now_iso
from ninexf.registry import append_activity, write_state
from tests.helpers import cleanup

os.environ.setdefault("NINEXF_APP_DIR", tempfile.mkdtemp(prefix="loopy-app-"))


def _get(url: str) -> dict | list:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _post(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


class TestWebApp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server(0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_page_and_static_endpoints(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as resp:
            html = resp.read().decode()
        self.assertIn("Get started", html)
        self.assertIn("diffpane", html)
        self.assertIsInstance(_get(self.base + "/api/runs"), list)
        b = _get(self.base + "/api/browse?path=")
        self.assertIn("dirs", b)
        self.assertTrue(b["path"])
        onboarding = _get(self.base + "/api/onboarding")
        self.assertIn("needs_onboarding", onboarding)
        self.assertIn("settings", onboarding)

    def test_settings_round_trip_and_validation_endpoints(self):
        onboarding = _get(self.base + "/api/onboarding")
        self.assertTrue(onboarding["needs_onboarding"])

        saved = _post(self.base + "/api/settings", {
            "preferred_mode": "api",
            "api_model": "mistral/mistral-small-2603",
            "api_key": "test-key",
            "onboarding_complete": True,
        })
        self.assertTrue(saved.get("ok"), saved)
        self.assertTrue(saved["settings"]["api_key_present"])
        self.assertTrue(saved["settings"]["onboarding_complete"])

        settings = _get(self.base + "/api/settings")
        self.assertEqual(settings["preferred_mode"], "api")
        self.assertEqual(settings["api_model"], "mistral/mistral-small-2603")
        self.assertTrue(settings["api_key_present"])

        bad_provider = _post(self.base + "/api/validate/provider", {
            "model": "mistral/mistral-small-2603",
            "api_key": "",
        })
        self.assertFalse(bad_provider.get("ok"))
        self.assertIn("API key", bad_provider.get("error", ""))

        good_provider = _post(self.base + "/api/validate/provider", {
            "model": "mistral/mistral-small-2603",
            "api_key": "test-key",
        })
        self.assertTrue(good_provider.get("ok"))
        self.assertEqual(good_provider["provider"], "mistral")

        ollama = _post(self.base + "/api/validate/ollama", {
            "endpoint": "http://127.0.0.1:65534",
        })
        self.assertFalse(ollama.get("ok"))
        self.assertIn("Ollama", ollama.get("error", ""))

    def test_start_run_watch_finish_and_diff(self):
        d = Path(tempfile.mkdtemp(prefix="9xf-webapp-")).resolve()
        try:
            r = _post(self.base + "/api/start", {
                "dir": str(d), "goal": "Greeting tool",
                "model": "mock/finisher", "iterations": 10, "delay": 0,
            })
            self.assertTrue(r.get("ok"), r)

            detail = {}
            deadline = time.time() + 60
            while time.time() < deadline:
                detail = _get(self.base + f"/api/run?dir={d}")
                if detail.get("finished"):
                    break
                time.sleep(0.5)
            self.assertTrue(detail.get("finished"), f"run never finished: {detail}")

            events = [e["event"] for e in detail["entries"]]
            self.assertIn("decompose", events)
            self.assertIn("iteration", events)
            self.assertIn("finished", events)
            iters = [e for e in detail["entries"] if e["event"] == "iteration"]
            self.assertTrue(all("subtask" in e and "summary" in e for e in iters))

            committed = next(e for e in iters if e["commit"])
            diff = _get(self.base + f"/api/diff?dir={d}&commit={committed['commit']}")
            self.assertNotIn("error", diff)
            self.assertIn("src/main.py", diff["diff"])

            bundle = _get(self.base + f"/api/export?dir={d}")
            self.assertNotIn("error", bundle)
            text = bundle["text"]
            self.assertIn("9XF DIAGNOSTIC BUNDLE", text)
            self.assertIn("===== goal.txt =====", text)
            self.assertIn("===== loop_log.jsonl =====", text)
            self.assertIn("===== run.out =====", text)
            self.assertIn("===== FILE src/main.py =====", text)
            self.assertIn("Greeting tool", text)

            # stop endpoint drops the STOP file even on a finished run
            r = _post(self.base + "/api/stop", {"dir": str(d)})
            self.assertTrue(r.get("ok"))
            self.assertTrue((d / "STOP").exists())
        finally:
            cleanup(d)

    def test_start_requires_goal_for_new_dir(self):
        d = Path(tempfile.mkdtemp(prefix="9xf-webapp-")).resolve()
        try:
            r = _post(self.base + "/api/start", {"dir": str(d), "goal": ""})
            self.assertIn("goal", r.get("error", ""))
        finally:
            cleanup(d)

    def test_start_uses_saved_default_model_when_none_is_provided(self):
        _post(self.base + "/api/settings", {
            "preferred_mode": "ollama",
            "preferred_model": "mock/finisher",
            "onboarding_complete": True,
        })
        d = Path(tempfile.mkdtemp(prefix="9xf-webapp-")).resolve()
        try:
            r = _post(self.base + "/api/start", {
                "dir": str(d),
                "goal": "Greeting tool",
                "iterations": 10,
                "delay": 0,
            })
            self.assertTrue(r.get("ok"), r)
            deadline = time.time() + 60
            while time.time() < deadline:
                detail = _get(self.base + f"/api/run?dir={d}")
                if detail.get("finished"):
                    break
                time.sleep(0.5)
            self.assertTrue(detail.get("finished"), f"run never finished: {detail}")
        finally:
            cleanup(d)

    def test_live_state_entry_when_log_has_not_caught_up(self):
        from ninexf.cli import init_project
        d = Path(tempfile.mkdtemp(prefix="9xf-webapp-")).resolve()
        try:
            init_project(d, "Progress bar", model="mock")
            append_entry(d, LogEntry(
                iteration=0, timestamp=now_iso(), subtask="",
                summary="run started", event="startup",
            ))
            write_state(d, running=True, iteration=1, mode="decompose",
                        subtask="(decomposing goal)", ts=now_iso())
            append_activity(d, "asking model to decompose the goal",
                            iteration=1, kind="model")
            detail = _get(self.base + f"/api/run?dir={d}")
            live = [e for e in detail["entries"] if e["event"] == "live"]
            self.assertEqual(len(live), 1)
            self.assertEqual(live[0]["mode"], "decompose")
            self.assertIn("decomposing", live[0]["subtask"])
            activity = [e for e in detail["entries"] if e["event"] == "activity"]
            self.assertTrue(activity)
            self.assertIn("decompose", activity[-1]["summary"])
        finally:
            cleanup(d)

    def test_bad_requests_are_contained(self):
        diff = _get(self.base + f"/api/diff?dir=/nonexistent&commit=zzz")
        self.assertIn("error", diff)
        detail = _get(self.base + "/api/run?dir=/nonexistent")
        self.assertIn("error", detail)


if __name__ == "__main__":
    unittest.main()
