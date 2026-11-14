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
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path

import httpx

from .engine import DEFAULT_GOAL, Runner, _write_json_atomic, read_json_object

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


# A provider's model list is read at most this many pages deep.
MAX_MODEL_PAGES = 20


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
        for _ in range(MAX_MODEL_PAGES):
            body = _provider_get(client, url, key, headers=headers, params=params)
            ids += [m["id"] for m in body.get("data", [])]
            if not (body.get("has_more") and body.get("last_id")):
                break
            params = {"limit": 1000, "after_id": body["last_id"]}
        return ids
    if provider == "google":
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        headers = {"x-goog-api-key": key}
        ids, params = [], {"pageSize": 1000}
        for _ in range(MAX_MODEL_PAGES):
            body = _provider_get(client, url, key, headers=headers, params=params)
            ids += [
                m["name"].removeprefix("models/")
                for m in body.get("models", [])
                # Only models that can chat; embedding models can't play a Run.
                if "generateContent"
                in m.get("supportedGenerationMethods", ["generateContent"])
            ]
            if not body.get("nextPageToken"):
                break
            params = {"pageSize": 1000, "pageToken": body["nextPageToken"]}
        return ids
    headers = {"Authorization": f"Bearer {key}"}
    if provider == "openrouter":
        # OpenRouter lists its models to anyone, so the key is checked on its own.
        _provider_get(client, "https://openrouter.ai/api/v1/key", key, headers=headers)
    body = _provider_get(client, _MODEL_LISTS[provider], key, headers=headers)
    return [m["id"] for m in body.get("data", [])]


def scrub(text: str, key: str) -> str:
    """Text that might echo the key (provider error messages do), with the key removed.

    Providers also echo a key masked, as its first or last few characters ("sk-abc...wxyz"),
    so for a key long enough that they don't give it away, every occurrence of its first 6
    and of its last 4 characters is removed too."""
    if not key:
        return text
    text = text.replace(key, "[key]")
    if len(key) >= 12:
        text = text.replace(key[:6], "[key]").replace(key[-4:], "[key]")
    return text


def start_visitor_run(
    root: Path,
    story: Path,
    provider: str,
    model_id: str,
    key: str,
    model_factory: ModelFactory,
    *,
    stop_requested: threading.Event | None = None,
    on_end: Callable[[], None] | None = None,
) -> Path:
    """Starts a Visitor Run under the default goal and returns its folder. Its first files
    are written before this returns, so the Run is listed (as playing) straight away.

    Setting ``stop_requested`` ends the Run after the model call under way; it is kept as a partial
    Run. A Run that fails is kept as partial too. ``on_end`` is called once it ends, however
    (the dashboard then decides whether a complete Run is public)."""
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
                if stop_requested is not None and stop_requested.is_set():
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


# --- Publication ----------------------------------------------------------------------------
# A Visitor Run that completes becomes public (listed for everyone) if no complete public
# Run of the same exact provider and model id exists yet, counting the Runs baked into the
# runs root. The decision is made once, under a lock, and kept in the Run's folder in a
# file written atomically, so it survives restarts. Partial and playing Runs are never
# public and stay undecided. Decisions are settled at start-up (for complete Runs a restart
# cut off before theirs, in order of completion) and whenever a Visitor Run ends.

PUBLICATION_FILE = "publication.json"
_publication_lock = threading.Lock()


def _read_json(path: Path) -> dict:
    return read_json_object(path) or {}


def _model_of(directory: Path) -> tuple[str, str]:
    experiment = _read_json(directory / "experiment.json")
    return experiment.get("provider", ""), experiment.get("model_id", "")


def _is_complete(directory: Path) -> bool:
    return _read_json(directory / "summary.json").get("status") == "complete"


def is_public(directory: Path) -> bool:
    """Whether this Visitor Run was made public."""
    return _read_json(directory / PUBLICATION_FILE).get("public") is True


def _visitor_runs(root: Path) -> list[Path]:
    folder = root / VISITOR_FOLDER
    if not folder.is_dir():
        return []
    return [p for p in folder.iterdir() if (p / "experiment.json").is_file()]


def _baked_in_runs(root: Path) -> list[Path]:
    visitors = root / VISITOR_FOLDER
    return [
        file.parent
        for file in root.rglob("experiment.json")
        if not file.parent.is_relative_to(visitors)
    ]


def _public_models(root: Path) -> set[tuple[str, str]]:
    baked = [d for d in _baked_in_runs(root) if _is_complete(d)]
    visitors = [d for d in _visitor_runs(root) if is_public(d)]
    return {_model_of(d) for d in baked + visitors}


class Publications:
    """Which models under a runs root have a complete public Run: one baked into the runs
    root or a Visitor Run made public. :meth:`settle` works it out; the dashboard calls it
    at start-up and whenever a Visitor Run ends, and the answer is kept until the next
    call, so a visitor's request never scans the runs root."""

    def __init__(self, root: Path):
        self.root = root
        self._public: set[tuple[str, str]] = set()

    def settle(self) -> None:
        """Decides, once and for good, whether each complete Visitor Run not yet decided is
        public: the first of its model to complete is, unless a public Run of it exists."""
        with _publication_lock:
            public = _public_models(self.root)
            undecided = [
                d
                for d in _visitor_runs(self.root)
                if not (d / PUBLICATION_FILE).exists() and _is_complete(d)
            ]
            undecided.sort(
                key=lambda d: _read_json(d / "summary.json").get("completed_at") or ""
            )
            for directory in undecided:
                model = _model_of(directory)
                _write_json_atomic(
                    directory / PUBLICATION_FILE, {"public": model not in public}
                )
                public.add(model)
            self._public = public

    def public_run_exists(self, provider: str, model_id: str) -> bool:
        """Whether a complete public Run of this exact provider and model id exists."""
        with _publication_lock:
            return (provider, model_id) in self._public


# --- Stop and play limits ---------------------------------------------------------------------


class TooManyRequests(Exception):
    """This visitor asked too often within the window."""


class RateLimit:
    """At most ``limit`` requests per visitor (a client IP) in any ``window`` seconds."""

    def __init__(
        self, limit: int, window: float = 60, clock: Callable[[], float] = time.monotonic
    ):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._seen: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, visitor: str) -> None:
        """Counts a request; raises TooManyRequests when this visitor is over the limit."""
        now = self._clock()
        with self._lock:
            # Forgets visitors whose requests all fall outside the window.
            for other in [v for v, t in self._seen.items() if t[-1] <= now - self.window]:
                del self._seen[other]
            seen = self._seen.setdefault(visitor, deque())
            while seen and seen[0] <= now - self.window:
                seen.popleft()
            if len(seen) >= self.limit:
                raise TooManyRequests(
                    "Too many model listings from your address. Wait a minute and try"
                    " again, or type a model id."
                )
            seen.append(now)


class Busy(Exception):
    """The site already plays as many Visitor Runs as it allows."""


class AlreadyPlaying(Exception):
    """This visitor already has a Visitor Run playing."""


class Slot:
    """One playing Visitor Run's place in the limits, and the switch that stops it."""

    def __init__(self, visitor: str):
        self.visitor = visitor
        self.stop_requested = threading.Event()
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

    def playing_ids(self) -> set[str]:
        """The ids of the Runs whose slot is still held: their thread has not ended yet."""
        with self._lock:
            return {slot.run_id for slot in self._slots if slot.run_id is not None}

    def stop(self, run_id: str) -> bool:
        """Asks the playing Run with this id to stop; False if no such Run is playing."""
        with self._lock:
            slot = next((s for s in self._slots if s.run_id == run_id), None)
        if slot is None:
            return False
        slot.stop_requested.set()
        return True


def mark_cut_off_runs(root: Path) -> None:
    """At start-up, a Visitor Run still marked in progress was cut off (by a redeploy, say)
    and can never resume, its key being gone: it is marked partial."""
    for checkpoint in (root / VISITOR_FOLDER).glob("*/checkpoint.json"):
        if (checkpoint.parent / "summary.json").exists():
            continue
        saved = read_json_object(checkpoint)
        if saved is None:
            continue
        state = saved.get("state") or {}
        if state.get("status") != "running":
            continue
        state["status"] = "partial"
        state["stop_reason"] = CUT_OFF
        _write_json_atomic(checkpoint, saved)
