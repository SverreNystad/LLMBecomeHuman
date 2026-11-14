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


class ProviderAuthError(Exception):
    """The provider rejected the key. The message never contains the key."""


class ProviderUnreachable(Exception):
    """The provider could not be reached, or failed to answer. The message never
    contains the key."""


def list_models(
    provider: str, key: str, client: httpx.Client | None = None
) -> list[str]:
    """The model ids the provider's list-models endpoint returns for this key, sorted.

    Raises :class:`ProviderAuthError` when the provider rejects the key and
    :class:`ProviderUnreachable` when it can't be reached or fails; neither message
    contains the key. ``client`` is for tests (an httpx MockTransport).
    """
    owned = client is None
    client = client or httpx.Client(timeout=20)
    try:
        return sorted(_listed_ids(client, provider, key))
    except httpx.HTTPError as exc:
        reason = scrub(f"{type(exc).__name__}: {exc}", key)
        raise ProviderUnreachable(reason) from None
    finally:
        if owned:
            client.close()


def _provider_get(client: httpx.Client, url: str, key: str, **options) -> dict:
    response = client.get(url, **options)
    if response.status_code in (401, 403) or _google_rejected_key(response):
        raise ProviderAuthError(
            f"The provider rejected the key ({response.status_code})"
        )
    if response.status_code >= 400:
        raise ProviderUnreachable(f"The provider answered {response.status_code}")
    return response.json()


def _google_rejected_key(response: httpx.Response) -> bool:
    """Google answers a bad key with 400 and the reason API_KEY_INVALID."""
    return response.status_code == 400 and (
        "API_KEY_INVALID" in response.text or "API key not valid" in response.text
    )


def _listed_ids(client: httpx.Client, provider: str, key: str) -> list[str]:
    """Every page of the provider's model list."""
    if provider == "anthropic":
        url = "https://api.anthropic.com/v1/models"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        ids, params = [], {"limit": 1000}
        while True:
            body = _provider_get(client, url, key, headers=headers, params=params)
            ids += [m["id"] for m in body.get("data", [])]
            if not (body.get("has_more") and body.get("last_id")):
                return ids
            params = {"limit": 1000, "after_id": body["last_id"]}
    if provider == "google":
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        headers = {"x-goog-api-key": key}
        ids, params = [], {"pageSize": 1000}
        while True:
            body = _provider_get(client, url, key, headers=headers, params=params)
            ids += [
                m["name"].removeprefix("models/")
                for m in body.get("models", [])
                # Only models that can chat; embedding models can't play a Run.
                if "generateContent"
                in m.get("supportedGenerationMethods", ["generateContent"])
            ]
            if not body.get("nextPageToken"):
                return ids
            params = {"pageSize": 1000, "pageToken": body["nextPageToken"]}
    headers = {"Authorization": f"Bearer {key}"}
    if provider == "openrouter":
        # OpenRouter lists its models to anyone, so the key is checked on its own.
        _provider_get(client, "https://openrouter.ai/api/v1/key", key, headers=headers)
    body = _provider_get(client, _MODEL_LISTS[provider], key, headers=headers)
    return [m["id"] for m in body.get("data", [])]


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
