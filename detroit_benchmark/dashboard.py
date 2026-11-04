"""Read-only dashboard for saved LLM benchmark experiments.

The dashboard is intentionally limited to local, previously recorded run directories.
It does not invoke LLMs or alter the benchmark's state.
"""
from __future__ import annotations

import base64
import csv
import io
import json
from collections import Counter

from .engine import canonical_hash
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

ASSETS = Path(__file__).parent / "dashboard_assets"


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
    if path == root or not path.is_relative_to(root) or not (path / "experiment.json").is_file():
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


def _event_iter(directory: Path):
    """Ignore an incompletely written final JSONL record while runs are live."""
    try:
        with (directory / "events.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    yield parsed
    except OSError:
        return


def _metadata(root: Path, directory: Path) -> dict[str, Any]:
    exp = _json_file(directory / "experiment.json") or {}
    summary = _json_file(directory / "summary.json") or {}
    checkpoint = _json_file(directory / "checkpoint.json") or {}
    state = checkpoint.get("state", {})
    status = summary.get("status") or state.get("status") or "unknown"
    chapters = summary.get("chapters_visited", state.get("chapters_visited", []))
    decisions = summary.get("number_of_choices", len(state.get("decisions", [])))
    return {
        "id": _run_id(root, directory),
        "name": directory.relative_to(root).as_posix(),
        "provider": exp.get("provider", summary.get("provider", "unknown")),
        "display_provider": exp.get("display_provider") if exp.get("synthetic", False) else None,
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
        "total_input_tokens": summary.get("total_input_tokens", state.get("total_input_tokens", 0)),
        "total_output_tokens": summary.get("total_output_tokens", state.get("total_output_tokens", 0)),
        "total_llm_latency_seconds": summary.get("total_llm_latency_seconds", state.get("total_llm_latency_seconds", 0)),
        "warnings": len(summary.get("warnings", state.get("warnings", []))),
        "end_description": summary.get("end_description"),
        "final_flags": summary.get("final_flags", state.get("flags", {})),
        "graph_sha256": exp.get("graph_sha256", summary.get("graph_sha256")),
    }


def _short_event(event: dict[str, Any]) -> dict[str, Any]:
    kind = event.get("type")
    result = {k: event.get(k) for k in ("index", "timestamp", "type", "chapter", "node_id")}
    if kind == "scene":
        scene = event.get("visible_to_agent") or {}
        result.update(heading=scene.get("heading"), description=scene.get("description"),
                      character=scene.get("character"), observations=scene.get("observations", []),
                      dialogue_count=len(scene.get("dialogue", [])))
    elif kind == "decision":
        context = event.get("input") or {}
        scene = context.get("current_scene") or {}
        result.update(heading=scene.get("heading"), description=scene.get("description"),
                      character=scene.get("character"),
                      available_choices=context.get("available_choices", []),
                      label=event.get("label"), choice_key=event.get("decision_key"),
                      choice_id=(event.get("output") or {}).get("choice_id"),
                      rationale=(event.get("output") or {}).get("rationale"),
                      relevant_prior_choices=(event.get("output") or {}).get("relevant_prior_choices", []),
                      flags_before=event.get("flags_before", {}),
                      flags_after=event.get("flags_after", {}),
                      prompt_history_count=len(context.get("entire_decision_history", [])),
                      retrieved_scenes_count=len(context.get("relevant_earlier_scenes", [])),
                      model_info=event.get("model_info", {}),
                      unverified_requirements=event.get("unverified_requirements", []))
    elif kind == "ending":
        result["description"] = event.get("description")
    elif kind in ("condition", "route"):
        result.update({k: event.get(k) for k in ("branch_index", "used_unverified_default", "flag", "value", "assumed", "next") if k in event})
    return result


def _detail(root: Path, directory: Path) -> dict[str, Any]:
    meta = _metadata(root, directory)
    events = [_short_event(event) for event in _event_iter(directory)]
    decisions = [ev for ev in events if ev["type"] == "decision"]
    chapter_counts: Counter = Counter()
    for decision in decisions:
        chapter_counts[str(decision.get("chapter") or "Unknown")] += 1
    ordered_chapters = list(dict.fromkeys(str(ev.get("chapter") or "Unknown") for ev in events))
    return {
        "run": meta, "events": events, "decisions": decisions,
        "decisions_by_chapter": [{"chapter": ch, "choices": chapter_counts[ch]} for ch in ordered_chapters],
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
            status = "same" if left.get("choice_id") == right.get("choice_id") else "different"
            if status == "same": identical += 1
            else: different += 1
        else:
            status = "only_left" if left else "only_right"
            unshared += 1
        rows.append({"node_id": key[0], "occurrence": key[1],
                     "chapter": (left or right).get("chapter"), "status": status,
                     "left": left, "right": right})
    rows.sort(key=lambda row: ((row["left"] or row["right"])["index"], row["node_id"]))
    return {
        "runs": [d["run"] for d in details],
        "identical": identical, "different": different, "unshared": unshared,
        "shared": identical + different,
        "rows": rows,
        "notes": "Only the same decision node and visit number can be compared directly. Different paths can encounter different choices."
    }



def _flowchart_projection(graph: dict, *, complete: bool, source: str) -> dict[str, Any]:
    """A small, read-only graph for the browser; excludes full dialogue and raw game text."""
    nodes = {}
    for node_id, node in graph.get("nodes", {}).items():
        nodes[node_id] = {k: node[k] for k in (
            "id", "type", "chapter", "character", "heading", "description", "next",
            "if_true", "if_false", "flag", "unverified", "condition_text",
        ) if k in node}
        if node.get("type") == "choice":
            nodes[node_id]["options"] = [
                {k: o[k] for k in ("id", "label", "next", "requirements_unverified") if k in o}
                for o in node.get("options", [])
            ]
        if node.get("type") == "condition":
            nodes[node_id]["branches"] = [
                {k: b[k] for k in ("next", "condition_text") if k in b}
                for b in node.get("branches", [])
            ]
    chapters = list(dict.fromkeys(
        str(node["chapter"]) for node in nodes.values() if node.get("chapter")
    ))
    return {"metadata": graph.get("metadata", {}), "start": graph.get("start"),
            "complete": complete, "source": source, "chapters": chapters,
            "node_count": len(nodes), "nodes": nodes}


def _event_only_graph(directory: Path) -> dict:
    """Compatibility for old logs: never fabricate the unrecorded branches."""
    events = list(_event_iter(directory))
    nodes = {}
    for i, event in enumerate(events):
        nid = event.get("node_id")
        if not nid:
            continue
        typ = event.get("type")
        scene = (event.get("input") or {}).get("current_scene") or event.get("visible_to_agent") or {}
        node = nodes.setdefault(nid, {"id": nid, "type": "scene", "chapter": event.get("chapter")})
        node.update(type={"decision": "choice"}.get(typ, typ), chapter=event.get("chapter"),
                    heading=scene.get("heading"), description=scene.get("description"),
                    character=scene.get("character"))
        next_id = events[i+1].get("node_id") if i+1 < len(events) else None
        if typ == "decision":
            chosen = (event.get("output") or {}).get("choice_id")
            node["options"] = [
                {"id": opt["id"], "label": opt.get("label", opt["id"]),
                 "next": next_id if opt["id"] == chosen else None}
                for opt in (event.get("input") or {}).get("available_choices", [])
            ]
        elif typ in ("scene", "chapter_exit"):
            node["next"] = next_id
        elif typ in ("condition", "route"):
            node["next"] = next_id
    return {"metadata": {"title": "Partial reconstruction from recorded events"},
            "start": events[0].get("node_id") if events else None, "nodes": nodes}


def _load_saved_graph(root: Path, directory: Path, extra_graphs_dir: Path | None) -> tuple[dict, bool, str]:
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
            if graph and "nodes" in graph and (not expected or canonical_hash(graph) == expected):
                return graph, True, "matched_local_graph"
    return _event_only_graph(directory), False, "event_log_only"


def create_app(runs_dir: str | Path = "runs", graphs_dir: str | Path | None = None) -> FastAPI:
    root = Path(runs_dir).expanduser().resolve()
    graph_root = Path(graphs_dir).expanduser().resolve() if graphs_dir is not None else None
    app = FastAPI(title="Detroit LLM Benchmark Dashboard", version="0.3.0", docs_url="/api/docs")

    @app.get("/api/health")
    def health():
        return {"ok": True, "runs_dir": str(root)}

    @app.get("/api/runs")
    def list_runs():
        return {"runs": sorted((_metadata(root, path) for path in _discovered_runs(root)),
                               key=lambda run: run.get("started_at") or "", reverse=True)}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        return _detail(root, _resolve_run(root, run_id))

    @app.get("/api/runs/{run_id}/flowchart")
    def get_flowchart(run_id: str):
        directory = _resolve_run(root, run_id)
        graph, complete, source = _load_saved_graph(root, directory, graph_root)
        return _flowchart_projection(graph, complete=complete, source=source)

    @app.get("/api/runs/{run_id}/events/{event_index}")
    def get_event(run_id: str, event_index: int):
        if event_index < 0:
            raise HTTPException(status_code=404, detail="Unknown event")
        directory = _resolve_run(root, run_id)
        for event in _event_iter(directory):
            if event.get("index") == event_index:
                return event
        raise HTTPException(status_code=404, detail="Unknown event")

    @app.get("/api/runs/{run_id}/decisions.csv")
    def export_decisions(run_id: str):
        detail = _detail(root, _resolve_run(root, run_id))
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["event_index", "timestamp", "chapter", "node_id", "character", "choice_id",
                         "choice_label", "rationale", "relevant_prior_choices", "state_changes"])
        for decision in detail["decisions"]:
            before, after = decision.get("flags_before") or {}, decision.get("flags_after") or {}
            changes = {k: {"before": before.get(k), "after": after.get(k)}
                       for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
            writer.writerow([decision["index"], decision["timestamp"], decision["chapter"],
                             decision["node_id"], decision.get("character"), decision["choice_id"],
                             decision["label"], decision["rationale"],
                             json.dumps(decision.get("relevant_prior_choices", []), ensure_ascii=False),
                             json.dumps(changes, ensure_ascii=False)])
        return Response(stream.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{run_id[:40]}-decisions.csv"'})

    @app.get("/api/compare")
    def compare(run_ids: list[str] = Query(...)):
        if len(run_ids) != 2:
            raise HTTPException(status_code=422, detail="Provide exactly two run_ids")
        return _compare([_detail(root, _resolve_run(root, run_id)) for run_id in run_ids])

    @app.get("/legacy")
    def legacy_home():
        return FileResponse(ASSETS / "legacy.html", media_type="text/html")

    @app.get("/")
    def home():
        return FileResponse(ASSETS / "index.html", media_type="text/html")

    app.mount("/assets", StaticFiles(directory=ASSETS), name="dashboard_assets")
    return app
