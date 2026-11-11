"""Condition resolution: Quick-Time Events, rules over earlier choices, unknowns."""

import itertools
import json
from pathlib import Path

import pytest

from detroit_benchmark.engine import Runner, evaluate_condition, validate_graph


def _scene(nid, nxt):
    return {
        "id": nid,
        "type": "scene",
        "chapter": "demo-1",
        "character": "Connor",
        "heading": nid,
        "description": f"{nid} happens.",
        "dialogue": [],
        "observations": [],
        "next": nxt,
    }


def tiny_graph(condition: dict, flag_options: list[dict] | None = None) -> dict:
    """start -> [choice] -> gate -> one of a/b -> end."""
    nodes = {
        "a": _scene("a", "end"),
        "b": _scene("b", "end"),
        "end": {"id": "end", "type": "ending", "chapter": "demo-1"},
        "gate": {
            "id": "gate",
            "type": "condition",
            "chapter": "demo-1",
            "character": "Connor",
            "heading": "Gate",
            **condition,
        },
    }
    start = "gate"
    if flag_options:
        nodes["pick"] = {
            "id": "pick",
            "type": "choice",
            "chapter": "demo-1",
            "character": "Connor",
            "heading": "Pick",
            "description": "Pick one.",
            "options": [{**o, "next": "gate", "label": o["id"]} for o in flag_options],
        }
        start = "pick"
    return {
        "metadata": {"fidelity": "verified_game_rules"},
        "start": start,
        "nodes": nodes,
    }


def play(g, tmp_path, **kw):
    result = Runner(g, "mock", None, tmp_path / "run", **kw).run()
    events = [
        json.loads(line)
        for line in (tmp_path / "run" / "events.jsonl").read_text().splitlines()
    ]
    return result, events


def visited(events):
    return [e["node_id"] for e in events]


def test_quick_time_event_always_takes_success_branch(tmp_path):
    g = tiny_graph(
        {
            "resolution": "qte",
            "unverified": True,
            "default_branch": 1,
            "branches": [
                {"condition_text": "Connor fails", "when": None, "next": "a"},
                {"condition_text": "Connor succeeds", "when": None, "next": "b"},
            ],
        }
    )
    result, events = play(g, tmp_path)
    assert "b" in visited(events) and "a" not in visited(events)
    gate = next(e for e in events if e["node_id"] == "gate")
    assert gate["quick_time_event"] == "success"
    assert gate["used_unverified_default"] is False
    assert result["warnings"] == []


RULE = {
    "resolution": "rule",
    "source": "https://detroit-become-human.fandom.com/wiki/Example#Choices",
    "unverified": False,
    "default_branch": 0,
    "branches": [
        {
            "condition_text": "Connor sacrificed himself",
            "when": {"flag": "connor_sacrificed", "equals": True},
            "next": "a",
        },
        {
            "condition_text": "Connor stayed back",
            "when": {"flag": "connor_sacrificed", "equals": False},
            "next": "b",
        },
    ],
}


def test_rule_follows_earlier_choice_not_default(tmp_path):
    # The mock model takes the first listed option: staying back.
    g = tiny_graph(
        RULE,
        [
            {"id": "stay", "effects": {"flags": {"connor_sacrificed": False}}},
            {"id": "jump", "effects": {"flags": {"connor_sacrificed": True}}},
        ],
    )
    result, events = play(g, tmp_path)
    assert "b" in visited(events) and "a" not in visited(events)
    assert result["warnings"] == []


def test_rule_needs_source_and_when_on_every_branch():
    no_source = {k: v for k, v in RULE.items() if k != "source"}
    assert not validate_graph(tiny_graph(no_source))["valid"]
    half = {
        **RULE,
        "branches": [RULE["branches"][0], {**RULE["branches"][1], "when": None}],
    }
    assert not validate_graph(tiny_graph(half))["valid"]
    assert validate_graph(tiny_graph(RULE))["valid"]


def test_unknown_resolution_value_is_rejected():
    assert not validate_graph(tiny_graph({**RULE, "resolution": "maybe"}))["valid"]


def test_rule_with_flag_missing_falls_back_to_default_with_warning(tmp_path):
    # No earlier choice set the flag (e.g. it was decided at an unknown node).
    result, events = play(tiny_graph(RULE), tmp_path, allow_unverified=True)
    assert "a" in visited(events)
    gate = next(e for e in events if e["node_id"] == "gate")
    assert gate["used_unverified_default"] is True
    assert result["warnings"][0]["node"] == "gate"


DATASET = Path(__file__).resolve().parents[1] / "data" / "detroit-unverified.json"
SORTED_CHAPTERS = [str(i) for i in range(1, 23)]


@pytest.mark.parametrize("chapter", SORTED_CHAPTERS)
def test_dataset_conditions_are_sorted(chapter):
    nodes = json.loads(DATASET.read_text(encoding="utf-8"))["nodes"]
    sorted_nodes = [
        n
        for n in nodes.values()
        if n["type"] == "condition" and n.get("chapter") == chapter
    ]
    for n in sorted_nodes:
        assert n.get("resolution") in ("qte", "rule", "unknown"), n["id"]
        if n["resolution"] == "rule":
            assert n.get("source", "").startswith("https://"), n["id"]
            assert all(b["when"] is not None for b in n["branches"]), n["id"]
        if n["resolution"] == "qte":
            assert 0 <= n["default_branch"] < len(n["branches"]), n["id"]


def test_dataset_rule_flags_are_set_by_some_choice():
    nodes = json.loads(DATASET.read_text(encoding="utf-8"))["nodes"]
    set_by_choices = {
        name
        for n in nodes.values()
        if n["type"] == "choice"
        for o in n["options"]
        for name in (o.get("effects") or {}).get("flags", {})
    }

    def flags_in(expr):
        if "flag" in expr:
            return {expr["flag"]}
        inner = expr.get("all") or expr.get("any") or [expr["not"]]
        return set().union(*(flags_in(x) for x in inner))

    for n in nodes.values():
        if n.get("resolution") == "rule":
            for b in n["branches"]:
                assert flags_in(b["when"]) <= set_by_choices, n["id"]


def test_dataset_rule_branches_never_overlap():
    # The engine refuses a condition where two branches match at once.
    nodes = json.loads(DATASET.read_text(encoding="utf-8"))["nodes"]
    values = {}
    for n in nodes.values():
        for o in n.get("options", []):
            for name, value in (o.get("effects") or {}).get("flags", {}).items():
                values.setdefault(name, []).append(value)

    def flags_in(expr):
        if "flag" in expr:
            return {expr["flag"]}
        inner = expr.get("all") or expr.get("any") or [expr["not"]]
        return set().union(*(flags_in(x) for x in inner))

    for n in nodes.values():
        if n.get("resolution") != "rule":
            continue
        names = sorted(set().union(*(flags_in(b["when"]) for b in n["branches"])))
        for combo in itertools.product(*(set(values[f]) for f in names)):
            flags = dict(zip(names, combo))
            hits = [evaluate_condition(b["when"], flags) for b in n["branches"]]
            assert hits.count(True) <= 1, (n["id"], flags)


def test_unknown_condition_keeps_default_and_warns(tmp_path):
    unknown = {
        "resolution": "unknown",
        "unverified": True,
        "default_branch": 0,
        "branches": [
            {"condition_text": "x", "when": None, "next": "a"},
            {"condition_text": "y", "when": None, "next": "b"},
        ],
    }
    assert validate_graph(tiny_graph(unknown))["warnings"]
    result, events = play(tiny_graph(unknown), tmp_path, allow_unverified=True)
    assert "a" in visited(events)
    assert result["warnings"][0]["problem"].startswith("Unverified condition")
