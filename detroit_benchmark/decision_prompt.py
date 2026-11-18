"""The Decision Prompt: everything a model sees at a choice, and nothing else (ADR 0001).

``decision_prompt(graph, node, offered, run)`` builds it from a ``RunView``: the
Character Memories, the moments each Character lived in other segments since its last
Memory Update, the current Chapter Segment so far, Public News and the goal. Flags stay
internal for routing; other Characters' memories never appear, except in a Joint
Decision (ADR 0005). The Runner passes its Run's state; the token estimate passes
placeholders of the sizes it measures.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass


# A choice's "deciders" (ADR 0005). Two or more make a Joint Decision, made with all
# their Character Memories and each one's view of the moment. One other than the
# segment's Character makes a Cross-Segment Decision: that Character decides alone,
# with its own memory, inside another Character's segment.
JOINT_DECISION_INSTRUCTION = (
    "This is a Joint Decision: it belongs to both {names}. Decide it with both points "
    "of view: each Character's own memory and what each knows of this moment, given in "
    "points_of_view. The outcome becomes part of both Characters' stories."
)


def and_list(names: list[str]) -> str:
    """Names as prose: "A", "A and B", "A, B and C"."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def decision_text(deciders: list[str]) -> str:
    """How the Story and the other Characters' memories word who decided."""
    if len(deciders) == 1:
        return f"Decided as {deciders[0]}"
    return (
        f"Decided with {and_list([name + chr(39) + 's' for name in deciders])} memories"
    )


def is_cross_segment(node: dict) -> bool:
    """Whether a choice is a Cross-Segment Decision: decided by one Character other
    than the segment's own (ADR 0005)."""
    deciders = node.get("deciders") or []
    return len(deciders) == 1 and deciders[0] != node.get("character")


@dataclass(frozen=True)
class RunView:
    """What a Run has to show a model at a choice."""

    # Each Character's Character Memory.
    memories: Mapping[str, str]
    # Per Character, the moments it lived in other Characters' segments since its last
    # Memory Update (Joint and Cross-Segment Decisions).
    pending: Mapping[str, list]
    # The current Chapter Segment so far.
    segment: list
    # Public News: the latest headlines, or None.
    news: Sequence[str] | None
    goal: str


def chapter_briefing(graph: dict, chapter) -> str | None:
    """The Chapter Briefing for a Chapter Segment, if the graph has one."""
    briefing = (graph.get("chapter_briefings") or {}).get(str(chapter))
    return briefing if isinstance(briefing, str) else None


def scene_view(node: dict) -> dict:
    """The ``current_scene`` a decision prompt opens with."""
    return {
        "chapter": node.get("chapter"),
        "character": node.get("character"),
        "heading": node.get("heading"),
        "description": node.get("description"),
    }


def decision_prompt(graph: dict, node: dict, offered: list[dict], run: RunView) -> dict:
    """The prompt a model decides ``node`` with, offered ``offered``."""
    character = node.get("character")
    prompt = {"current_scene": scene_view(node)}
    deciders = node.get("deciders")
    # A Cross-Segment Decision's decider sees its own this_moment, not the
    # segment's Chapter Briefing, which is the segment Character's side.
    cross_segment = is_cross_segment(node)
    briefing = chapter_briefing(graph, node.get("chapter"))
    if briefing and not cross_segment:
        prompt["chapter_briefing"] = briefing
    if run.news:
        prompt["news"] = list(run.news)
    views = node.get("decider_context") or {}
    if cross_segment:
        # A Cross-Segment Decision (ADR 0005): the decider's memory and its own view
        # of the moment; nothing of the segment's Character is shown.
        (decider,) = deciders
        prompt["current_scene"]["character"] = decider
        prompt["character_memory"] = run.memories.get(decider, "")
        prompt.update(_other_view(run, decider, views.get(decider, "")))
    elif deciders:
        # A Joint Decision: both Characters' memories, each with its own view of the
        # moment (ADR 0005). Nothing else of the other Character's is shown.
        prompt["current_scene"]["deciders"] = list(deciders)
        prompt["joint_decision"] = JOINT_DECISION_INSTRUCTION.format(
            names=and_list(list(deciders))
        )
        prompt["points_of_view"] = {
            name: {
                "character_memory": run.memories.get(name, ""),
                **(
                    {"chapter_segment_so_far": segment_for(run, name)}
                    if name == character
                    else _other_view(run, name, views.get(name, ""))
                ),
            }
            for name in deciders
        }
    else:
        prompt["character_memory"] = run.memories.get(character, "")
        prompt["chapter_segment_so_far"] = segment_for(run, character)
    prompt["goal"] = run.goal
    prompt["available_choices"] = [
        {"id": o["id"], "label": o["label"]} for o in offered
    ]
    return prompt


def segment_for(run: RunView, character) -> list:
    """What a Character has lived through since its last Memory Update: moments from
    other Characters' segments, then the current segment."""
    return deepcopy(list(run.pending.get(character) or []) + list(run.segment))


def _other_view(run: RunView, name: str, moment: str) -> dict:
    """A decider's view of a moment in another Character's segment: what it knows
    of it, after any earlier such decision of its own not yet in its memory."""
    pending = run.pending.get(name) or []
    return {
        **({"since_last_memory": deepcopy(list(pending))} if pending else {}),
        "this_moment": moment,
    }


def choice_moments(
    node: dict, chosen: dict, rationale: str, on_screen: list[str]
) -> tuple[dict, dict[str, dict]]:
    """What a choice adds to memories: the moment joining the current Chapter Segment,
    and, per decider from outside the segment, the moment it remembers at its next
    Memory Update. ``on_screen`` is the Gauge Feedback the choice flashed.

    When another Character decided alone, the segment's Character only learns the
    outcome; otherwise the segment holds the model's own choice and rationale.
    """
    character = node.get("character")
    deciders = node.get("deciders") or []
    if is_cross_segment(node):
        moment = {
            "at": node.get("heading"),
            "decided_by": deciders[0],
            "outcome": chosen["label"],
        }
    else:
        moment = {
            "at": node.get("heading"),
            "your_choice": chosen["label"],
            "rationale": rationale,
        }
    if on_screen:
        moment["on_screen"] = list(on_screen)
    remembered_by = {
        name: {
            "chapter": node.get("chapter"),
            "at": node.get("heading"),
            "decided": decision_text(deciders),
            "your_choice": chosen["label"],
            "rationale": rationale,
        }
        for name in deciders
        if name != character
    }
    return moment, remembered_by


def feedback_moment(node: dict, on_screen: list[str]) -> dict:
    """The segment entry for Gauge Feedback a condition's branch flashed on screen."""
    return {"at": node.get("heading"), "on_screen": list(on_screen)}
