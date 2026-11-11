"""Condition resolution: Quick-Time Events, rules over earlier choices, unknowns."""

import itertools
import json
import re

import pytest

from detroit_benchmark.engine import (
    ModelDecision,
    Runner,
    _reachable,
    evaluate_condition,
    validate_graph,
)
from tests.dataset import load_dataset


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


FAILURE_ONLY_QTE = {
    "resolution": "qte",
    "unverified": True,
    "default_branch": None,
    "branches": [{"condition_text": "Connor is caught", "when": None, "next": "a"}],
    "next": "b",
}


def test_quick_time_event_with_only_a_failure_branch_falls_through(tmp_path):
    g = tiny_graph(FAILURE_ONLY_QTE)
    assert validate_graph(g)["valid"]
    result, events = play(g, tmp_path)
    assert "b" in visited(events) and "a" not in visited(events)
    gate = next(e for e in events if e["node_id"] == "gate")
    assert gate["quick_time_event"] == "success"
    assert result["warnings"] == []


def test_failure_only_quick_time_event_needs_a_fall_through():
    g = tiny_graph({**FAILURE_ONLY_QTE, "next": None})
    assert any("success" in e for e in validate_graph(g)["errors"])


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


WIKI = "https://detroit-become-human.fandom.com/wiki/"
SORTED_CHAPTERS = [str(i) for i in range(1, 30)] + [
    "30.1",
    "30.2",
    "30.3",
    "31.1",
    "31.2",
    "32.1",
    "32.2",
    "32.3",
    "32.4",
    "32.5",
    "32.6",
]


@pytest.mark.parametrize("chapter", SORTED_CHAPTERS)
def test_dataset_conditions_are_sorted(chapter):
    nodes = load_dataset()["nodes"]
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
        if n["resolution"] == "qte" and n["default_branch"] is None:
            assert n["next"] in nodes, n["id"]
        elif n["resolution"] == "qte":
            assert 0 <= n["default_branch"] < len(n["branches"]), n["id"]


def test_dataset_rule_flags_are_set_by_some_choice():
    nodes = load_dataset()["nodes"]
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
    nodes = load_dataset()["nodes"]
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


_dataset = load_dataset


# Quick-Time Events that are really a decision between two courses of action:
# the model chooses, and each option leads where the old branch did.
DECISIONS = {
    "ch23_00103": {"ch23_00099", "ch23_00102"},  # which guard Markus shoots
    "ch30_2_00048": {"ch30_2_00047", "ch30_2_00046"},  # help the chased androids
    "ch30_3_00083": {"ch30_3_00082", "ch30_3_00080"},  # help the chased androids
}


@pytest.mark.parametrize("nid", sorted(DECISIONS))
def test_dataset_decisions_are_choices_not_quick_time_events(nid):
    node = _dataset()["nodes"][nid]
    assert node["type"] == "choice"
    assert {o["next"] for o in node["options"]} == DECISIONS[nid]
    for option in node["options"]:
        assert option["label"].isupper(), option["label"]
        assert option["effects"]["flags"], option["id"]
    assert len({o["id"] for o in node["options"]}) == len(node["options"])


FAILURE = re.compile(
    r"\b(dies|die|died|dead|fail|fails|failed|lose|lost|destroyed|caught|"
    r"too much time|get shot|gets hit|shot twice|wrong way)\b",
    re.IGNORECASE,
)
# Outcome checks whose success is the outcome of an earlier Quick-Time Event
# (always a success), checked against the wiki; and The Hostage's leap, where
# succeeding means Connor reaches Emma in time and falls to his death.
SUCCESS = {
    "ch1_00005": "reaches Emma in time",
    "ch12_00008": "Kara didn't die",
    "ch13_00063": "Kara shot Todd",
    "ch15_00189": "arrive together",
}


def test_dataset_quick_time_events_default_to_their_success():
    for nid, node in _dataset()["nodes"].items():
        if node.get("resolution") != "qte" or node["default_branch"] is None:
            continue
        texts = [b["condition_text"] for b in node["branches"]]
        success = texts[node["default_branch"]]
        if nid in SUCCESS:
            assert SUCCESS[nid] in success, nid
            assert node["source"].startswith(WIKI), nid
        elif not all(FAILURE.search(t) for t in texts):
            assert not FAILURE.search(success), (nid, success)


def test_dataset_public_enemy_shows_the_guard_markus_shot():
    nodes = _dataset()["nodes"]
    gate = nodes["ch24_00102"]
    assert gate["resolution"] == "rule"
    chose = {
        o["next"]: o["effects"]["flags"]["markus_stratford_guard_shot_first"]
        for o in nodes["ch23_00103"]["options"]
    }
    bodies = {b["next"]: b["when"]["equals"] for b in gate["branches"]}
    # Shooting the guard drawing his weapon leaves Chris Robert's body;
    # shooting the guard on the phone leaves Sean Chedd's.
    assert chose == {"ch23_00099": "weapon", "ch23_00102": "phone"}
    assert bodies == {"ch24_00101": "weapon", "ch24_00100": "phone"}


@pytest.mark.parametrize("pushed_leo", [True, False])
def test_dataset_night_of_the_soul_plays_one_carl_scene(pushed_leo):
    graph = _dataset()
    nodes = graph["nodes"]
    entry = graph["chapter_entries"]["31.1"]
    seen = _reachable(nodes, entry, {"markus_pushed_leo": pushed_leo})
    headings = {nodes[n].get("heading") for n in seen if nodes[n]["chapter"] == "31.1"}
    assert ("Carl is still alive" in headings) is pushed_leo
    assert ("Carl died in Broken" in headings) is not pushed_leo
    assert "Speak to androids" in headings


def test_dataset_metadata_counts_unverified_conditions():
    graph = _dataset()
    unknown = sum(
        n["type"] == "condition" and n.get("resolution") == "unknown"
        for n in graph["nodes"].values()
    )
    assert graph["metadata"]["condition_nodes_unverified"] == unknown


class _ScriptedRunner(Runner):
    """Mock player that picks a named option at given choice nodes, else the first."""

    def __init__(self, *args, picks: dict, **kwargs):
        self.picks = picks
        super().__init__(*args, **kwargs)

    def _model_response(self, payload, options):
        wanted = self.picks.get(self.state["node"])
        pick = next((o for o in options if o["label"] == wanted), options[0])
        return ModelDecision(choice_id=pick["id"], rationale="Scripted."), {}


def _play_story(tmp_path, picks):
    """Play the whole real story; return the headings seen per chapter."""
    run = _ScriptedRunner(
        _dataset(), "mock", None, tmp_path / "run", allow_unverified=True, picks=picks
    )
    run.run()
    seen = {}
    for line in (tmp_path / "run" / "events.jsonl").read_text().splitlines():
        event = json.loads(line)
        if event["type"] == "scene":
            heading = event["visible_to_agent"]["heading"]
            seen.setdefault(str(event.get("chapter")), set()).add(heading)
    assert run.state["status"] == "complete"
    return seen


MOTEL, SQUAT, CAR = "In the room", "Talk to Ralph", "Looking at the car"
MORNING = {
    "motel": "Kara stayed at the Motel",
    "squat": "Kara stayed at the Squat",
    "car": "Kara stayed at the Parking lot",
}
SHELTERS = {
    # The first options steal clothes and money, so the motel gives them a room.
    "motel": ({}, MOTEL),
    "squat": ({"ch10_00109": "DON'T STEAL", "ch10_00039": "STAY"}, SQUAT),
    "car": (
        {
            "ch10_00109": "DON'T STEAL",
            "ch10_00039": "LEAVE",
            "ch10_00013": "STAY HERE",
        },
        CAR,
    ),
}


@pytest.mark.parametrize("shelter", sorted(SHELTERS))
def test_kara_spends_one_night_in_one_shelter_and_wakes_up_there(tmp_path, shelter):
    picks, night = SHELTERS[shelter]
    seen = _play_story(tmp_path, picks)
    nights = {MOTEL, SQUAT, CAR} & seen["10"]
    assert nights == {night}
    mornings = set(MORNING.values()) & seen["13"]
    assert mornings == {MORNING[shelter]}


def test_shelter_choices_record_where_kara_slept():
    nodes = _dataset()["nodes"]
    recorded = {
        (nid, o["label"]): o["effects"]["flags"].get("kara_ch10_shelter")
        for nid in ("ch10_00039", "ch10_00013")
        for o in nodes[nid]["options"]
    }
    assert recorded[("ch10_00039", "STAY")] == "squat"
    assert recorded[("ch10_00013", "STAY HERE")] == "car"
    gate = nodes[_dataset()["chapter_entries"]["13"]]
    assert gate["resolution"] == "rule"
    assert gate["source"].startswith(WIKI)


KARA_LATER = {"10", "13", "17", "21", "25", "30.1", "32.1", "32.2"}


def test_kara_standing_still_lets_todd_kill_alice_and_ends_her_story(tmp_path):
    seen = _play_story(tmp_path, {"ch7_00092": "STAND STILL"})
    assert not KARA_LATER & set(seen)
    assert "Talking with Kara" not in seen["31.1"] | seen.get("31.2", set())
    # Connor's and Markus's stories go on without her.
    assert {"11", "12", "14", "32.3", "32.4"} & set(seen)


def test_kara_acting_after_breaking_her_programming_keeps_her_story(tmp_path):
    seen = _play_story(tmp_path, {"ch7_00092": "GO UPSTAIRS"})
    assert {"10", "13", "17"} <= set(seen)


def test_breaking_programming_is_not_a_choice_but_standing_still_is():
    nodes = _dataset()["nodes"]
    assert nodes["ch7_00097"]["resolution"] == "qte"
    after = nodes["ch7_00092"]
    assert after["type"] == "choice"
    labels = {o["label"]: o for o in after["options"]}
    assert set(labels) == {"STAND STILL", "TALK TO TODD", "GO UPSTAIRS"}
    assert labels["STAND STILL"]["effects"]["flags"]["kara_story_ended"] is True
