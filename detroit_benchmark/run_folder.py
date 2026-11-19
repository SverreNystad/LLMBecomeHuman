"""A Run's folder: the one module that knows the files a Run is saved in.

A Run is saved as its settings (experiment.json), a snapshot of its story graph
(story-graph.json), its events, one JSON line each (events.jsonl), its resume checkpoint
(checkpoint.json, rewritten after every event) and, once it has ended, its summary
(summary.json). The Runner writes them through :class:`RunFolder`; the dashboard, the
Visitor Runs and the CLI read them through it, so the file names, which file wins when
two say the same thing, and the migration of old checkpoints live only here.

A Visitor Run's key is never given to this module, so it never reaches disk (ADR 0003).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

SETTINGS = "experiment.json"
STORY_GRAPH = "story-graph.json"
EVENTS = "events.jsonl"
CHECKPOINT = "checkpoint.json"
SUMMARY = "summary.json"


def canonical_hash(obj) -> str:
    """A stable hash of a JSON value, e.g. the story graph a Run played."""
    data = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()


def file_stamp(path: Path) -> tuple[int, int] | None:
    """A file's version, for caches: (modified time, size), or None if it is missing."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def read_json_object(path: Path) -> dict | None:
    """The JSON object in this file, or None when it is missing, unreadable or not an object."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def write_json_atomic(path: Path, obj, indent: int | None = None) -> None:
    """Write JSON so a crash never leaves a half-written file."""
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8"
    )
    os.replace(temp, path)


def _parse_event(line: bytes) -> dict | None:
    try:
        parsed = json.loads(line)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def find_runs(root: Path) -> list[RunFolder]:
    """Every Run saved under ``root`` (a folder with its settings), in path order."""
    if not root.is_dir():
        return []
    folders = {
        file.parent.resolve()
        for file in root.rglob(SETTINGS)
        if file.parent.resolve().is_relative_to(root)
    }
    return [
        RunFolder(path) for path in sorted(folders, key=lambda p: p.as_posix().lower())
    ]


class RunFolder:
    """One Run's folder, for the Runner playing it and for everyone reading it."""

    def __init__(self, path: Path):
        self.path = Path(path)
        # (graph hash, provider, model id): set once the Run is begun or resumed here.
        self._key: dict | None = None

    def _file(self, name: str) -> Path:
        return self.path / name

    # --- Playing: the Runner ---------------------------------------------------------------

    def begin(self, graph: dict, key: dict, settings: dict, state: dict) -> None:
        """Start a new Run here: its story snapshot, settings and first checkpoint.
        ``key`` is what a resume must match: graph_sha256, provider and model_id."""
        self.path.mkdir(parents=True, exist_ok=True)
        if self._file(EVENTS).exists() or self._file(CHECKPOINT).exists():
            raise FileExistsError(
                "Run directory already contains a run. Choose a new folder or --resume."
            )
        self._key = dict(key)
        self._save_story_graph(graph)
        self._file(SETTINGS).write_text(
            json.dumps(settings, indent=2), encoding="utf-8"
        )
        self.save(state)

    def resume(self, graph: dict, key: dict, blank_state: dict) -> dict:
        """The saved state of the Run here, to play on from. It must have been played
        with the same ``key``; a checkpoint from before a part of the state existed gets
        that part from ``blank_state``, a new Run's. Events written after the last
        checkpoint (a crash in between) are dropped."""
        checkpoint = self._file(CHECKPOINT)
        if not checkpoint.exists():
            raise ValueError(f"No checkpoint at {checkpoint}")
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        if any(saved[name] != value for name, value in key.items()):
            raise ValueError("Cannot resume with different graph, provider, or model")
        self._key = dict(key)
        state = {**blank_state, **saved["state"]}
        self._save_story_graph(graph)
        if state.get("status") == "complete":
            raise ValueError("Run is already complete")
        events, kept = self._file(EVENTS), state["event_idx"]
        if events.exists():
            lines = events.read_text(encoding="utf-8").splitlines()
            events.write_text(
                "\n".join(lines[:kept]) + "\n" if kept else "", encoding="utf-8"
            )
        return state

    def _save_story_graph(self, graph: dict) -> None:
        """Keep the story graph beside the Run, so its untaken branches stay visible."""
        path = self._file(STORY_GRAPH)
        if path.exists():
            if (
                canonical_hash(json.loads(path.read_text(encoding="utf-8")))
                != self._key["graph_sha256"]
            ):
                raise ValueError(
                    "Existing story-graph.json does not match the run graph"
                )
            return
        write_json_atomic(path, graph, indent=2)

    def save(self, state: dict) -> None:
        """Checkpoint the playing Run's state (after every event, so kept compact)."""
        write_json_atomic(self._file(CHECKPOINT), {**self._key, "state": state})

    def append(self, event: dict) -> None:
        """Add an event to the Run's log, on disk before this returns."""
        with self._file(EVENTS).open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    def finish(self, summary: dict) -> None:
        """Save the summary of a Run that reached its ending."""
        self._file(SUMMARY).write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def stop(self, reason: str, state: dict | None = None) -> None:
        """Keep a playing Run as partial, recording why. ``state`` is the state of the
        Run being played; without it, the saved Run (one no process plays any more,
        cut off by a restart, say) is marked, if it was still playing."""
        if state is None:
            if self._file(SUMMARY).exists():
                return
            saved = read_json_object(self._file(CHECKPOINT)) or {}
            state = saved.get("state") or {}
        if state.get("status") != "running":
            return
        state.update(status="partial", stop_reason=reason)
        if self._key is not None:
            self.save(state)
        else:
            write_json_atomic(self._file(CHECKPOINT), saved)

    def model(self) -> tuple[str, str]:
        """The provider and model id the Run was begun with, from its settings."""
        settings = read_json_object(self._file(SETTINGS)) or {}
        return settings.get("provider", ""), settings.get("model_id", "")

    # --- Reading: the dashboard, the Visitor Runs and the CLI -------------------------------

    def is_run(self) -> bool:
        """Whether a Run was begun here."""
        return self._file(SETTINGS).is_file()

    def has_events(self) -> bool:
        return self._file(EVENTS).is_file()

    def metadata(self) -> dict[str, Any]:
        """What the Run is and how far it got: its settings, then its summary once it
        has ended, else its latest checkpoint. Re-read only when the files change."""
        summary = self._file(SUMMARY)
        return dict(
            _metadata(
                str(self.path),
                file_stamp(self._file(SETTINGS)),
                file_stamp(summary),
                # A finished Run's summary has everything; the checkpoint only fills in live ones.
                None if summary.exists() else file_stamp(self._file(CHECKPOINT)),
            )
        )

    def summary(self) -> dict | None:
        """The summary of a Run that reached its ending; None before it has."""
        return read_json_object(self._file(SUMMARY))

    def is_complete(self) -> bool:
        """Whether the Run reached its ending and its summary is saved."""
        return (self.summary() or {}).get("status") == "complete"

    def news(self) -> list[str]:
        """The Run's Public News so far, in the order it happened."""
        news = _saved_state(self.path).get("news") or []
        return [str(item) for item in news if isinstance(item, str)]

    def story_graph(self) -> dict | None:
        """The story graph saved beside the Run, if it is the one the Run played."""
        snapshot = read_json_object(self._file(STORY_GRAPH))
        expected = self.graph_sha256()
        if snapshot is not None and (
            not expected or canonical_hash(snapshot) == expected
        ):
            return snapshot
        return None

    def has_story_graph(self) -> bool:
        return self._file(STORY_GRAPH).exists()

    def graph_sha256(self) -> str | None:
        """The hash of the story graph the Run played, from its settings."""
        return (read_json_object(self._file(SETTINGS)) or {}).get("graph_sha256")

    def events_at(self):
        """The Run's events in order, each with the byte offset of its line, read line by
        line. A half-written last line (the Run is still playing) and anything that is
        not an event object are skipped."""
        try:
            with self._file(EVENTS).open("rb") as stream:
                offset = 0
                for line in stream:
                    start, offset = offset, offset + len(line)
                    if line.strip() and (event := _parse_event(line)) is not None:
                        yield start, event
        except OSError:
            return

    def events(self):
        """The Run's events in order; see :meth:`events_at`."""
        return (event for _, event in self.events_at())

    def event_at(self, offset: int) -> dict | None:
        """The event whose line starts at this byte offset (from :meth:`events_at`)."""
        try:
            with self._file(EVENTS).open("rb") as stream:
                stream.seek(offset)
                return _parse_event(stream.readline())
        except OSError:
            return None

    def events_version(self) -> tuple[int, int] | None:
        """The version of the Run's event log, for caches; None before it has one."""
        return file_stamp(self._file(EVENTS))

    def seconds_since_write(self) -> float:
        """How long ago the Run last recorded an event."""
        try:
            return time.time() - self._file(EVENTS).stat().st_mtime
        except OSError:
            return float("inf")


@lru_cache(maxsize=8)
def _cached_state(path: str, _stamp) -> dict[str, Any]:
    return (read_json_object(Path(path)) or {}).get("state") or {}


def _saved_state(directory: Path) -> dict[str, Any]:
    """A Run's checkpointed state, parsed once per version of its checkpoint. Read-only."""
    path = directory / CHECKPOINT
    return _cached_state(str(path), file_stamp(path))


@lru_cache(maxsize=256)
def _metadata(directory_s: str, *_stamps) -> dict[str, Any]:
    directory = Path(directory_s)
    exp = read_json_object(directory / SETTINGS) or {}
    summary = read_json_object(directory / SUMMARY) or {}
    state = {} if summary else _saved_state(directory)
    status = summary.get("status") or state.get("status") or "unknown"
    chapters = summary.get("chapters_visited", state.get("chapters_visited", []))
    decisions = summary.get("number_of_choices", len(state.get("decisions", [])))
    return {
        "provider": exp.get("provider", summary.get("provider", "unknown")),
        "display_provider": exp.get("display_provider")
        if exp.get("synthetic", False)
        else None,
        "model": exp.get("model_id", summary.get("model", "unknown")),
        "goal": exp.get("goal", summary.get("goal", "")),
        "story_title": exp.get("story_title"),
        "synthetic": exp.get("synthetic", False),
        "fidelity": exp.get("fidelity", summary.get("fidelity", "unknown")),
        "unverified": exp.get("allow_unverified", summary.get("unverified", False)),
        "status": status,
        "choices": decisions,
        "chapters": len(chapters),
        "chapters_visited": chapters,
        "started_at": exp.get("started_at", summary.get("started_at")),
        "completed_at": summary.get("completed_at"),
        "total_input_tokens": summary.get(
            "total_input_tokens", state.get("total_input_tokens", 0)
        ),
        "total_output_tokens": summary.get(
            "total_output_tokens", state.get("total_output_tokens", 0)
        ),
        "total_llm_latency_seconds": summary.get(
            "total_llm_latency_seconds", state.get("total_llm_latency_seconds", 0)
        ),
        "warnings": len(summary.get("warnings", state.get("warnings", []))),
        "end_description": summary.get("end_description"),
        "final_flags": summary.get("final_flags", state.get("flags", {})),
        "graph_sha256": exp.get("graph_sha256", summary.get("graph_sha256")),
        "stop_reason": state.get("stop_reason"),
    }
