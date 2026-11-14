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

from .engine import DEFAULT_GOAL, Runner, _write_json_atomic

logger = logging.getLogger(__name__)

# Under the runs root. Its Runs are private: listed only for a request that names their ids.
VISITOR_FOLDER = "visitor-runs"
# The story every Visitor Run plays, in the maintainers' Runs' fidelity mode (allow-unverified).
VISITOR_STORY = Path(__file__).resolve().parents[1] / "data" / "detroit-unverified.json"
STOPPED_BY_VISITOR = "Stopped by the visitor"
CUT_OFF = "Cut off by a dashboard restart; it cannot be resumed, because its key is gone"
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
    *,
    stop: threading.Event | None = None,
    on_end: Callable[[], None] | None = None,
) -> Path:
    """Starts a Visitor Run under the default goal and returns its folder. Its first files
    are written before this returns, so the Run is listed (as playing) straight away.

    Setting ``stop`` ends the Run after the model call under way; it is kept as a partial
    Run. A Run that fails is kept as partial too. ``on_end`` is called once it ends, however."""
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
            while runner.state["status"] == "running":
                if stop is not None and stop.is_set():
                    runner.halt(STOPPED_BY_VISITOR)
                    break
                runner.step()
        except Exception as exc:  # The Run ends partial; the visitor sees why.
            reason = scrub(f"The Run failed: {type(exc).__name__}: {exc}", key)
            logger.warning("Visitor Run %s stopped: %s", directory.name, reason)
            runner.halt(reason)
        finally:
            if on_end is not None:
                on_end()

    threading.Thread(
        target=play, name=f"visitor-run-{directory.name}", daemon=True
    ).start()
    return directory


# Stop and play limits (#74, #75)


class Busy(Exception):
    """The site already plays as many Visitor Runs as it allows."""


class AlreadyPlaying(Exception):
    """This visitor already has a Visitor Run playing."""


class Slot:
    """One playing Visitor Run's place in the limits, and the switch that stops it."""

    def __init__(self, visitor: str):
        self.visitor = visitor
        self.stop = threading.Event()
        self.run_id: str | None = None


class PlayingRuns:
    """The Visitor Runs playing in this process: at most ``max_playing`` across the site and
    ``max_per_visitor`` per visitor (a client IP). A slot frees when its Run ends, however."""

    def __init__(self, max_playing: int = 2, max_per_visitor: int = 1):
        self.max_playing = max_playing
        self.max_per_visitor = max_per_visitor
        self._slots: list[Slot] = []
        self._lock = threading.Lock()

    def reserve(self, visitor: str) -> Slot:
        """A slot for a Run about to start; raises AlreadyPlaying or Busy when there is none."""
        with self._lock:
            mine = sum(slot.visitor == visitor for slot in self._slots)
            if mine >= self.max_per_visitor:
                raise AlreadyPlaying(
                    "You already have a Run playing. Stop it or let it finish before"
                    " starting another."
                )
            if len(self._slots) >= self.max_playing:
                raise Busy(
                    "The site is busy: it is already playing as many Visitor Runs as it"
                    " allows. Try again later."
                )
            slot = Slot(visitor)
            self._slots.append(slot)
            return slot

    def release(self, slot: Slot) -> None:
        with self._lock:
            if slot in self._slots:
                self._slots.remove(slot)

    def stop(self, run_id: str) -> bool:
        """Asks the playing Run with this id to stop; False if no such Run is playing."""
        with self._lock:
            slot = next((s for s in self._slots if s.run_id == run_id), None)
        if slot is None:
            return False
        slot.stop.set()
        return True


def mark_cut_off_runs(root: Path) -> None:
    """At start-up, a Visitor Run still marked in progress was cut off (by a redeploy, say)
    and can never resume, its key being gone: it is marked partial."""
    for checkpoint in (root / VISITOR_FOLDER).glob("*/checkpoint.json"):
        if (checkpoint.parent / "summary.json").exists():
            continue
        try:
            saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        state = saved.get("state") or {}
        if state.get("status") != "running":
            continue
        state["status"] = "partial"
        state["stop_reason"] = CUT_OFF
        _write_json_atomic(checkpoint, saved)
