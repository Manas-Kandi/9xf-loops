"""Local app settings and secrets for the Loopy desktop/web app.

This is intentionally separate from per-run `9xf.config.json`. It stores
user-level defaults (onboarding state, preferred model, recent folder, etc.)
and local-only secrets used by the app when starting runs.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from ninexf.models import DEFAULT_MODEL, MISTRAL_SMALL_MODEL

APP_DIR_ENV = "NINEXF_APP_DIR"
SECRET_ENV_NAME = "LOOPY_API_KEY"
SETTINGS_FILENAME = "settings.json"
SECRETS_FILENAME = "secrets.json"


def _default_app_dir() -> Path:
    override = os.environ.get(APP_DIR_ENV)
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Loopy"
    return Path.home() / ".loopy"


def app_dir() -> Path:
    return _default_app_dir()


def settings_path() -> Path:
    return app_dir() / SETTINGS_FILENAME


def secrets_path() -> Path:
    return app_dir() / SECRETS_FILENAME


@dataclass
class AppSettings:
    onboarding_complete: bool = False
    preferred_mode: str = "ollama"  # ollama | api
    preferred_model: str = DEFAULT_MODEL
    ollama_endpoint: str = "http://localhost:11434"
    api_model: str = MISTRAL_SMALL_MODEL
    api_key_env: str = SECRET_ENV_NAME
    last_dir: str = ""
    mascot_enabled: bool = True


def _ensure_dir() -> Path:
    root = app_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root


def load_app_settings() -> AppSettings:
    path = settings_path()
    if not path.exists():
        return AppSettings()
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return AppSettings()
    known = {k: raw[k] for k in AppSettings.__dataclass_fields__ if k in raw}
    return AppSettings(**known)


def save_app_settings(settings: AppSettings) -> Path:
    _ensure_dir()
    path = settings_path()
    path.write_text(json.dumps(asdict(settings), indent=2) + "\n")
    return path


def patch_app_settings(**updates) -> AppSettings:
    current = load_app_settings()
    for key, value in updates.items():
        if value is None or not hasattr(current, key):
            continue
        setattr(current, key, value)
    save_app_settings(current)
    return current


def load_secrets() -> dict:
    path = secrets_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_secret(name: str, value: str) -> None:
    _ensure_dir()
    secrets = load_secrets()
    if value:
        secrets[name] = value
    else:
        secrets.pop(name, None)
    secrets_path().write_text(json.dumps(secrets, indent=2) + "\n")


def get_secret(name: str) -> str:
    return str(load_secrets().get(name, ""))


def settings_payload() -> dict:
    settings = load_app_settings()
    api_key = get_secret(settings.api_key_env)
    return {
        **asdict(settings),
        "api_key_present": bool(api_key),
        "settings_path": str(settings_path()),
    }
