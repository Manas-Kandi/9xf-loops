"""Model backends: ollama (local, default), anthropic (API), mock (harness testing).

All backends expose one method: complete(system, user) -> str.
Stdlib-only — HTTP via urllib so the harness has zero pip dependencies.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request

from ninexf.config import Config


class BackendError(Exception):
    pass


def context_overflowed(prompt_tokens: int | None, num_ctx: int) -> bool:
    """Did the prompt fill (and therefore overflow) the context window?
    Ollama truncates silently from the TOP when the prompt exceeds num_ctx —
    dropping the system prompt and goal first, which makes the loop aimless
    with no error anywhere. prompt_eval_count brushing num_ctx is the tell."""
    return prompt_tokens is not None and prompt_tokens >= num_ctx - 64


class Backend:
    def __init__(self):
        self._overflowed = False

    def note_overflow(self) -> None:
        self._overflowed = True

    def take_overflow(self) -> bool:
        """Sticky overflow flag: True if any call since the last take filled
        the context window. The loop reads this once per iteration entry."""
        v = self._overflowed
        self._overflowed = False
        return v

    def complete(self, system: str, user: str, temperature: float | None = None) -> str:
        """temperature=None means the backend's default (used by best-of-N
        candidate sampling to vary candidates)."""
        raise NotImplementedError


def _post_json(url: str, payload: dict, headers: dict, timeout: float = 300) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:500]
        raise BackendError(f"HTTP {e.code} from {url}: {body}") from e
    except urllib.error.URLError as e:
        raise BackendError(f"cannot reach {url}: {e.reason}") from e
    except (TimeoutError, socket.timeout) as e:
        raise BackendError(f"timeout calling {url} after {timeout:g}s") from e
    except json.JSONDecodeError as e:
        raise BackendError(f"invalid JSON from {url}: {e}") from e


class OllamaBackend(Backend):
    def __init__(self, config: Config):
        super().__init__()
        self.model = config.model_name
        self.endpoint = config.endpoint.rstrip("/")
        self.num_ctx = config.num_ctx
        self.default_temperature = config.temperature

    def complete(self, system: str, user: str, temperature: float | None = None) -> str:
        data = _post_json(
            f"{self.endpoint}/api/chat",
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": temperature if temperature is not None
                            else self.default_temperature,
                            "num_ctx": self.num_ctx},
            },
            headers={},
        )
        if context_overflowed(data.get("prompt_eval_count"), self.num_ctx):
            self.note_overflow()
            print(f"[9xf] WARNING: prompt filled the context window "
                  f"({data.get('prompt_eval_count')} / num_ctx {self.num_ctx}) — "
                  f"ollama truncates from the top; raise num_ctx in 9xf.config.json")
        content = data.get("message", {}).get("content", "")
        if not content:
            raise BackendError(f"empty response from ollama: {json.dumps(data)[:300]}")
        return content


class AnthropicBackend(Backend):
    def __init__(self, config: Config):
        super().__init__()
        self.model = config.model_name
        self.api_key = os.environ.get(config.api_key_env, "")
        if not self.api_key:
            raise BackendError(
                f"API mode requires {config.api_key_env} to be set in the environment"
            )

    def complete(self, system: str, user: str, temperature: float | None = None) -> str:
        payload = {
            "model": self.model,
            "max_tokens": 8192,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        if temperature is not None:
            payload["temperature"] = min(1.0, temperature)
        data = _post_json(
            "https://api.anthropic.com/v1/messages",
            payload,
            headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
        )
        blocks = data.get("content", [])
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        if not text:
            raise BackendError(f"empty response from anthropic: {json.dumps(data)[:300]}")
        return text


class MockBackend(Backend):
    """Deterministic scripted backend so the loop harness can be tested end-to-end
    without inference. The script deliberately exercises every loop feature:
    a broken commit (-> fix mode + regression flag), a repeated subtask
    (-> stuck nudge), tool creation + RUN_TOOL, and a unittest test file.

    Scenario variants (selected via `mock/<scenario>` in the config) script
    specific v0.3 behaviors for the harness's own test suite."""

    def __init__(self, scenario: str = ""):
        super().__init__()
        self.scenario = scenario
        self._verify_calls = 0

    # -- finisher scenario: drives decompose -> build -> verify_done -> FINISHED.
    # The first verify intentionally FAILs one criterion so the corrective-task
    # path is exercised before the run completes.

    def _finisher(self, user: str) -> str:
        if "Break this goal down" in user:
            return (
                "TASK: Create src/main.py with a main() function that prints a greeting.\n"
                "TASK: Add a unit test for main() in tests/test_main.py.\n"
                "CRITERION: running `python src/main.py` exits 0\n"
                "CRITERION: tests in tests/ pass and assert the greeting text\n"
            )
        if "First line: YES or NO" in user:
            return "YES — the task is complete."
        if "one PASS/FAIL line" in user:
            self._verify_calls += 1
            if self._verify_calls == 1:
                return "PASS: C1\nFAIL: C2 — the test does not assert the greeting text\n"
            return "PASS: C1\nPASS: C2\n"
        if "single most useful next step" in user:
            if "T1 (DONE)" not in user:
                return "TASK T1: Create src/main.py with a main() function that prints a greeting."
            if "T2 (DONE)" not in user:
                return "TASK T2: Add a unit test for main() in tests/test_main.py."
            return "TASK T3: Fix the test to assert the greeting text."
        _, _, sub = user.partition("SUB-TASK FOR THIS ITERATION:")
        if "greeting text" in sub:
            return (
                "SUMMARY: Tightened the test to assert the greeting text.\n"
                "FILE: tests/test_main.py\n"
                "```python\n"
                "import subprocess, sys, unittest\n\n"
                "class TestMain(unittest.TestCase):\n"
                "    def test_greeting(self):\n"
                "        out = subprocess.run([sys.executable, 'src/main.py'],\n"
                "                             capture_output=True, text=True)\n"
                "        self.assertEqual(out.returncode, 0)\n"
                "        self.assertIn('hello', out.stdout)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
                "```\n"
            )
        if "unit test" in sub:
            return (
                "SUMMARY: Added a unittest for main().\n"
                "FILE: tests/test_main.py\n"
                "```python\n"
                "import subprocess, sys, unittest\n\n"
                "class TestMain(unittest.TestCase):\n"
                "    def test_main_runs(self):\n"
                "        out = subprocess.run([sys.executable, 'src/main.py'], capture_output=True)\n"
                "        self.assertEqual(out.returncode, 0)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
                "```\n"
            )
        return (
            "SUMMARY: Created src/main.py with a greeting.\n"
            "FILE: src/main.py\n"
            "```python\n"
            "def main():\n"
            "    print('hello from 9xf')\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
            "```\n"
        )

    # -- regressor scenario: one green iteration, then endless broken code.
    # Exercises fix mode, same_error stuck signals, and auto-revert.

    def _regressor(self, user: str) -> str:
        if "Break this goal down" in user:
            return (
                "TASK: Create the entry point that prints a greeting.\n"
                "TASK: Add the feature module.\n"
                "CRITERION: running the entry point exits 0\n"
            )
        if "First line: YES or NO" in user:
            return "YES — complete."
        if "one PASS/FAIL line" in user:
            return "FAIL: C1 — not done\n"
        if "single most useful next step" in user:
            # "--- src/main.py ---" appears in the snapshot only once the file exists
            if "--- src/main.py ---" not in user:
                return "Create src/main.py with a main() function that prints a greeting."
            return "Add the feature module in src/feature.py."
        _, _, sub = user.partition("SUB-TASK FOR THIS ITERATION:")
        if "src/main.py" in sub or "entry point" in sub or "prints a greeting" in sub:
            return (
                "SUMMARY: Created src/main.py with a greeting.\n"
                "FILE: src/main.py\n"
                "```python\n"
                "def main():\n"
                "    print('hello from 9xf')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
                "```\n"
            )
        return (
            "SUMMARY: Added the feature module (broken).\n"
            "FILE: src/feature.py\n"
            "```python\n"
            "def feature(:\n"
            "    return 1\n"
            "```\n"
        )

    # -- repairer scenario: every first executor attempt is broken; the
    # in-iteration repair prompt fixes it. Exercises the repair loop end-to-end.

    def _repairer(self, user: str) -> str:
        if "Break this goal down" in user:
            return (
                "TASK: Create src/main.py with a main() function that prints a greeting.\n"
                "TASK: Add a unit test for main() in tests/test_main.py.\n"
                "CRITERION: running `python src/main.py` exits 0\n"
            )
        if "First line: YES or NO" in user:
            return "YES — the task is complete."
        if "one PASS/FAIL line" in user:
            return "PASS: C1\n"
        if "single most useful next step" in user:
            if "T1 (DONE)" not in user:
                return "TASK T1: Create src/main.py with a main() function that prints a greeting."
            return "TASK T2: Add a unit test for main() in tests/test_main.py."
        _, _, sub = user.partition("SUB-TASK FOR THIS ITERATION:")
        if "FAILED VALIDATION" in sub:
            return (
                "SUMMARY: Fixed the syntax error in main.py.\n"
                "FILE: src/main.py\n"
                "```python\n"
                "def main():\n"
                "    print('hello from 9xf')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
                "```\n"
            )
        if "unit test" in sub:
            return (
                "SUMMARY: Added a unittest for main().\n"
                "FILE: tests/test_main.py\n"
                "```python\n"
                "import subprocess, sys, unittest\n\n"
                "class TestMain(unittest.TestCase):\n"
                "    def test_main_runs(self):\n"
                "        out = subprocess.run([sys.executable, 'src/main.py'], capture_output=True)\n"
                "        self.assertEqual(out.returncode, 0)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
                "```\n"
            )
        return (
            "SUMMARY: Created src/main.py (broken on the first try).\n"
            "FILE: src/main.py\n"
            "```python\n"
            "def main(:\n"
            "    print('hello from 9xf')\n"
            "```\n"
        )

    # -- explorer scenario: regressor behavior until the harness triggers
    # branch-and-explore; approach A stays broken, approach B works.

    def _explorer(self, user: str) -> str:
        if "Another planner already proposed" in user:
            return "Implement the feature with approach beta."
        if "THE LOOP IS HARD-STUCK" in user:
            return "Implement the feature with approach alpha."
        _, _, sub = user.partition("SUB-TASK FOR THIS ITERATION:")
        if "approach alpha" in sub:
            return (
                "SUMMARY: Feature via approach alpha (still broken).\n"
                "FILE: src/feature.py\n"
                "```python\n"
                "def feature(:\n"
                "    return 'alpha'\n"
                "```\n"
            )
        if "approach beta" in sub:
            return (
                "SUMMARY: Feature via approach beta (working).\n"
                "FILE: src/feature.py\n"
                "```python\n"
                "def feature():\n"
                "    return 'beta'\n"
                "```\n"
            )
        return self._regressor(user)

    def _bad_decompose(self, user: str) -> str:
        if "Break this goal down" in user and "previous decomposition" not in user:
            return (
                "TASK: Create src/main.py with the progress bar entry point.\n"
                "TASK: Initialize a virtual environment in the project root.\n"
                "TASK: Update `.gitignore` for venv artifacts.\n"
                "CRITERION: running `flake8 src/progress_bar` produces no errors.\n"
                "CRITERION: a venv directory exists and is active.\n"
            )
        if "Break this goal down" in user:
            return (
                "TASK: Create src/main.py with the progress bar entry point.\n"
                "TASK: Add src/progress_bar.py with a ProgressBar class.\n"
                "TASK: Add unittest coverage in tests/test_progress_bar.py.\n"
                "CRITERION: running `python src/main.py` exits 0.\n"
                "CRITERION: unittest discovery passes.\n"
            )
        return self._finisher(user)

    def _deferred_retry(self, user: str) -> str:
        if "Break this goal down" in user:
            return (
                "TASK: Add a broken module in src/broken.py.\n"
                "TASK: Create src/main.py with a main() function that prints a greeting.\n"
                "CRITERION: running `python src/main.py` exits 0\n"
            )
        if "First line: YES or NO" in user:
            return "YES — complete."
        if "single most useful next step" in user:
            return "TASK T1: Add a broken module in src/broken.py."
        _, _, sub = user.partition("SUB-TASK FOR THIS ITERATION:")
        if "main.py" in sub or "greeting" in sub:
            return (
                "SUMMARY: Created the greeting entry point.\n"
                "FILE: src/main.py\n"
                "```python\n"
                "def main():\n"
                "    print('hello')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
                "```\n"
            )
        return (
            "SUMMARY: Added a broken module.\n"
            "FILE: src/broken.py\n"
            "```python\n"
            "def broken(:\n"
            "    return 1\n"
            "```\n"
        )

    def _slow_test(self, user: str) -> str:
        if "Break this goal down" in user:
            return (
                "TASK: Create src/main.py with a main() function.\n"
                "TASK: Add a slow unittest in tests/test_main.py.\n"
                "CRITERION: unittest discovery passes\n"
            )
        if "First line: YES or NO" in user:
            return "YES — complete."
        if "single most useful next step" in user:
            if "T1 (DONE)" not in user:
                return "TASK T1: Create src/main.py with a main() function."
            return "TASK T2: Add a slow unittest in tests/test_main.py."
        _, _, sub = user.partition("SUB-TASK FOR THIS ITERATION:")
        if "slow unittest" in sub:
            return (
                "SUMMARY: Added a slow unittest.\n"
                "FILE: tests/test_main.py\n"
                "```python\n"
                "import time\n"
                "import unittest\n\n"
                "class TestMain(unittest.TestCase):\n"
                "    def test_slow(self):\n"
                "        time.sleep(1)\n"
                "        self.assertTrue(True)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
                "```\n"
            )
        return (
            "SUMMARY: Created src/main.py.\n"
            "FILE: src/main.py\n"
            "```python\n"
            "def main():\n"
            "    return 0\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
            "```\n"
        )

    def _unknown_tool(self, user: str) -> str:
        if "Break this goal down" in user:
            return (
                "TASK: Create src/main.py and request an unavailable tool.\n"
                "TASK: Add a unit test for main.\n"
                "CRITERION: validation passes\n"
            )
        if "First line: YES or NO" in user:
            return "YES — complete."
        if "single most useful next step" in user:
            return "TASK T1: Create src/main.py and request an unavailable tool."
        return (
            "SUMMARY: Created src/main.py and requested pytest.\n"
            "FILE: src/main.py\n"
            "```python\n"
            "def main():\n"
            "    print('hello')\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
            "```\n"
            "RUN_TOOL: pytest tests/\n"
        )

    def _unittest_tool(self, user: str) -> str:
        if "Break this goal down" in user:
            return (
                "TASK: Create src/main.py and request unittest discovery.\n"
                "CRITERION: validation passes\n"
            )
        if "First line: YES or NO" in user:
            return "YES — complete."
        if "one PASS/FAIL line" in user:
            return "PASS: C1\n"
        if "single most useful next step" in user:
            return "TASK T1: Create src/main.py and request unittest discovery."
        return (
            "SUMMARY: Created src/main.py and requested built-in unittest validation.\n"
            "FILE: src/main.py\n"
            "```python\n"
            "def main():\n"
            "    print('hello')\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
            "```\n"
            "RUN_TOOL: unittest discover -s tests\n"
        )

    def _tests_fail_and_unknown_tool(self, user: str) -> str:
        if "Break this goal down" in user:
            return (
                "TASK: Add a broken unittest and request an unavailable tool.\n"
                "TASK: Fix the unittest.\n"
                "CRITERION: validation passes\n"
            )
        if "First line: YES or NO" in user:
            return "NO — tests fail."
        if "single most useful next step" in user:
            return "TASK T1: Add a broken unittest and request an unavailable tool."
        return (
            "SUMMARY: Added a broken unittest and requested flake8.\n"
            "FILE: tests/test_main.py\n"
            "```python\n"
            "import unittest\n\n"
            "class TestMain(unittest.TestCase):\n"
            "    def test_broken(self):\n"
            "        self.assertEqual(1, 2)\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n"
            "```\n"
            "RUN_TOOL: flake8 tests/\n"
        )

    def _jump_ahead(self, user: str) -> str:
        if "Break this goal down" in user:
            return (
                "TASK: Create src/main.py with a main() function.\n"
                "TASK: Add tests/test_main.py for main.\n"
                "CRITERION: unittest discovery passes\n"
            )
        if "First line: YES or NO" in user:
            return "YES — complete."
        if "single most useful next step" in user:
            return "TASK T2: Add tests/test_main.py for main."
        _, _, sub = user.partition("SUB-TASK FOR THIS ITERATION:")
        if "src/main.py" in sub:
            return (
                "SUMMARY: Created src/main.py.\n"
                "FILE: src/main.py\n"
                "```python\n"
                "def main():\n"
                "    return 'hello'\n\n"
                "if __name__ == '__main__':\n"
                "    print(main())\n"
                "```\n"
            )
        return (
            "SUMMARY: Added main tests.\n"
            "FILE: tests/test_main.py\n"
            "```python\n"
            "import unittest\n"
            "from src.main import main\n\n"
            "class TestMain(unittest.TestCase):\n"
            "    def test_main(self):\n"
            "        self.assertEqual(main(), 'hello')\n\n"
            "if __name__ == '__main__':\n"
            "    unittest.main()\n"
            "```\n"
        )

    def _plan(self, user: str) -> str:
        if "You are repeating yourself" in user:
            return "Create a helper tool tools/line_count.py that counts lines of source code."
        if "FIX ITERATION" in user:
            return "Fix the syntax error in src/validate_input.py."
        if "REVIEW ITERATION" in user:
            return "Add a unit test for main() in tests/test_main.py."
        # "--- <path> ---" markers appear in the snapshot only once a file exists,
        # so key on those (the v0.3 task list may mention paths before they exist)
        if "--- src/main.py ---" not in user:
            return "Create src/main.py with a main() function that prints a greeting."
        if "--- src/validate_input.py ---" not in user:
            return "Add input validation in src/validate_input.py."
        if "--- tools/line_count.py ---" not in user:
            # deliberate repeat of the fix subtask to trigger stuck detection
            return "Fix the syntax error in src/validate_input.py."
        return "Improve the docstrings in src/main.py."

    def complete(self, system: str, user: str, temperature: float | None = None) -> str:
        # branches shared by every scenario (acceptance generation, critic)
        if "Write the acceptance test file now" in user:
            return (
                "FILE: acceptance/test_acceptance.py\n"
                "```python\n"
                "import subprocess, sys, unittest\n\n"
                "class TestAcceptance(unittest.TestCase):\n"
                "    def test_entry_point_runs(self):\n"
                "        out = subprocess.run([sys.executable, 'src/main.py'],\n"
                "                             capture_output=True, text=True)\n"
                "        self.assertEqual(out.returncode, 0)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
                "```\n"
            )
        if "Judge the change now" in user:
            return "VERDICT: ACCEPT"
        if "Diagnose now" in user:
            return "CAUSE: the same validation error recurred.\nPATCH_PLAN: make the smallest code change that directly addresses the traceback."
        if self.scenario == "finisher":
            return self._finisher(user)
        if self.scenario == "regressor":
            return self._regressor(user)
        if self.scenario == "explorer":
            return self._explorer(user)
        if self.scenario == "repairer":
            return self._repairer(user)
        if self.scenario == "bad_decompose":
            return self._bad_decompose(user)
        if self.scenario == "deferred_retry":
            return self._deferred_retry(user)
        if self.scenario == "slow_test":
            return self._slow_test(user)
        if self.scenario == "unknown_tool":
            return self._unknown_tool(user)
        if self.scenario == "unittest_tool":
            return self._unittest_tool(user)
        if self.scenario == "tests_fail_unknown_tool":
            return self._tests_fail_and_unknown_tool(user)
        if self.scenario == "jump_ahead":
            return self._jump_ahead(user)
        # v0.3 harness prompts (decompose / task-check / verify-done)
        if "Break this goal down" in user:
            return (
                "TASK: Create src/main.py with a main() function that prints a greeting.\n"
                "TASK: Add input validation in src/validate_input.py.\n"
                "TASK: Add a unit test for main() in tests/test_main.py.\n"
                "CRITERION: running `python src/main.py` exits 0\n"
                "CRITERION: tests in tests/ pass\n"
            )
        if "First line: YES or NO" in user:
            return "YES — complete."
        if "one PASS/FAIL line" in user:
            return "PASS: C1\nPASS: C2\n"
        if "single most useful next step" in user:
            return self._plan(user)

        # Execution call — key off the sub-task section only (the codebase
        # snapshot above it would otherwise match every branch).
        _, _, user = user.partition("SUB-TASK FOR THIS ITERATION:")
        if "Add input validation" in user:
            return (
                "SUMMARY: Added input validation (contains a deliberate syntax error).\n"
                "FILE: src/validate_input.py\n"
                "```python\n"
                "def validate(value:\n"
                "    return bool(value)\n"
                "```\n"
            )
        if "Fix the syntax error" in user:
            return (
                "SUMMARY: Fixed the syntax error in validate_input.py.\n"
                "FILE: src/validate_input.py\n"
                "```python\n"
                "def validate(value):\n"
                "    return bool(value)\n"
                "```\n"
            )
        if "tools/line_count.py" in user or "helper tool" in user:
            return (
                "SUMMARY: Created a line-counting helper tool and ran it.\n"
                "FILE: tools/line_count.py\n"
                "```python\n"
                '"""Count lines in src/*.py files."""\n'
                "from pathlib import Path\n\n"
                "total = sum(len(p.read_text().splitlines()) for p in Path('src').glob('*.py'))\n"
                "print(f'{total} lines in src/')\n"
                "```\n"
                "RUN_TOOL: line_count\n"
            )
        if "unit test" in user:
            return (
                "SUMMARY: Added a unittest for main().\n"
                "FILE: tests/test_main.py\n"
                "```python\n"
                "import subprocess, sys, unittest\n\n"
                "class TestMain(unittest.TestCase):\n"
                "    def test_main_runs(self):\n"
                "        out = subprocess.run([sys.executable, 'src/main.py'], capture_output=True)\n"
                "        self.assertEqual(out.returncode, 0)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
                "```\n"
            )
        if "docstrings" in user:
            return (
                "SUMMARY: Improved docstrings in main.py.\n"
                "NOTE: main.py is the entry point; keep the greeting in one place.\n"
                "FILE: src/main.py\n"
                "```python\n"
                '"""Entry point for the greeting tool."""\n\n'
                "def main():\n"
                '    """Print a friendly greeting."""\n'
                "    print('hello from 9xf')\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
                "```\n"
            )
        return (
            "SUMMARY: Created src/main.py with a greeting.\n"
            "FILE: src/main.py\n"
            "```python\n"
            "def main():\n"
            "    print('hello from 9xf')\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
            "```\n"
        )


def make_backend(config: Config) -> Backend:
    provider = config.provider
    if provider == "ollama":
        return OllamaBackend(config)
    if provider == "anthropic":
        return AnthropicBackend(config)
    if provider == "mock":
        scenario = config.model.split("/", 1)[1] if "/" in config.model else ""
        return MockBackend(scenario)
    raise BackendError(f"unknown provider {provider!r} (use ollama/<model>, anthropic/<model>, or mock)")
