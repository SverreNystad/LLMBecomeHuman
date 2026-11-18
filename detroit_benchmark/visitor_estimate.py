"""The token estimate a visitor sees before starting a Visitor Run.

It comes from the story itself: the prompts of every decision and Memory Update along the
story's shortest and longest routes, measured in characters exactly as the engine builds
them, then turned into tokens with a range of characters per token. The range and the
per-call output tokens are calibrated against the maintainers' real Runs, which record both
their prompts and the tokens their providers counted (tests/test_visitor_models_estimate.py
checks every one of them still falls within CALIBRATION_TOLERANCE of the range).

It is an approximation, and only ever tokens, never a price. It is cached per story file.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .engine import (
    DECISION_MAX_OUTPUT_TOKENS,
    DEFAULT_GOAL,
    DEFAULT_MEMORY_MAX_CHARS,
    HEADLINE_MAX_CHARS,
    MEMORY_UPDATE_MAX_OUTPUT_TOKENS,
    PUBLIC_NEWS_LIMIT,
    SYSTEM_PROMPT,
    file_stamp,
    memory_update_payload,
    planned_feedback,
    prompt_message,
    read_json,
    scene_record,
)
from .decision_prompt import chapter_briefing, scene_view
from .story_rules import StoryRules

# Characters per token: (the most tokens a provider counts, the fewest). The real Runs
# measured 2.3 (Claude Sonnet and Haiku 5.5) to 3.9 (OpenAI, Claude Haiku 4.5).
CHARS_PER_TOKEN = (2.25, 4.0)
# Output tokens per decision: the real Runs averaged 75 to 408 (a retry can pass the limit).
DECISION_OUTPUT_TOKENS = (60, DECISION_MAX_OUTPUT_TOKENS)
# Output tokens per Memory Update: half a full memory at 4 characters per token, up to the limit.
MEMORY_UPDATE_OUTPUT_TOKENS = (
    DEFAULT_MEMORY_MAX_CHARS // 8,
    MEMORY_UPDATE_MAX_OUTPUT_TOKENS,
)
# How far outside the range a real Run's recorded totals may fall, as a share of the bound.
CALIBRATION_TOLERANCE = 0.10

# A rationale is at most two sentences: (short, long) in characters.
RATIONALE_CHARS = (100, 400)


@dataclass(frozen=True)
class Route:
    """What a route through the story sends a model: prompt characters (system prompt
    included) over its decisions and Memory Updates."""

    prompt_chars: int
    decisions: int
    memory_updates: int


def token_range(shortest: Route, longest: Route) -> dict:
    """Input and output token ranges from the shortest and longest routes' prompts."""
    most, fewest = CHARS_PER_TOKEN
    return {
        "input_tokens": {
            "low": round(shortest.prompt_chars / fewest),
            "high": round(longest.prompt_chars / most),
        },
        "output_tokens": {
            "low": shortest.decisions * DECISION_OUTPUT_TOKENS[0]
            + shortest.memory_updates * MEMORY_UPDATE_OUTPUT_TOKENS[0],
            "high": longest.decisions * DECISION_OUTPUT_TOKENS[1]
            + longest.memory_updates * MEMORY_UPDATE_OUTPUT_TOKENS[1],
        },
    }


def story_estimate(story: Path) -> dict:
    """The token estimate for a story file, recomputed only when the file changes."""
    return _cached_estimate(str(story), file_stamp(story))


@lru_cache(maxsize=4)
def _cached_estimate(story: str, _stamp) -> dict:
    graph = read_json(Path(story))
    return token_range(*route_extremes(graph))


def route_extremes(graph: dict) -> tuple[Route, Route]:
    """The routes through the story whose prompts are shortest and longest in total.

    The shortest assumes empty Character Memories, short rationales and no Public News;
    the longest full memories, long rationales and full news. Every branch counts as
    possible, whatever the flags; Quick-Time Events and retries are left out.
    """
    return (
        _extreme_route(graph, min, memory=0, rationale=RATIONALE_CHARS[0], news=0),
        _extreme_route(
            graph,
            max,
            memory=DEFAULT_MEMORY_MAX_CHARS,
            rationale=RATIONALE_CHARS[1],
            news=PUBLIC_NEWS_LIMIT,
        ),
    )


def _size(obj) -> int:
    return len(prompt_message(obj))


def _extreme_route(graph: dict, pick, memory: int, rationale: int, news: int) -> Route:
    """Dynamic programming over the story, from the ending back. A prompt carries the
    Chapter Segment so far, so a scene costs its size once for every later call in its
    segment: each node keeps, per number of calls left in its segment, the best
    (characters, decisions, Memory Updates) from there to the ending."""
    nodes = graph["nodes"]
    rules = StoryRules(graph)
    remembered = "x" * memory
    headlines = ["x" * HEADLINE_MAX_CHARS] * news
    best: dict[str, dict[int, tuple[int, int, int]]] = {}

    def keep(table, calls, value):
        if calls not in table or pick(table[calls], value, key=lambda v: v[0]) is value:
            table[calls] = value

    def overall(table):
        return pick(table.values(), key=lambda v: v[0]) if table else (0, 0, 0)

    for node_id in _children_first(rules, nodes, graph["start"]):
        node, kind = nodes[node_id], nodes[node_id]["type"]
        table: dict[int, tuple[int, int, int]] = {}
        if kind == "chapter_exit":
            prompt = len(SYSTEM_PROMPT) + _size(
                memory_update_payload(
                    node.get("character"),
                    node.get("chapter"),
                    remembered,
                    [],
                    DEFAULT_MEMORY_MAX_CHARS,
                )
            )
            # The next segment's prompts don't carry this one.
            chars, decisions, updates = overall(best.get(node.get("next"), {}))
            table[1] = (prompt + chars, decisions, updates + 1)
        elif kind == "choice":
            prompt = len(SYSTEM_PROMPT) + _size(
                {
                    "current_scene": scene_view(node),
                    "chapter_briefing": chapter_briefing(graph, node.get("chapter")),
                    "news": headlines,
                    "character_memory": remembered,
                    "chapter_segment_so_far": [],
                    "goal": DEFAULT_GOAL,
                    "available_choices": [
                        {"id": o["id"], "label": o["label"]} for o in node["options"]
                    ],
                }
            )
            # A Joint Decision also carries the other deciders' memories.
            prompt += len(remembered) * (len(node.get("deciders") or [None]) - 1)
            for option in node["options"]:
                # The choice joins the segment every later prompt in it carries,
                # with any Gauge Feedback it caused.
                moment = {
                    "at": node.get("heading"),
                    "your_choice": option["label"],
                    "rationale": "x" * rationale,
                }
                # Relationship arrows are shown by default, as in CLI and Visitor Runs.
                feedback = planned_feedback(graph, option)
                if feedback:
                    moment["on_screen"] = feedback
                chosen = 1 + _size(moment)
                for calls, (chars, decisions, updates) in best.get(
                    option.get("next"), {0: (0, 0, 0)}
                ).items():
                    keep(
                        table,
                        calls + 1,
                        (prompt + chars + chosen * calls, decisions + 1, updates),
                    )
        else:
            scene = 0
            if kind == "scene":
                scene = 1 + _size(scene_record(node))
            # A condition branch's Gauge Feedback joins the segment as its own entry.
            flashed = {}
            if kind == "condition":
                for branch in node.get("branches", []):
                    lines = planned_feedback(graph, branch)
                    if lines and branch.get("next"):
                        entry = 1 + _size({"at": node.get("heading"), "on_screen": lines})
                        flashed[branch["next"]] = max(flashed.get(branch["next"], 0), entry)
            for child in rules.successors(node_id) or [None]:
                cost = scene + flashed.get(child, 0)
                for calls, (chars, decisions, updates) in best.get(
                    child, {0: (0, 0, 0)}
                ).items():
                    keep(table, calls, (chars + cost * calls, decisions, updates))
        best[node_id] = table
    return Route(*overall(best[graph["start"]]))


def _children_first(rules: StoryRules, nodes: dict, start: str) -> list[str]:
    """Every node reachable from ``start``, each after all the nodes it leads to (the
    story graph has no cycles)."""
    order, seen = [], {start}
    stack = [(start, iter(rules.successors(start)))]
    while stack:
        node_id, children = stack[-1]
        for child in children:
            if child in nodes and child not in seen:
                seen.add(child)
                stack.append((child, iter(rules.successors(child))))
                break
        else:
            order.append(node_id)
            stack.pop()
    return order
