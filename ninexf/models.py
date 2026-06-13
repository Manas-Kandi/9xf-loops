"""Shared model catalog for CLI, interactive mode, and the app.

The harness still accepts any provider/model string. This file only defines
known-good local options that should be easy to discover from the UI.
"""

from __future__ import annotations

DEFAULT_MODEL = "ollama/qwen2.5-coder:7b"
GPT_OSS_20B_MODEL = "ollama/gpt-oss:20b"
NVIDIA_QWEN_MODEL = "nvidia/qwen/qwen3.5-122b-a10b"
NVIDIA_KIMI_MODEL = "nvidia/moonshotai/kimi-k2.6"

RECOMMENDED_MODELS = (
    DEFAULT_MODEL,
    GPT_OSS_20B_MODEL,
    NVIDIA_QWEN_MODEL,
    NVIDIA_KIMI_MODEL,
)


def ollama_model_id(name: str) -> str:
    return f"ollama/{name}"


def model_options(installed_ollama_models: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Installed Ollama models first, then recommended fallbacks."""
    options: list[str] = []
    seen: set[str] = set()
    for name in installed_ollama_models:
        model = ollama_model_id(name)
        if model not in seen:
            options.append(model)
            seen.add(model)
    for model in RECOMMENDED_MODELS:
        if model not in seen:
            options.append(model)
            seen.add(model)
    return options
