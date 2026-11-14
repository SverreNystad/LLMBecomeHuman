"""Visitor Runs: a Run a visitor starts from the dashboard with their own API key.

Each one plays in a background thread inside the dashboard process and is saved in its own
folder under the runs root's Visitor Run folder, named with a random, unguessable token.
The key lives only in memory for the life of the Run: it is never written to the run
folder or any log, and error messages are scrubbed of it before they are logged or saved.
See ADR 0003.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from collections.abc import Callable
from pathlib import Path

import httpx

from .engine import DEFAULT_GOAL, Runner

logger = logging.getLogger(__name__)

# Under the runs root. Its Runs are private: listed only for a request that names their ids.
VISITOR_FOLDER = "visitor-runs"
# The story every Visitor Run plays, in the maintainers' Runs' fidelity mode (allow-unverified).
VISITOR_STORY = Path(__file__).resolve().parents[1] / "data" / "detroit-unverified.json"
PROVIDERS = (
    "openai",
    "anthropic",
    "google",
    "xai",
    "deepseek",
    "mistral",
    "openrouter",
)

# (provider, key) -> model ids
ModelLister = Callable[[str, str], list[str]]
# The shape of engine.create_model: (provider, model id, temperature, max_tokens=, api_key=).
ModelFactory = Callable[..., object]

_MODEL_LISTS = {
    "openai": "https://api.openai.com/v1/models",
    "xai": "https://api.x.ai/v1/models",
    "deepseek": "https://api.deepseek.com/models",
    "mistral": "https://api.mistral.ai/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
}


def list_models(provider: str, key: str) -> list[str]:
    """The model ids the provider's list-models endpoint returns for this key."""
    if provider == "anthropic":
        url, headers, params = (
            "https://api.anthropic.com/v1/models",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {"limit": 1000},
        )
    elif provider == "google":
        url, headers, params = (
            "https://generativelanguage.googleapis.com/v1beta/models",
            {"x-goog-api-key": key},
            {"pageSize": 1000},
        )
    else:
        url, headers, params = (
            _MODEL_LISTS[provider],
            {"Authorization": f"Bearer {key}"},
            {},
        )
    response = httpx.get(url, headers=headers, params=params, timeout=20)
    response.raise_for_status()
    body = response.json()
    if provider == "google":
        return sorted(m["name"].removeprefix("models/") for m in body.get("models", []))
    return sorted(m["id"] for m in body.get("data", []))


def scrub(text: str, key: str) -> str:
    """Text that might echo the key (provider error messages do), with the key removed."""
    return text.replace(key, "[key]") if key else text


def start_visitor_run(
    root: Path,
    story: Path,
    provider: str,
    model_id: str,
    key: str,
    model_factory: ModelFactory,
) -> Path:
    """Starts a Visitor Run under the default goal and returns its folder. Its first files
    are written before this returns, so the Run is listed (as playing) straight away."""
    graph = json.loads(story.read_text(encoding="utf-8"))
    directory = root / VISITOR_FOLDER / secrets.token_urlsafe(18)
    runner = Runner(
        graph=graph,
        provider=provider,
        model_id=model_id,
        run_dir=directory,
        goal=DEFAULT_GOAL,
        allow_unverified=True,
        model_factory=model_factory,
        api_key=key,
    )

    def play():
        try:
            runner.run()
        except Exception as exc:  # The Run stops; the visitor sees it as stopped.
            reason = scrub(f"{type(exc).__name__}: {exc}", key)
            logger.warning("Visitor Run %s stopped: %s", directory.name, reason)
            runner.halt(reason)

    threading.Thread(
        target=play, name=f"visitor-run-{directory.name}", daemon=True
    ).start()
    return directory
