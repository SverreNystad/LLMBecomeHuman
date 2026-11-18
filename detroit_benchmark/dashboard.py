"""Read-only dashboard for saved LLM benchmark experiments.

The dashboard is intentionally limited to local, previously recorded run directories.
It does not invoke LLMs or alter the benchmark's state, except that with ``allow_own_runs``
visitors can play Visitor Runs with their own key (see visitor_runs.py).
"""

from __future__ import annotations

import base64
import csv
import io
import json
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .decision_prompt import chapter_briefing
from .ending import ending_summary, route_question
from .engine import (
    create_model,
)
from .run_folder import (
    NOT_STORY_GRAPHS,
    RunFolder,
    canonical_hash,
    file_stamp as _stamp,
    find_runs,
    read_json_object as _json_file,
)
from .run_timeline import (
    capped_justification,
    chapter_of,
    event_output,
    event_scene,
    moment_id,
    timeline,
)
from .visitor_estimate import story_estimate
from .visitor_runs import (
    PROVIDERS,
    VISITOR_FOLDER,
    VISITOR_STORY,
    AlreadyPlaying,
    Busy,
    ModelFactory,
    ModelLister,
    PlayingRuns,
    ProviderAuthError,
    ProviderUnreachable,
    Publications,
    RateLimit,
    TooManyRequests,
    is_public,
    list_models,
    mark_cut_off_runs,
    scrub,
    start_visitor_run,
)

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
    "32.7": "Battle for Detroit: Connor in the Zen Garden",
    "32.8": "Battle for Detroit: Connor in the Crowd",
    "32.9": "Battle for Detroit: Kara After the Assault",
    "final": "Final Routes",
}


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
        or not RunFolder(path).is_run()
    ):
        raise HTTPException(status_code=404, detail="Unknown run")
    return path


def _discovered_runs(root: Path) -> list[Path]:
    return [folder.path for folder in find_runs(root) if folder.has_events()]


def _is_private(root: Path, directory: Path) -> bool:
    """Visitor Runs are private, unless made public: only a request naming their id lists them."""
    return directory.relative_to(root).parts[0] == VISITOR_FOLDER and not is_public(
        directory
    )


def _visitor_ip(request: Request) -> str:
    """The client IP that identifies a visitor: Cloudflare's connecting IP, else the peer."""
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    return forwarded or (request.client.host if request.client else "unknown")


def _metadata(root: Path, directory: Path) -> dict[str, Any]:
    """A Run as the Run list shows it; polled every few seconds, so its folder re-reads
    its files only when they change."""
    meta = {
        "id": _run_id(root, directory),
        "name": directory.relative_to(root).as_posix(),
        **RunFolder(directory).metadata(),
    }
    if (
        meta["status"] == "running"
        and RunFolder(directory).seconds_since_write() > STALE_RUN_SECONDS
    ):
        meta["status"] = "stopped"
    return meta


def _detail(root: Path, directory: Path) -> dict[str, Any]:
    meta = _metadata(root, directory)
    events = timeline(directory).events
    decisions = timeline(directory).decisions
    chapter_counts: Counter = Counter()
    for decision in decisions:
        chapter_counts[chapter_of(decision)] += 1
    ordered_chapters = list(dict.fromkeys(map(chapter_of, events)))
    return {
        "run": meta,
        "events": events,
        "decisions": decisions,
        "decisions_by_chapter": [
            {"chapter": ch, "choices": chapter_counts[ch]} for ch in ordered_chapters
        ],
        "ending_summary": ending_summary(
            meta["final_flags"] or {},
            [ev for ev in events if ev["type"] == "route"],
            RunFolder(directory).news(),
            finished=meta["status"] == "complete",
        ),
    }


def _compare(details: list[dict[str, Any]]) -> dict[str, Any]:
    # Repeated visits to one decision node are distinguished by visit number.
    sequences = [
        {(str(d["node_id"]), d["visit"]): d for d in detail["decisions"]}
        for detail in details
    ]
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


def _chapter_order(graph: dict, nodes: dict) -> list[str]:
    """Chapters in story order: as the graph lists its Chapter Segments, so a segment
    played late (32.7, 32.8) follows the ones before it; others keep first-seen order."""
    seen = list(
        dict.fromkeys(
            str(node["chapter"]) for node in nodes.values() if node.get("chapter")
        )
    )
    listed = [str(c) for c in graph.get("chapter_entries", {})]
    rank = {chapter: i for i, chapter in enumerate(listed)}
    return sorted(seen, key=lambda c: (rank.get(c, len(listed)), seen.index(c)))


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
        nodes[node_id]["moment"] = moment_id(node_id)
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
        if node.get("type") == "route" and "heading" not in node:
            # The Flowchart labels a route node with the question its flag answers.
            question = route_question(str(node.get("flag")))
            if question:
                nodes[node_id]["heading"] = question
        if node.get("type") == "condition":
            nodes[node_id]["branches"] = [
                {k: b[k] for k in ("next", "condition_text") if k in b}
                for b in node.get("branches", [])
            ]
    chapters = _chapter_order(graph, nodes)
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
    events = list(RunFolder(directory).events())
    nodes = {}
    for i, event in enumerate(events):
        nid = event.get("node_id")
        if not nid:
            continue
        typ = event.get("type")
        scene = event_scene(event)
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
            chosen = event_output(event).get("choice_id")
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
    folder = RunFolder(directory)
    expected = folder.graph_sha256()
    # New benchmark runs always include their original full story graph.
    snapshot = folder.story_graph()
    if snapshot is not None:
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
            if path.name in NOT_STORY_GRAPHS:
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
    folder = RunFolder(directory)
    expected = folder.graph_sha256()
    key = (expected, folder.has_story_graph(), str(extra_graphs_dir))
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
    *,
    allow_own_runs: bool = False,
    model_lister: ModelLister | None = None,
    model_factory: ModelFactory = create_model,
    visitor_story: str | Path = VISITOR_STORY,
    max_playing: int = 2,
    max_playing_per_visitor: int = 1,
    model_listings_per_minute: int = 10,
) -> FastAPI:
    """The dashboard app. With ``allow_own_runs``, visitors can play Visitor Runs with their
    own key: ``model_lister`` (provider, key) -> model ids and ``model_factory`` (the shape of
    :func:`engine.create_model`) are the real ones unless a test injects fakes. At most
    ``max_playing`` Visitor Runs play at once, and ``max_playing_per_visitor`` per client IP;
    a client IP may list a provider's models ``model_listings_per_minute`` times a minute."""
    root = Path(runs_dir).expanduser().resolve()
    images_root = Path(images_dir).expanduser().resolve() if images_dir else IMAGES
    manifest_path = Path(art_manifest or SCENE_ART_MANIFEST).expanduser()
    graph_root = (
        Path(graphs_dir).expanduser().resolve() if graphs_dir is not None else None
    )
    story_path = Path(visitor_story).expanduser().resolve()
    app = FastAPI(title="LLM: Become Human", version="0.3.0", docs_url="/api/docs")
    # Lists a provider's models for the Visitor Run form.
    app.state.model_lister = model_lister or list_models
    # Empty unless Visitor Runs are on.
    playing = PlayingRuns(max_playing, max_playing_per_visitor)

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
    def list_runs(visitor_runs: list[str] = Query([])):
        """Every Run except private Visitor Runs, which are listed only when named."""
        named = set(visitor_runs)
        # A Visitor Run is playing until its thread has ended and its publication is decided.
        still_playing = playing.playing_ids()
        listed = (
            path
            for path in _discovered_runs(root)
            if _run_id(root, path) in named or not _is_private(root, path)
        )
        runs = (
            {**run, "status": "running"} if run["id"] in still_playing else run
            for run in (_metadata(root, path) for path in listed)
        )
        return {
            "runs": sorted(
                runs,
                key=lambda run: run.get("started_at") or "",
                reverse=True,
            )
        }

    if allow_own_runs:
        _add_visitor_run_routes(
            app,
            root,
            story_path,
            playing,
            model_factory,
            RateLimit(model_listings_per_minute),
        )

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
            for moment in timeline(directory).chapter(
                chapter, _story(directory, graph_root)[0]
            )
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
        offset = timeline(directory).offsets.get(event_index)
        event = None if offset is None else RunFolder(directory).event_at(offset)
        if event is None:
            raise HTTPException(status_code=404, detail="Unknown event")
        return capped_justification(event)

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


class VisitorRunStart(BaseModel):
    provider: str
    model: str
    key: str


class VisitorModelsRequest(BaseModel):
    provider: str
    key: str


def _require_known_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HTTPException(status_code=422, detail="Unknown provider")


def _add_visitor_run_routes(
    app: FastAPI,
    root: Path,
    story_path: Path,
    playing: PlayingRuns,
    model_factory: ModelFactory,
    model_listings: RateLimit,
) -> None:
    """Every Visitor Run route: the form's config, model list and token estimate, the
    public-Run check, Start and Stop. Registered only with ``allow_own_runs``."""
    # A Run a restart cut off is partial; a complete one a restart left undecided is decided.
    mark_cut_off_runs(root)
    publications = Publications(root)
    publications.settle()

    @app.get("/api/visitor-runs/config")
    def visitor_run_config():
        return {"providers": list(PROVIDERS)}

    @app.post("/api/visitor-runs/models")
    def list_visitor_models(body: VisitorModelsRequest, request: Request):
        """The model ids the provider lists for this key. The key is never echoed."""
        key = body.key.strip()
        _require_known_provider(body.provider)
        if not key:
            raise HTTPException(status_code=422, detail="Enter your API key")
        try:
            model_listings.check(_visitor_ip(request))
        except TooManyRequests as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from None
        try:
            ids = app.state.model_lister(body.provider, key)
        except ProviderAuthError:
            raise HTTPException(
                status_code=401,
                detail="The provider rejected this API key. Check the key and try again.",
            ) from None
        except ProviderUnreachable:
            raise HTTPException(
                status_code=502,
                detail="Could not reach the provider to list its models. "
                "You can still type a model id.",
            ) from None
        return {"models": list(ids)}

    @app.get("/api/visitor-runs/estimate")
    def estimate_visitor_run(provider: str, model: str):
        """About how many tokens a Visitor Run uses, and whether a public Run of this
        exact model exists already (the form warns before Start if so)."""
        _require_known_provider(provider)
        return {
            **story_estimate(story_path),
            "approximate": True,
            "public_run_exists": publications.public_run_exists(provider, model.strip()),
        }

    @app.get("/api/visitor-runs/public")
    def visitor_run_public(provider: str, model: str):
        return {
            "public_run_exists": publications.public_run_exists(provider, model.strip())
        }

    @app.post("/api/visitor-runs")
    def start_run(body: VisitorRunStart, request: Request):
        _require_known_provider(body.provider)
        model, key = body.model.strip(), body.key.strip()
        if not model or not key:
            raise HTTPException(status_code=422, detail="Enter a key and a model id")
        try:
            slot = playing.reserve(_visitor_ip(request))
        except AlreadyPlaying as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except Busy as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None

        def ended():
            try:
                publications.settle()  # Public if the first complete Run of its model.
            finally:
                playing.release(slot)

        try:
            directory = start_visitor_run(
                root,
                story_path,
                body.provider,
                model,
                key,
                model_factory,
                stop_requested=slot.stop_requested,
                on_end=ended,
            )
        except Exception as exc:
            playing.release(slot)
            detail = scrub(f"Could not start the Run: {exc}", key)
            raise HTTPException(status_code=500, detail=detail) from None
        slot.run_id = _run_id(root, directory)
        return {"id": slot.run_id}

    @app.post("/api/visitor-runs/{run_id}/stop", status_code=202)
    def stop_run(run_id: str):
        """Stops a playing Visitor Run after its current model call; it stays partial."""
        if not playing.stop(run_id):
            raise HTTPException(status_code=404, detail="No such Run is playing")
        return {"id": run_id, "stopping": True}
