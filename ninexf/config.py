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
    "decompose_enabled": True,
    "max_task_failures": 3,
    "max_verify_attempts": 3,
    "revert_after_failures": 3,
    "context_strategy": "relevance",  # relevance | brute (v0.2 control)
    "diff_char_budget": 3000,
    "notes_enabled": True,
    "notes_max_lines": 40,
    "max_notes_per_iteration": 2,
    "acceptance_tests": False,
    "critic_enabled": False,
    "critic_max_revisions": 1,
    "best_of_n": 1,
    "best_of_mode": "fix",  # fix | always | off
    "explore_enabled": False,
    "explore_after_stuck": 3,
    "max_explores_per_run": 2,
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
    decompose_enabled: bool = DEFAULTS["decompose_enabled"]
    max_task_failures: int = DEFAULTS["max_task_failures"]
    max_verify_attempts: int = DEFAULTS["max_verify_attempts"]
    revert_after_failures: int = DEFAULTS["revert_after_failures"]
    context_strategy: str = DEFAULTS["context_strategy"]
    diff_char_budget: int = DEFAULTS["diff_char_budget"]
    notes_enabled: bool = DEFAULTS["notes_enabled"]
    notes_max_lines: int = DEFAULTS["notes_max_lines"]
    max_notes_per_iteration: int = DEFAULTS["max_notes_per_iteration"]
    acceptance_tests: bool = DEFAULTS["acceptance_tests"]
    critic_enabled: bool = DEFAULTS["critic_enabled"]
    critic_max_revisions: int = DEFAULTS["critic_max_revisions"]
    best_of_n: int = DEFAULTS["best_of_n"]
    best_of_mode: str = DEFAULTS["best_of_mode"]
    explore_enabled: bool = DEFAULTS["explore_enabled"]
    explore_after_stuck: int = DEFAULTS["explore_after_stuck"]
    max_explores_per_run: int = DEFAULTS["max_explores_per_run"]
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
