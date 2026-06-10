"""Shared helpers for the harness test suite: run a real loop end-to-end in a
temp dir with a mock scenario backend, then assert on loop_log.jsonl + git."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from ninexf.cli import main as cli_main
from ninexf.config import load_config
from ninexf.loop import LoopRunner
from ninexf.looplog import read_entries


def make_run(goal: str, model: str, config_overrides: dict | None = None) -> Path:
    d = Path(tempfile.mkdtemp(prefix="9xf-test-")).resolve()
    cli_main(["init", "--goal", goal, "--model", model, "--dir", str(d), "--delay", "0"])
    if config_overrides:
        cfg_path = d / "9xf.config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg.update(config_overrides)
        cfg_path.write_text(json.dumps(cfg, indent=2) + "\n")
    return d


def run_loop(project: Path, max_iterations: int) -> list[dict]:
    LoopRunner(project, load_config(project)).run(max_iterations=max_iterations, delay=0)
    return read_entries(project)


def iteration_entries(entries: list[dict]) -> list[dict]:
    return [e for e in entries if e.get("event") == "iteration"]


def events(entries: list[dict], kind: str) -> list[dict]:
    return [e for e in entries if e.get("event") == kind]


def git(project: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=project, capture_output=True,
                          text=True, check=True).stdout


def cleanup(project: Path) -> None:
    shutil.rmtree(project, ignore_errors=True)
