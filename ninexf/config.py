"""Load and validate the per-project 9xf.config.json.

The config is written once by `9xf init` and never modified by the agent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ninexf import CONFIG_FILENAME

DEFAULTS = {
    "model": "ollama/qwen2.5-coder:7b",
    "endpoint": "http://localhost:11434",
    "max_iterations": 50,
    "delay_seconds": 5,
    "validation_timeout": 10,
    "allow_network": False,
    "context_char_budget": 24000,
    "history_entries_in_context": 15,
    "api_key_env": "ANTHROPIC_API_KEY",
    "review_every": 5,
    "stuck_similarity": 0.85,
    "max_tool_runs_per_iteration": 3,
    "tools_enabled": True,
    "run_tests": True,
}


@dataclass
class Config:
    model: str = DEFAULTS["model"]
    endpoint: str = DEFAULTS["endpoint"]
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
    extra: dict = field(default_factory=dict)

    @property
    def provider(self) -> str:
        return self.model.split("/", 1)[0] if "/" in self.model else self.model

    @property
    def model_name(self) -> str:
        return self.model.split("/", 1)[1] if "/" in self.model else self.model


def load_config(project_dir: Path) -> Config:
    path = project_dir / CONFIG_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"No {CONFIG_FILENAME} found in {project_dir}. Run `9xf init` first."
        )
    raw = json.loads(path.read_text())
    known = {k: raw[k] for k in DEFAULTS if k in raw}
    extra = {k: v for k, v in raw.items() if k not in DEFAULTS}
    return Config(**known, extra=extra)


def write_config(project_dir: Path, overrides: dict | None = None) -> Path:
    data = dict(DEFAULTS)
    if overrides:
        data.update({k: v for k, v in overrides.items() if v is not None})
    path = project_dir / CONFIG_FILENAME
    path.write_text(json.dumps(data, indent=2) + "\n")
    return path
