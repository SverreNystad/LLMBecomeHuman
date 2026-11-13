"""Read-only dashboard for saved LLM benchmark experiments.

The dashboard is intentionally limited to local, previously recorded run directories.
It does not invoke LLMs or alter the benchmark's state.
"""

from __future__ import annotations

import base64
import csv
import io
import json
import time
from collections import Counter
from functools import lru_cache

from .engine import canonical_hash, chapter_briefing, iter_events, limit_sentences
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

ASSETS = Path(__file__).parent / "dashboard_assets"
ART_RECHECK_SECONDS = 30
# Game art is copyrighted, so it stays local (gitignored) and every view works without it.
IMAGES = Path(__file__).resolve().parents[1] / "images"
# The scene-art manifest is committed; the images it names live under the images folder.
SCENE_ART_MANIFEST = Path(__file__).resolve().parents[1] / "data" / "scene-art.json"

# A run with no final summary and no new events for this long is no longer active.
STALE_RUN_SECONDS = 15 * 60

# Display names from the transcript's own chapter menu. They live here rather than in
# the story graph because adding them there would change the hash that run comparison uses.
DETROIT_SOURCE = "detroitbecometext"
DETROIT_CHAPTER_TITLES = {
    "1": "The Hostage",
    "2": "Opening",
    "3": "Shades of Color",
    "4": "A New Home",
    "5": "The Painter",
    "6": "Partners",
    "7": "Stormy Night",
    "8": "Broken",
    "9": "The Interrogation",
    "10": "Fugitives",
    "11": "From the Dead",
    "12": "Waiting for Hank...",
    "13": "On the Run",
    "14": "Jericho",
    "15": "The Nest",
    "16": "Time to Decide",
    "17": "Zlatko",
    "18": "Russian Roulette",
    "19": "Spare Parts",
    "20": "The Eden Club",
    "21": "The Pirates' Cove",
    "22": "The Bridge",
    "23": "The Stratford Tower",
    "24": "Public Enemy",
    "25": "Midnight Train",
    "26": "Capitol Park",
    "27": "Meet Kamski",
    "28": "Freedom March",
    "29": "Last Chance, Connor",
    "30.1": "Crossroads: Kara",
    "30.2": "Crossroads: Connor",
    "30.3": "Crossroads: Markus",
    "31.1": "Night of the Soul: Markus",
    "31.2": "Night of the Soul: Connor",
    "32.1": "Battle for Detroit: Kara Leaving Detroit",
    "32.2": "Battle for Detroit: Kara Captured",
    "32.3": "Battle for Detroit: Connor's Last Mission",
    "32.4": "Battle for Detroit: Connor at the CyberLife Tower",
    "32.5": "Battle for Detroit: Markus Demonstration",
    "32.6": "Battle for Detroit: Markus Revolution",
    "final": "Final Routes",
}


def _json_file(path: Path) -> dict[str, Any] | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _run_id(root: Path, directory: Path) -> str:
    rel = directory.relative_to(root).as_posix()
    return base64.urlsafe_b64encode(rel.encode("utf-8")).decode("ascii").rstrip("=")


def _resolve_run(root: Path, run_id: str) -> Path:
    try:
        encoded = run_id + "=" * (-len(run_id) % 4)
        rel = base64.b64decode(encoded, altchars=b"-_", validate=True).decode("utf-8")
        path = (root / rel).resolve()
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=404, detail="Unknown run") from exc
    if (
        path == root
        or not path.is_relative_to(root)
        or not (path / "experiment.json").is_file()
    ):
        raise HTTPException(status_code=404, detail="Unknown run")
    return path


def _discovered_runs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    paths: list[Path] = []
    for file in root.rglob("experiment.json"):
        resolved = file.parent.resolve()
        if resolved.is_relative_to(root) and (resolved / "events.jsonl").is_file():
            paths.append(resolved)
    return sorted(set(paths), key=lambda p: p.as_posix().lower())


def _seconds_since_write(directory: Path) -> float:
    try:
        return time.time() - (directory / "events.jsonl").stat().st_mtime
    except OSError:
        return float("inf")


def _stamp(path: Path) -> tuple[int, int] | None:
    """A file's version, for caches: (modified time, size), or None if it is missing."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _metadata(root: Path, directory: Path) -> dict[str, Any]:
    """The Run list is polled every few seconds; its files are re-read only when they change."""
    summary = directory / "summary.json"
    meta = dict(
        _cached_metadata(
            str(root),
            str(directory),
            _stamp(directory / "experiment.json"),
            _stamp(summary),
            # A finished Run's summary has everything; the checkpoint only fills in live ones.
            None if summary.exists() else _stamp(directory / "checkpoint.json"),
        )
    )
    if (
        meta["status"] == "running"
        and _seconds_since_write(directory) > STALE_RUN_SECONDS
    ):
        meta["status"] = "stopped"
    return meta


@lru_cache(maxsize=256)
def _cached_metadata(root_s: str, directory_s: str, *_stamps) -> dict[str, Any]:
    root, directory = Path(root_s), Path(directory_s)
    exp = _json_file(directory / "experiment.json") or {}
    summary = _json_file(directory / "summary.json") or {}
    checkpoint = {} if summary else _json_file(directory / "checkpoint.json") or {}
    state = checkpoint.get("state", {})
    status = summary.get("status") or state.get("status") or "unknown"
    chapters = summary.get("chapters_visited", state.get("chapters_visited", []))
    decisions = summary.get("number_of_choices", len(state.get("decisions", [])))
    return {
        "id": _run_id(root, directory),
        "name": directory.relative_to(root).as_posix(),
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
    }


def _short_event(event: dict[str, Any]) -> dict[str, Any]:
    kind = event.get("type")
    result = {
        k: event.get(k) for k in ("index", "timestamp", "type", "chapter", "node_id")
    }
    if kind == "scene":
        scene = event.get("visible_to_agent") or {}
        result.update(
            heading=scene.get("heading"),
            description=scene.get("description"),
            character=scene.get("character"),
            observations=scene.get("observations", []),
            dialogue_count=len(scene.get("dialogue", [])),
        )
    elif kind == "decision":
        context = event.get("input") or {}
        scene = context.get("current_scene") or {}
        result.update(
            heading=scene.get("heading"),
            description=scene.get("description"),
            character=scene.get("character"),
            available_choices=context.get("available_choices", []),
            label=event.get("label"),
            choice_key=event.get("decision_key"),
            choice_id=(event.get("output") or {}).get("choice_id"),
            rationale=(event.get("output") or {}).get("rationale"),
            relevant_prior_choices=(event.get("output") or {}).get(
                "relevant_prior_choices", []
            ),
            flags_before=event.get("flags_before", {}),
            flags_after=event.get("flags_after", {}),
            prompt_history_count=len(context.get("entire_decision_history", [])),
            retrieved_scenes_count=len(context.get("relevant_earlier_scenes", [])),
            model_info=event.get("model_info", {}),
            unverified_requirements=event.get("unverified_requirements", []),
        )
    elif kind == "ending":
        result["description"] = event.get("description")
    elif kind in ("condition", "route"):
        result.update(
            {
                k: event.get(k)
                for k in (
                    "branch_index",
                    "used_unverified_default",
                    "flag",
                    "value",
                    "assumed",
                    "next",
                )
                if k in event
            }
        )
    return result


def _moment_id(node_id: Any) -> str | None:
    """A Moment is one story graph node: the Story and the Flowchart both address it by this id."""
    return str(node_id) if node_id is not None else None


def _story_beat(event: dict[str, Any]) -> dict[str, Any] | None:
    """What a reader needs from one event, including the dialogue _short_event leaves out."""
    kind = event.get("type")
    beat = {k: event.get(k) for k in ("index", "type", "node_id")}
    beat["moment"] = _moment_id(event.get("node_id"))
    if kind == "scene":
        scene = event.get("visible_to_agent") or {}
        beat.update(
            heading=scene.get("heading"),
            description=scene.get("description"),
            observations=scene.get("observations", []),
            dialogue=[
                {"speaker": line.get("speaker"), "text": line.get("text")}
                for line in scene.get("dialogue", [])
            ],
        )
    elif kind == "decision":
        scene = (event.get("input") or {}).get("current_scene") or {}
        beat.update(
            heading=scene.get("heading"),
            character=scene.get("character"),
            available_choices=(event.get("input") or {}).get("available_choices", []),
            choice_id=(event.get("output") or {}).get("choice_id"),
            rationale=(event.get("output") or {}).get("rationale"),
        )
    elif kind == "condition":
        beat.update(
            branch_index=event.get("branch_index"),
            used_unverified_default=event.get("used_unverified_default", False),
        )
    elif kind == "route":
        beat.update(
            flag=event.get("flag"),
            value=event.get("value"),
            assumed=event.get("assumed", False),
        )
    elif kind == "ending":
        beat.update(description=event.get("description"))
    elif kind == "memory_update":
        # A Memory Update closes a Chapter Segment; _parse_events adds the previous memory.
        beat.update(
            type="memory",
            character=event.get("character"),
            memory=event.get("memory") or "",
            length=event.get("length"),
            max_chars=event.get("max_chars"),
            truncated=bool(event.get("truncated", False)),
        )
    else:
        return None
    return beat


def _capped_justification(event: dict[str, Any]) -> dict[str, Any]:
    """Runs recorded before the engine capped justifications are shown capped too."""
    output = event.get("output")
    if event.get("type") != "decision" or not isinstance(output, dict):
        return event
    rationale = output.get("rationale")
    if not isinstance(rationale, str):
        return event
    return {**event, "output": {**output, "rationale": limit_sentences(rationale)}}


def _parse_events(directory: str) -> tuple[list, dict]:
    """Decision events repeat the whole prompt, so logs reach tens of MB; parse each version once."""
    short: list[dict[str, Any]] = []
    story: dict[str, list[dict[str, Any]]] = {}
    visits: Counter = Counter()
    memories: dict[str, str] = {}
    for event in map(_capped_justification, iter_events(Path(directory))):
        short.append(_short_event(event))
        beat = _story_beat(event)
        if beat is not None:
            if beat["type"] == "memory":
                # Each Character's memory is compared only with its own last one.
                beat["previous"] = memories.get(beat["character"], "")
                memories[beat["character"]] = beat["memory"]
            # A node can recur, so each pass through a Moment is numbered from the run's start.
            visits[beat["moment"]] += 1
            beat["visit"] = visits[beat["moment"]]
            story.setdefault(str(event.get("chapter") or "Unknown"), []).append(beat)
    return short, story


# Run directory -> (log version, parsed log). Only the latest version of a live Run is kept.
_PARSED_LOGS: dict[str, tuple[tuple[int, int], tuple[list, dict]]] = {}


def _parsed_events(directory: Path) -> tuple[list, dict]:
    stamp = _stamp(directory / "events.jsonl")
    if stamp is None:
        return [], {}
    cached = _PARSED_LOGS.get(str(directory))
    if cached is None or cached[0] != stamp:
        cached = _PARSED_LOGS[str(directory)] = (stamp, _parse_events(str(directory)))
    return cached[1]


def _detail(root: Path, directory: Path) -> dict[str, Any]:
    meta = _metadata(root, directory)
    events = _parsed_events(directory)[0]
    decisions = [ev for ev in events if ev["type"] == "decision"]
    chapter_counts: Counter = Counter()
    for decision in decisions:
        chapter_counts[str(decision.get("chapter") or "Unknown")] += 1
    ordered_chapters = list(
        dict.fromkeys(str(ev.get("chapter") or "Unknown") for ev in events)
    )
    return {
        "run": meta,
        "events": events,
        "decisions": decisions,
        "decisions_by_chapter": [
            {"chapter": ch, "choices": chapter_counts[ch]} for ch in ordered_chapters
        ],
    }


def _compare(details: list[dict[str, Any]]) -> dict[str, Any]:
    # Repeated visits to one decision node are distinguished by visit number.
    sequences: list[dict[tuple[str, int], dict[str, Any]]] = []
    for detail in details:
        seen: Counter = Counter()
        indexed = {}
        for decision in detail["decisions"]:
            node = str(decision["node_id"])
            seen[node] += 1
            indexed[(node, seen[node])] = decision
        sequences.append(indexed)
    keys = set(sequences[0]) | set(sequences[1])
    rows = []
    identical = different = unshared = 0
    for key in keys:
        left, right = (seq.get(key) for seq in sequences)
        if left and right:
            status = (
                "same"
                if left.get("choice_id") == right.get("choice_id")
                else "different"
            )
            if status == "same":
                identical += 1
            else:
                different += 1
        else:
            status = "only_left" if left else "only_right"
            unshared += 1
        rows.append(
            {
                "node_id": key[0],
                "occurrence": key[1],
                "chapter": (left or right).get("chapter"),
                "status": status,
                "left": left,
                "right": right,
            }
        )
    rows.sort(key=lambda row: ((row["left"] or row["right"])["index"], row["node_id"]))
    return {
        "runs": [d["run"] for d in details],
        "identical": identical,
        "different": different,
        "unshared": unshared,
        "shared": identical + different,
        "rows": rows,
        "notes": "Only the same decision node and visit number can be compared directly. Different paths can encounter different choices.",
    }


def _chapter_info(
    graph: dict, nodes: dict, chapters: list[str]
) -> dict[str, dict[str, Any]]:
    characters: dict[str, Counter] = {chapter: Counter() for chapter in chapters}
    for node in nodes.values():
        if node.get("chapter") and node.get("character") not in (None, "multiple"):
            characters[str(node["chapter"])][node["character"]] += 1
    is_detroit = DETROIT_SOURCE in str(graph.get("metadata", {}).get("source", ""))
    return {
        chapter: {
            "title": DETROIT_CHAPTER_TITLES.get(chapter) if is_detroit else None,
            "character": characters[chapter].most_common(1)[0][0]
            if characters[chapter]
            else None,
        }
        for chapter in chapters
    }


def _flowchart_projection(
    graph: dict, *, complete: bool, source: str
) -> dict[str, Any]:
    """A read-only graph for the browser, with each scene's script but not its source keys."""
    nodes = {}
    for node_id, node in graph.get("nodes", {}).items():
        nodes[node_id] = {
            k: node[k]
            for k in (
                "id",
                "type",
                "chapter",
                "character",
                "heading",
                "description",
                "next",
                "if_true",
                "if_false",
                "flag",
                "unverified",
                "condition_text",
                "exploration",
                "key",
            )
            if k in node
        }
        nodes[node_id]["moment"] = _moment_id(node_id)
        if node.get("type") == "scene":
            nodes[node_id]["observations"] = node.get("observations", [])
            nodes[node_id]["dialogue"] = [
                {"speaker": line.get("speaker"), "text": line.get("text")}
                for line in node.get("dialogue", [])
            ]
        if node.get("type") == "choice":
            nodes[node_id]["options"] = [
                {
                    k: o[k]
                    for k in ("id", "label", "next", "requirements_unverified")
                    if k in o
                }
                for o in node.get("options", [])
            ]
        if node.get("type") == "condition":
            nodes[node_id]["branches"] = [
                {k: b[k] for k in ("next", "condition_text") if k in b}
                for b in node.get("branches", [])
            ]
    chapters = list(
        dict.fromkeys(
            str(node["chapter"]) for node in nodes.values() if node.get("chapter")
        )
    )
    return {
        "metadata": graph.get("metadata", {}),
        "start": graph.get("start"),
        "complete": complete,
        "source": source,
        "chapters": chapters,
        "chapter_info": _chapter_info(graph, nodes, chapters),
        "node_count": len(nodes),
        "nodes": nodes,
    }


def _event_only_graph(directory: Path) -> dict:
    """Compatibility for old logs: never fabricate the unrecorded branches."""
    events = list(iter_events(directory))
    nodes = {}
    for i, event in enumerate(events):
        nid = event.get("node_id")
        if not nid:
            continue
        typ = event.get("type")
        scene = (
            (event.get("input") or {}).get("current_scene")
            or event.get("visible_to_agent")
            or {}
        )
        node = nodes.setdefault(
            nid, {"id": nid, "type": "scene", "chapter": event.get("chapter")}
        )
        node.update(
            type={"decision": "choice"}.get(typ, typ),
            chapter=event.get("chapter"),
            heading=scene.get("heading"),
            description=scene.get("description"),
            character=scene.get("character"),
        )
        next_id = events[i + 1].get("node_id") if i + 1 < len(events) else None
        if typ == "decision":
            chosen = (event.get("output") or {}).get("choice_id")
            node["options"] = [
                {
                    "id": opt["id"],
                    "label": opt.get("label", opt["id"]),
                    "next": next_id if opt["id"] == chosen else None,
                }
                for opt in (event.get("input") or {}).get("available_choices", [])
            ]
        else:
            node["next"] = next_id
    return {
        "metadata": {"title": "Partial reconstruction from recorded events"},
        "start": events[0].get("node_id") if events else None,
        "nodes": nodes,
    }


def _load_saved_graph(
    directory: Path, extra_graphs_dir: Path | None
) -> tuple[dict, bool, str]:
    expected = (_json_file(directory / "experiment.json") or {}).get("graph_sha256")
    # New benchmark runs always include their original full story graph.
    snapshot = _json_file(directory / "story-graph.json")
    if snapshot is not None and (not expected or canonical_hash(snapshot) == expected):
        return snapshot, True, "run_snapshot"
    # Compatibility with older runs, and optionally a user-provided graph directory.
    candidates = [Path(__file__).resolve().parent.parent / "examples"]
    if extra_graphs_dir is not None:
        candidates.insert(0, extra_graphs_dir)
    for parent in candidates:
        if not parent.is_dir():
            continue
        for path in parent.rglob("*.json"):
            # Ignore experiment/checkpoint/summary files even if a graph dir is broad.
            if path.name in {"experiment.json", "summary.json", "checkpoint.json"}:
                continue
            graph = _json_file(path)
            if (
                graph
                and "nodes" in graph
                and (not expected or canonical_hash(graph) == expected)
            ):
                return graph, True, "matched_local_graph"
    return _event_only_graph(directory), False, "event_log_only"


# (story hash, where it is found) -> (graph, Flowchart projection). Every Run of one story
# shares its graph, so it is loaded, hashed and projected once per story, not per request.
_STORIES: dict[tuple, tuple[dict, dict]] = {}


def _story(directory: Path, extra_graphs_dir: Path | None) -> tuple[dict, dict]:
    """A Run's story graph and its Flowchart projection."""
    expected = (_json_file(directory / "experiment.json") or {}).get("graph_sha256")
    key = (expected, (directory / "story-graph.json").exists(), str(extra_graphs_dir))
    if key in _STORIES:
        return _STORIES[key]
    graph, complete, source = _load_saved_graph(directory, extra_graphs_dir)
    story = graph, _flowchart_projection(graph, complete=complete, source=source)
    if complete and expected:
        _STORIES[key] = story
    return story


def _chapter_briefing(
    directory: Path, extra_graphs_dir: Path | None, chapter: str
) -> str | None:
    """Graphs older than Chapter Briefings have none."""
    return chapter_briefing(_story(directory, extra_graphs_dir)[0], chapter)


def _art_file(art_root: Path, relative: Any) -> Path | None:
    """An installed image inside the art folder, or None; never a path outside it."""
    if not isinstance(relative, str) or not relative:
        return None
    path = (art_root / relative).resolve()
    if not path.is_relative_to(art_root) or not path.is_file():
        return None
    return path


def _installed_scene_art(art_root: Path, manifest: Path) -> dict[str, dict[str, Any]]:
    """Manifest scenes whose image is actually installed, by key. Checked again when the
    manifest changes, and at most every ART_RECHECK_SECONDS for newly added images."""
    return _cached_scene_art(
        str(art_root),
        str(manifest),
        _stamp(manifest),
        int(time.time() // ART_RECHECK_SECONDS),
    )


@lru_cache(maxsize=4)
def _cached_scene_art(
    art_root_s: str, manifest_s: str, *_versions
) -> dict[str, dict[str, Any]]:
    art_root, manifest = Path(art_root_s), Path(manifest_s)
    scenes = (_json_file(manifest) or {}).get("scenes", [])
    installed: dict[str, dict[str, Any]] = {}
    for scene in scenes if isinstance(scenes, list) else []:
        if not isinstance(scene, dict) or not isinstance(scene.get("key"), str):
            continue
        if _art_file(art_root, scene.get("file")) is not None:
            installed[scene["key"]] = scene
    return installed


def _scene_art_key(
    scenes: dict[str, dict[str, Any]], chapter: str, heading: Any
) -> str | None:
    """The installed image for a scene: its heading's image, else the chapter's main one."""
    main = None
    for scene in scenes.values():
        if str(scene.get("chapter")) != chapter:
            continue
        if heading in (scene.get("headings") or []):
            return scene["key"]
        if scene.get("chapter_main") and main is None:
            main = scene["key"]
    return main


def create_app(
    runs_dir: str | Path = "runs",
    graphs_dir: str | Path | None = None,
    images_dir: str | Path | None = None,
    art_manifest: str | Path | None = None,
) -> FastAPI:
    root = Path(runs_dir).expanduser().resolve()
    images_root = Path(images_dir).expanduser().resolve() if images_dir else IMAGES
    manifest_path = Path(art_manifest or SCENE_ART_MANIFEST).expanduser()
    graph_root = (
        Path(graphs_dir).expanduser().resolve() if graphs_dir is not None else None
    )
    app = FastAPI(title="LLM: Become Human", version="0.3.0", docs_url="/api/docs")

    @app.middleware("http")
    async def revalidate_frontend(request, call_next):
        # Without this, browsers can keep an old page after the dashboard is updated.
        response = await call_next(request)
        if not request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/health")
    def health():
        return {"ok": True, "runs_dir": str(root)}

    @app.get("/api/runs")
    def list_runs():
        return {
            "runs": sorted(
                (_metadata(root, path) for path in _discovered_runs(root)),
                key=lambda run: run.get("started_at") or "",
                reverse=True,
            )
        }

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return _detail(root, _resolve_run(root, run_id))

    @app.get("/api/runs/{run_id}/flowchart")
    def get_flowchart(run_id: str):
        return _story(_resolve_run(root, run_id), graph_root)[1]

    @app.get("/api/runs/{run_id}/story")
    def get_story(run_id: str, chapter: str):
        # A chapter the run never entered is a normal answer, not an error.
        directory = _resolve_run(root, run_id)
        scenes = _installed_scene_art(images_root, manifest_path)
        moments = [
            {**moment, "art": _scene_art_key(scenes, chapter, moment.get("heading"))}
            if moment.get("type") == "scene"
            else moment
            for moment in _parsed_events(directory)[1].get(chapter, [])
        ]
        return {
            "chapter": chapter,
            "briefing": _chapter_briefing(directory, graph_root, chapter),
            "moments": moments,
        }

    @app.get("/api/runs/{run_id}/events/{event_index}")
    def get_event(run_id: str, event_index: int):
        if event_index < 0:
            raise HTTPException(status_code=404, detail="Unknown event")
        directory = _resolve_run(root, run_id)
        for event in iter_events(directory):
            if event.get("index") == event_index:
                return _capped_justification(event)
        raise HTTPException(status_code=404, detail="Unknown event")

    @app.get("/api/runs/{run_id}/decisions.csv")
    def export_decisions(run_id: str):
        detail = _detail(root, _resolve_run(root, run_id))
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(
            [
                "event_index",
                "timestamp",
                "chapter",
                "node_id",
                "character",
                "choice_id",
                "choice_label",
                "rationale",
                "relevant_prior_choices",
                "state_changes",
            ]
        )
        for decision in detail["decisions"]:
            before, after = (
                decision.get("flags_before") or {},
                decision.get("flags_after") or {},
            )
            changes = {
                k: {"before": before.get(k), "after": after.get(k)}
                for k in before.keys() | after.keys()
                if before.get(k) != after.get(k)
            }
            writer.writerow(
                [
                    decision["index"],
                    decision["timestamp"],
                    decision["chapter"],
                    decision["node_id"],
                    decision.get("character"),
                    decision["choice_id"],
                    decision["label"],
                    decision["rationale"],
                    json.dumps(
                        decision.get("relevant_prior_choices", []), ensure_ascii=False
                    ),
                    json.dumps(changes, ensure_ascii=False),
                ]
            )
        return Response(
            stream.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{run_id[:40]}-decisions.csv"'
            },
        )

    @app.get("/api/compare")
    def compare(run_ids: list[str] = Query(...)):
        if len(run_ids) != 2:
            raise HTTPException(status_code=422, detail="Provide exactly two run_ids")
        return _compare(
            [_detail(root, _resolve_run(root, run_id)) for run_id in run_ids]
        )

    @app.get("/api/art/title")
    def title_art():
        art = images_root / "ui" / "title.webp"
        if not art.is_file():
            raise HTTPException(status_code=404, detail="No title art installed")
        return FileResponse(art, media_type="image/webp")

    @app.get("/api/art/manifest")
    def art_manifest_route():
        return {
            "scenes": [
                {
                    k: scene.get(k)
                    for k in (
                        "key",
                        "chapter",
                        "character",
                        "headings",
                        "chapter_main",
                        "caption",
                    )
                }
                | {"url": f"/api/art/scene/{quote(key, safe='')}"}
                for key, scene in _installed_scene_art(
                    images_root, manifest_path
                ).items()
            ]
        }

    @app.get("/api/art/scene/{key}")
    def scene_art(key: str):
        # Only keys named in the manifest are served, so a request can never pick a path.
        scene = _installed_scene_art(images_root, manifest_path).get(key)
        path = _art_file(images_root, scene.get("file")) if scene else None
        if path is None:
            raise HTTPException(status_code=404, detail="Scene art not installed")
        return FileResponse(
            path,
            media_type="image/webp",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/")
    def home():
        return FileResponse(ASSETS / "index.html", media_type="text/html")

    app.mount("/assets", StaticFiles(directory=ASSETS), name="dashboard_assets")
    return app
