"""A Run's timeline: the Moments the Story and the Flowchart both draw, read from its events.

Every story meaning the dashboard shows is worked out here, once, in Python: which pass
through a node a decision is (a node can recur, so a decision is known by its node and
visit, its ``key``), where the Run went next, who decided and how the Story words it, and
what it assumed where the story could not tell. The browser only draws them.

A Moment is one story graph node, so the Story and the Flowchart address it by the same
id (``moment``).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .decision_prompt import and_list, decision_text
from .ending import assumed_route_text
from .engine import limit_sentences
from .run_folder import RunFolder


def moment_id(node_id: Any) -> str | None:
    """A Moment is one story graph node: the Story and the Flowchart both address it by this id."""
    return str(node_id) if node_id is not None else None


def event_scene(event: dict[str, Any]) -> dict[str, Any]:
    """The scene an event shows: a decision's prompt scene, else the scene the agent saw."""
    return (
        (event.get("input") or {}).get("current_scene")
        or event.get("visible_to_agent")
        or {}
    )


def event_output(event: dict[str, Any]) -> dict[str, Any]:
    return event.get("output") or {}


def chapter_of(event: dict[str, Any]) -> str:
    return str(event.get("chapter") or "Unknown")


def capped_justification(event: dict[str, Any]) -> dict[str, Any]:
    """Runs recorded before the engine capped justifications are shown capped too."""
    output = event.get("output")
    if event.get("type") != "decision" or not isinstance(output, dict):
        return event
    rationale = output.get("rationale")
    if not isinstance(rationale, str):
        return event
    return {**event, "output": {**output, "rationale": limit_sentences(rationale)}}


def decision_question(character: Any, deciders: list[str] | None) -> str:
    """The question the Story asks at a decision: who decides it."""
    if deciders and len(deciders) > 1:
        return f"What do {and_list(deciders)} do?"
    if character and character != "multiple":
        return f"What does {character} do?"
    return "What happens next?"


def _deciders(event: dict[str, Any]) -> list[str] | None:
    deciders = event.get("deciders")
    return deciders if isinstance(deciders, list) and deciders else None


def _summary(event: dict[str, Any]) -> dict[str, Any]:
    """An event as the Run's detail lists it: everything but the prompt and the script."""
    kind = event.get("type")
    result = {
        k: event.get(k) for k in ("index", "timestamp", "type", "chapter", "node_id")
    }
    if kind == "scene":
        scene = event_scene(event)
        result.update(
            heading=scene.get("heading"),
            description=scene.get("description"),
            character=scene.get("character"),
            observations=scene.get("observations", []),
            dialogue_count=len(scene.get("dialogue", [])),
        )
    elif kind == "decision":
        context = event.get("input") or {}
        scene = event_scene(event)
        output = event_output(event)
        result.update(
            heading=scene.get("heading"),
            description=scene.get("description"),
            character=scene.get("character"),
            available_choices=context.get("available_choices", []),
            label=event.get("label"),
            choice_key=event.get("decision_key"),
            choice_id=output.get("choice_id"),
            rationale=output.get("rationale"),
            relevant_prior_choices=output.get("relevant_prior_choices", []),
            flags_before=event.get("flags_before", {}),
            flags_after=event.get("flags_after", {}),
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


def _story_moment(event: dict[str, Any]) -> dict[str, Any] | None:
    """What a reader needs from one event, including the dialogue the summary leaves out."""
    kind = event.get("type")
    beat = {k: event.get(k) for k in ("index", "type", "node_id")}
    beat["moment"] = moment_id(event.get("node_id"))
    if kind == "scene":
        scene = event_scene(event)
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
        scene, output = event_scene(event), event_output(event)
        deciders = _deciders(event)
        beat.update(
            heading=scene.get("heading"),
            character=scene.get("character"),
            question=decision_question(scene.get("character"), deciders),
            available_choices=(event.get("input") or {}).get("available_choices", []),
            choice_id=output.get("choice_id"),
            rationale=output.get("rationale"),
        )
        if deciders:
            # A Joint Decision, or a Cross-Segment Decision by another Character alone.
            beat.update(deciders=deciders, decided=decision_text(deciders))
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
        if beat["assumed"]:
            beat["text"] = assumed_route_text(event.get("flag"), event.get("value"))
    elif kind == "ending":
        beat.update(description=event.get("description"))
    elif kind == "memory_update":
        # A Memory Update closes a Chapter Segment; the timeline adds the previous memory.
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
    if kind in ("decision", "condition") and isinstance(event.get("feedback"), list):
        # Gauge Feedback: what the game flashed on screen after this moment.
        beat["feedback"] = [
            item["text"]
            for item in event["feedback"]
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
    return beat


@dataclass(frozen=True)
class Timeline:
    """A Run's events, read once per version of its log."""

    # Every event as the Run's detail lists it; a decision carries its ``visit`` and
    # ``key``, and every event the node the Run went to next (``next``, ``next_chapter``).
    events: list[dict[str, Any]]
    # Per chapter, the Moments the Story reads, in order.
    story: dict[str, list[dict[str, Any]]]
    # Where each event index starts in the log, so one event is read alone.
    offsets: dict[Any, int]

    @property
    def decisions(self) -> list[dict[str, Any]]:
        return [event for event in self.events if event["type"] == "decision"]

    def chapter(self, chapter: str, graph: dict) -> list[dict[str, Any]]:
        """A chapter's Moments for the Story, worded with the story graph the Run played:
        a condition the story could not decide says what the Run assumed."""
        moments = []
        for moment in self.story.get(chapter, []):
            if moment["type"] == "condition" and moment["used_unverified_default"]:
                node = (graph.get("nodes") or {}).get(moment["node_id"]) or {}
                branches = node.get("branches") or []
                index = moment["branch_index"]
                taken = (
                    branches[index].get("condition_text")
                    if isinstance(index, int) and 0 <= index < len(branches)
                    else None
                )
                if taken:
                    moment = {**moment, "text": f"Assumed: {taken}"}
            moments.append(moment)
        return moments


def _read(folder: RunFolder) -> Timeline:
    events: list[dict[str, Any]] = []
    story: dict[str, list[dict[str, Any]]] = {}
    offsets: dict[Any, int] = {}
    visits: Counter = Counter()
    memories: dict[str, str] = {}
    for offset, raw in folder.events_at():
        offsets.setdefault(raw.get("index"), offset)
        event = capped_justification(raw)
        summary = _summary(event)
        if events:
            # Where the Run went from the event before: the node this event is at.
            events[-1].update(
                next=event.get("node_id"), next_chapter=event.get("chapter")
            )
        events.append(summary)
        beat = _story_moment(event)
        if beat is None:
            continue
        if beat["type"] == "memory":
            # Each Character's memory is compared only with its own last one.
            beat["previous"] = memories.get(beat["character"], "")
            memories[beat["character"]] = beat["memory"]
        # A node can recur, so each pass through a Moment is numbered from the Run's start.
        visits[beat["moment"]] += 1
        beat["visit"] = visits[beat["moment"]]
        if beat["type"] == "decision":
            beat["key"] = f"{beat['moment']}#{beat['visit']}"
            summary.update(visit=beat["visit"], key=beat["key"])
        story.setdefault(chapter_of(event), []).append(beat)
    return Timeline(events, story, offsets)


# Run directory -> (log version, timeline). Only the latest version of a live Run is kept.
_TIMELINES: dict[str, tuple[tuple[int, int], Timeline]] = {}


def timeline(directory: Path) -> Timeline:
    """The timeline of the Run in ``directory``. Decision events repeat the whole prompt,
    so logs reach tens of MB: each version of a log is read once."""
    folder = RunFolder(directory)
    version = folder.events_version()
    if version is None:
        return Timeline([], {}, {})
    cached = _TIMELINES.get(str(directory))
    if cached is None or cached[0] != version:
        cached = _TIMELINES[str(directory)] = (version, _read(folder))
    return cached[1]
