"""Load and validate the per-project 9xf.config.json.

The config is written once by `9xf init` and never modified by the agent.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from ninexf import CONFIG_FILENAME
from ninexf.models import DEFAULT_MODEL

DEFAULTS = {
    "model": DEFAULT_MODEL,
    "endpoint": "http://localhost:11434",
    "backend_timeout": 900,
    "max_tokens": 16384,
    "max_iterations": 50,
    "delay_seconds": 5,
    "validation_timeout": 10,
    "allow_network": False,
    "context_char_budget": 0,  # 0 = auto: derived from num_ctx (see snapshot_budget)
    "history_entries_in_context": 15,
    "api_key_env": "ANTHROPIC_API_KEY",
    "review_every": 5,
    "stuck_similarity": 0.85,
    "max_tool_runs_per_iteration": 3,
    "tools_enabled": True,
    "run_tests": True,
    "decompose_enabled": True,
    "control_mode": "hybrid",  # hybrid | strict | freeform
    "max_task_failures": 3,
    "max_verify_attempts": 3,
    "revert_after_failures": 3,
    "context_strategy": "relevance",  # relevance | brute (v0.2 control)
    "diff_char_budget": 3000,
    "notes_enabled": True,
    "notes_max_lines": 40,
    "max_notes_per_iteration": 2,
    "reflection_enabled": True,
    "reflection_every": 2,
    "reflection_max_notes": 3,
    "acceptance_tests": False,
    "critic_enabled": False,
    "critic_max_revisions": 1,
    "best_of_n": 1,
    "best_of_mode": "fix",  # fix | always | off
    "explore_enabled": False,
    "explore_after_stuck": 3,
    "max_explores_per_run": 2,
    "repair_attempts": 1,  # in-iteration fix-it-now retries after failed validation
    "format_retry_attempts": 1,  # immediate retry when executor output is not parseable
    "keep_best": True,  # restore the best-scoring state at shutdown if final is worse
    "max_hours": 0,  # wall-clock budget for a run (0 = no time limit)
    "num_ctx": 16384,  # ollama context window
    "temperature": 0.4,  # default sampling temperature (best-of-N still varies it)
    "top_p": 1.0,
}

NVIDIA_ENDPOINT = "https://integrate.api.nvidia.com/v1"

# Named presets applied at init (`9xf init --preset overnight`). A preset is a
# layer between DEFAULTS and explicit CLI overrides. "overnight" trades wall
# time for quality: maximum search (best-of-N always, critic, explore, repair),
# held-out acceptance tests, and a long leash — the bet being that a small
# local model plus hours of verified search approaches big-model quality.
PRESETS = {
    "overnight": {
        "max_iterations": 1000,
        "delay_seconds": 0,
        "backend_timeout": 1200,
        "max_hours": 8,
        "review_every": 4,
        "validation_timeout": 20,
        "best_of_n": 3,
        "best_of_mode": "always",
        "critic_enabled": True,
        "explore_enabled": True,
        "max_explores_per_run": 4,
        "repair_attempts": 2,
        "format_retry_attempts": 2,
        "reflection_enabled": True,
        "reflection_every": 1,
        "reflection_max_notes": 4,
        "max_task_failures": 4,
        "max_verify_attempts": 5,
        "acceptance_tests": True,
        "keep_best": True,
    },
    # The control condition for benchmarking: decompose + validate, but none of
    # the overnight search machinery (no best-of-N, critic, explore, repair,
    # reflection, or keep-best). Isolates "what does the search actually buy?"
    "baseline": {
        "best_of_n": 1,
        "best_of_mode": "off",
        "critic_enabled": False,
        "explore_enabled": False,
        "repair_attempts": 0,
        "format_retry_attempts": 1,
        "reflection_enabled": False,
        "keep_best": False,
        "acceptance_tests": False,
    },
}


@dataclass
class Config:
    model: str = DEFAULTS["model"]
    endpoint: str = DEFAULTS["endpoint"]
    backend_timeout: float = DEFAULTS["backend_timeout"]
    max_tokens: int = DEFAULTS["max_tokens"]
    max_iterations: int = DEFAULTS["max_iterations"]
    delay_seconds: float = DEFAULTS["delay_seconds"]
    validation_timeout: float = DEFAULTS["validation_timeout"]
    allow_network: bool = DEFAULTS["allow_network"]
    context_char_budget: int = DEFAULTS["context_char_budget"]
    history_entries_in_context: int = DEFAULTS["history_entries_in_context"]
    api_key_env: str = DEFAULTS["api_key_env"]
    review_every: int = DEFAULTS["review_every"]
    stuck_similarity: float = DEFAULTS["stuck_similarity"]
    max_tool_runs_per_iteration: int = DEFAULTS["max_tool_runs_per_iteration"]
    tools_enabled: bool = DEFAULTS["tools_enabled"]
    run_tests: bool = DEFAULTS["run_tests"]
    decompose_enabled: bool = DEFAULTS["decompose_enabled"]
    control_mode: str = DEFAULTS["control_mode"]
    max_task_failures: int = DEFAULTS["max_task_failures"]
    max_verify_attempts: int = DEFAULTS["max_verify_attempts"]
    revert_after_failures: int = DEFAULTS["revert_after_failures"]
    context_strategy: str = DEFAULTS["context_strategy"]
    diff_char_budget: int = DEFAULTS["diff_char_budget"]
    notes_enabled: bool = DEFAULTS["notes_enabled"]
    notes_max_lines: int = DEFAULTS["notes_max_lines"]
    max_notes_per_iteration: int = DEFAULTS["max_notes_per_iteration"]
    reflection_enabled: bool = DEFAULTS["reflection_enabled"]
    reflection_every: int = DEFAULTS["reflection_every"]
    reflection_max_notes: int = DEFAULTS["reflection_max_notes"]
    acceptance_tests: bool = DEFAULTS["acceptance_tests"]
    critic_enabled: bool = DEFAULTS["critic_enabled"]
    critic_max_revisions: int = DEFAULTS["critic_max_revisions"]
    best_of_n: int = DEFAULTS["best_of_n"]
    best_of_mode: str = DEFAULTS["best_of_mode"]
    explore_enabled: bool = DEFAULTS["explore_enabled"]
    explore_after_stuck: int = DEFAULTS["explore_after_stuck"]
    max_explores_per_run: int = DEFAULTS["max_explores_per_run"]
    repair_attempts: int = DEFAULTS["repair_attempts"]
    format_retry_attempts: int = DEFAULTS["format_retry_attempts"]
    keep_best: bool = DEFAULTS["keep_best"]
    max_hours: float = DEFAULTS["max_hours"]
    num_ctx: int = DEFAULTS["num_ctx"]
    temperature: float = DEFAULTS["temperature"]
    top_p: float = DEFAULTS["top_p"]
    extra: dict = field(default_factory=dict)

    @property
    def snapshot_budget(self) -> int:
        """Char budget for the codebase snapshot. When context_char_budget is 0
        (auto), it's derived from num_ctx so the two can't drift apart: reserve
        ~2k tokens for the model's reply, give the snapshot ~60% of what's left
        (history/tasks/notes/diff share the rest), at ~4 chars per token.
        v0.4 and earlier had two independent knobs — a snapshot that fit its own
        budget could still blow past num_ctx, and Ollama truncates silently from
        the TOP, dropping the system prompt and goal first."""
        if self.context_char_budget and self.context_char_budget > 0:
            return self.context_char_budget
        usable_tokens = max(2048, self.num_ctx - 2048)
        return int(usable_tokens * 4 * 0.6)

    @property
    def provider(self) -> str:
        return self.model.split("/", 1)[0] if "/" in self.model else self.model

    @property
    def model_name(self) -> str:
        return self.model.split("/", 1)[1] if "/" in self.model else self.model


def _parse_env_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    if "#" in value:
        value = value.split("#", 1)[0].rstrip()
    return value


def load_dotenv(project_dir: Path) -> None:
    """Load simple KEY=VALUE lines from .env without overriding real env vars."""
    for path in (Path.cwd() / ".env", project_dir / ".env"):
        if not path.exists():
            continue
        try:
            lines = path.read_text().splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key.startswith("export "):
                key = key.removeprefix("export ").strip()
            if not key or key in os.environ:
                continue
            os.environ[key] = _parse_env_value(value)


def load_config(project_dir: Path) -> Config:
    load_dotenv(project_dir)
    path = project_dir / CONFIG_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"No {CONFIG_FILENAME} found in {project_dir}. Run `9xf init` first."
        )
    raw = json.loads(path.read_text())
    known = {k: raw[k] for k in DEFAULTS if k in raw}
    extra = {k: v for k, v in raw.items() if k not in DEFAULTS}
    return Config(**known, extra=extra)


def write_config(project_dir: Path, overrides: dict | None = None,
                 preset: str | None = None) -> Path:
    data = dict(DEFAULTS)
    if preset:
        if preset not in PRESETS:
            raise ValueError(f"unknown preset {preset!r} (available: {', '.join(PRESETS)})")
        data.update(PRESETS[preset])
    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})
    if str(data.get("model", "")).startswith("nvidia/"):
        if data.get("endpoint") == DEFAULTS["endpoint"]:
            data["endpoint"] = NVIDIA_ENDPOINT
        if data.get("api_key_env") == DEFAULTS["api_key_env"]:
            data["api_key_env"] = "NVIDIA_API_KEY"
    path = project_dir / CONFIG_FILENAME
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path
