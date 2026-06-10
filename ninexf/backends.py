"""Model backends: ollama (local, default), anthropic (API), mock (harness testing).

All backends expose one method: complete(system, user) -> str.
Stdlib-only — HTTP via urllib so the harness has zero pip dependencies.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ninexf.config import Config


class BackendError(Exception):
    pass


class Backend:
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


class OllamaBackend(Backend):
    def __init__(self, config: Config):
        self.model = config.model_name
        self.endpoint = config.endpoint.rstrip("/")

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
                "options": {"temperature": temperature if temperature is not None else 0.4,
                            "num_ctx": 16384},
            },
            headers={},
        )
        content = data.get("message", {}).get("content", "")
        if not content:
            raise BackendError(f"empty response from ollama: {json.dumps(data)[:300]}")
        return content


class AnthropicBackend(Backend):
    def __init__(self, config: Config):
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
            return "NO — not complete."
        if "one PASS/FAIL line" in user:
            return "FAIL: C1 — not done\n"
        if "single most useful next step" in user:
            # "--- src/main.py ---" appears in the snapshot only once the file exists
            if "--- src/main.py ---" not in user:
                return "Create src/main.py with a main() function that prints a greeting."
            return "Add the feature module in src/feature.py."
        _, _, sub = user.partition("SUB-TASK FOR THIS ITERATION:")
        if "src/main.py" in sub:
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
        if self.scenario == "finisher":
            return self._finisher(user)
        if self.scenario == "regressor":
            return self._regressor(user)
        if self.scenario == "explorer":
            return self._explorer(user)
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
            # default mock keeps tasks open so the v0.2 script plays out fully
            return "NO — keep building."
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
