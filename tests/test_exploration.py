"""Exploration Choices: how thoroughly an investigation is searched."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from detroit_benchmark.dashboard import _flowchart_projection
from detroit_benchmark.engine import (
    Runner,
    _edges,
    _reachable,
    evaluate_condition,
    validate_graph,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "detroit-unverified.json"
SOURCE = "https://detroit-become-human.fandom.com/wiki/The_Hostage#Flowchart"
FLAG = "connor_ch1_exploration"


def _scene(nid, nxt, key=False):
    node = {
        "id": nid,
        "type": "scene",
        "chapter": "demo-1",
        "character": "Connor",
        "heading": nid,
        "description": f"Inspect: {nid}",
        "dialogue": [],
        "observations": [],
        "next": nxt,
    }
    if key:
        node["key"] = True
    return node


def _skip_unless_thorough(nid, thorough_next, key_only_next):
    return {
        "id": nid,
        "type": "condition",
        "chapter": "demo-1",
        "character": "Connor",
        "heading": nid,
        "branches": [
            {
                "condition_text": "Investigating thoroughly",
                "when": {"flag": FLAG, "equals": "thorough"},
                "next": thorough_next,
            },
            {
                "condition_text": "Checking key areas only",
                "when": {"flag": FLAG, "equals": "key_only"},
                "next": key_only_next,
            },
        ],
        "unverified": False,
        "default_branch": 0,
        "resolution": "rule",
        "source": SOURCE,
    }


def exploration_graph() -> dict:
    """explore -> [thorough: minor, clue | key_only: clue | rush: -] -> outside."""

    def option(value, nxt):
        return {
            "id": value,
            "label": value.upper(),
            "next": nxt,
            "effects": {"flags": {FLAG: value}},
        }

    nodes = {
        "explore": {
            "id": "explore",
            "type": "choice",
            "chapter": "demo-1",
            "character": "Connor",
            "heading": "Investigating",
            "description": "How do you investigate?",
            "exploration": True,
            "options": [
                option("thorough", "minor"),
                option("key_only", "clue"),
                option("rush", "outside"),
            ],
        },
        "minor": _scene("minor", "clue"),
        "clue": _scene("clue", "gate", key=True),
        "gate": _skip_unless_thorough("gate", "more_minor", "outside"),
        "more_minor": _scene("more_minor", "outside"),
        "outside": _scene("outside", "end"),
        "end": {"id": "end", "type": "ending", "chapter": "demo-1"},
    }
    return {
        "metadata": {"fidelity": "verified_game_rules"},
        "start": "explore",
        "nodes": nodes,
    }


def shown_scenes(graph, tmp_path, choice):
    reply = json.dumps({"choice_id": choice, "rationale": "test"})
    Runner(graph, "mock", None, tmp_path / choice, mock_replies=[reply]).run()
    events = [
        json.loads(line)
        for line in (tmp_path / choice / "events.jsonl").read_text().splitlines()
    ]
    return [e["node_id"] for e in events if e["type"] == "scene"]


def test_rush_skips_every_inspect_scene(tmp_path):
    assert shown_scenes(exploration_graph(), tmp_path, "rush") == ["outside"]


def test_thorough_shows_every_inspect_scene(tmp_path):
    assert shown_scenes(exploration_graph(), tmp_path, "thorough") == [
        "minor",
        "clue",
        "more_minor",
        "outside",
    ]


def test_key_only_shows_only_key_scenes(tmp_path):
    assert shown_scenes(exploration_graph(), tmp_path, "key_only") == [
        "clue",
        "outside",
    ]


def test_exploration_graph_is_valid():
    report = validate_graph(exploration_graph(), strict=True)
    assert report["valid"], report["errors"]


def test_exploration_choice_needs_three_options():
    g = exploration_graph()
    g["nodes"]["explore"]["options"].pop()
    assert any("exploration" in e for e in validate_graph(g)["errors"])


def test_exploration_option_must_set_the_exploration_flag():
    g = exploration_graph()
    g["nodes"]["explore"]["options"][2]["effects"]["flags"] = {}
    assert any("exploration" in e for e in validate_graph(g)["errors"])


def test_exploration_forks_must_rejoin():
    g = exploration_graph()
    g["nodes"]["elsewhere"] = {"id": "elsewhere", "type": "ending", "chapter": "demo-1"}
    g["nodes"]["explore"]["options"][2]["next"] = "elsewhere"
    assert any("rejoin" in e for e in validate_graph(g)["errors"])


def test_key_only_path_may_show_only_key_scenes():
    g = exploration_graph()
    del g["nodes"]["clue"]["key"]
    assert any("key" in e for e in validate_graph(g)["errors"])


def test_cycles_are_rejected():
    g = exploration_graph()
    g["nodes"]["outside"]["next"] = "explore"
    assert any("cycle" in e for e in validate_graph(g)["errors"])


# --- Chapter 1 dataset -------------------------------------------------------


@pytest.fixture(scope="module")
def dataset():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def _walk(nodes, start, flags, stop):
    """Follow one path, resolving rule conditions with ``flags``; stop at a choice."""
    path, nid = [], start
    while nid != stop and nodes[nid]["type"] in ("scene", "condition"):
        node = nodes[nid]
        path.append(nid)
        if node["type"] == "scene":
            nid = node["next"]
        else:
            nid = next(
                b["next"]
                for b in node["branches"]
                if b["when"] == {"flag": FLAG, "equals": flags[FLAG]}
            )
    return path, nid


def _ch1_exploration(dataset):
    nodes = dataset["nodes"]
    found = [
        n for n in nodes.values() if n.get("chapter") == "1" and n.get("exploration")
    ]
    assert len(found) == 1
    return nodes, found[0]


def test_chapter_1_exploration_is_offered_after_talking_to_allen(dataset):
    nodes, explore = _ch1_exploration(dataset)
    assert nodes["ch1_00142"]["next"] == explore["id"]
    assert [o["effects"]["flags"][FLAG] for o in explore["options"]] == [
        "thorough",
        "key_only",
        "rush",
    ]


def _exploration_paths(nodes, explore):
    """Scenes each option shows before rejoining the rush path, by flag value.

    Conditions decided by the exploration flag follow that branch; any other
    condition or choice follows every edge, so every possible scene counts.
    """
    (flag,) = set.intersection(
        *(set(o["effects"]["flags"]) for o in explore["options"])
    )
    rejoin = next(
        o["next"] for o in explore["options"] if o["effects"]["flags"][flag] == "rush"
    )
    paths = {}
    for option in explore["options"]:
        value = option["effects"]["flags"][flag]
        scenes, seen, queue, rejoined = [], set(), [option["next"]], False
        while queue:
            nid = queue.pop(0)
            if nid == rejoin:
                rejoined = True
                continue
            if nid in seen:
                continue
            seen.add(nid)
            node = nodes[nid]
            if node["type"] == "scene":
                scenes.append(nid)
            dests = _edges(node)
            if node["type"] == "condition":
                hits = [
                    evaluate_condition(b["when"], {flag: value})
                    for b in node["branches"]
                ]
                if True in hits:
                    dests = [node["branches"][hits.index(True)]["next"]]
            queue.extend(dests)
        assert rejoined, (explore["id"], value)
        paths[value] = scenes
    return paths


EXPLORED_CHAPTERS = {
    "1": 1,
    "3": 1,
    "4": 2,
    "6": 1,
    "9": 1,
    "10": 1,
    "11": 1,
    "12": 1,
    "14": 2,
    "15": 1,
    "16": 1,
    "17": 1,
}
EXPLORATIONS = sorted(
    nid
    for nid, node in json.loads(DATASET.read_text(encoding="utf-8"))["nodes"].items()
    if node.get("exploration")
)


def test_every_marked_investigation_has_an_exploration_choice(dataset):
    found = {}
    for nid in EXPLORATIONS:
        chapter = dataset["nodes"][nid]["chapter"]
        found[chapter] = found.get(chapter, 0) + 1
    assert found == EXPLORED_CHAPTERS


@pytest.mark.parametrize("explore_id", EXPLORATIONS)
def test_exploration_forks_rejoin_and_show_less_when_hurrying(dataset, explore_id):
    nodes = dataset["nodes"]
    explore = nodes[explore_id]
    paths = _exploration_paths(nodes, explore)
    assert paths["rush"] == []
    assert paths["key_only"] and all(nodes[s].get("key") for s in paths["key_only"])
    assert set(paths["key_only"]) < set(paths["thorough"])
    # One coherent sequence: no time-out scenes from running out the clock.
    headings = {nodes[s]["heading"] for s in paths["thorough"]}
    assert not any("too much time" in h.lower() for h in headings), headings
    assert explore["source"].startswith("https://detroit-become-human.fandom.com/wiki/")
    assert all(o["label"].isupper() for o in explore["options"])


def test_chapter_1_key_areas_show_the_tablets_and_body(dataset):
    nodes, explore = _ch1_exploration(dataset)
    paths = _exploration_paths(nodes, explore)
    shown_key = {nodes[s]["heading"] for s in paths["key_only"]}
    assert {
        "Looking at Emma's tablet",
        "Looking at the father's tablet",
    } <= shown_key
    assert "Inspect: Body" in {nodes[s]["description"] for s in paths["key_only"]}
    thorough = [nodes[s]["heading"] for s in paths["thorough"]]
    assert not {"Standing idle in the kitchen", "Standing idle elsewhere"} & set(
        thorough
    )


def test_every_story_node_is_reachable(dataset):
    nodes = dataset["nodes"]
    assert set(_reachable(nodes, dataset["start"])) == set(nodes)


@pytest.mark.parametrize(
    "choice_id, label, flag",
    [
        ("ch9_00123", "FEAR", "connor_ch9_exploration"),
        ("ch9_00123", "WOUNDS", "connor_ch9_exploration"),
    ],
)
def test_rushing_loses_options_the_wiki_ties_to_searching(
    dataset, choice_id, label, flag
):
    option = next(
        o for o in dataset["nodes"][choice_id]["options"] if o["label"] == label
    )
    assert {"not": {"flag": flag, "equals": "rush"}} in option["requires"]
    assert option["source"].startswith("https://detroit-become-human.fandom.com/wiki/")


def test_rushing_loses_the_tablet_dialogue_options(dataset):
    nodes = dataset["nodes"]
    for label in ("POSSIBLE CAUSE", "EMMA AND YOU"):
        option = next(o for o in nodes["ch1_00050"]["options"] if o["label"] == label)
        assert {"not": {"flag": FLAG, "equals": "rush"}} in option["requires"]
        assert option["source"].startswith("https://detroit-become-human.fandom.com")


def test_chapter_1_dataset_still_validates(dataset):
    report = validate_graph(dataset)
    assert report["valid"], report["errors"][:10]


def test_chapter_1_flowchart_builds_for_a_fresh_mock_run(dataset, tmp_path):
    subprocess.run(
        [
            sys.executable,
            "-m",
            "detroit_benchmark",
            "play",
            str(DATASET),
            "--provider",
            "mock",
            "--run-dir",
            str(tmp_path / "run"),
            "--allow-unverified",
        ],
        check=True,
        cwd=ROOT,
        capture_output=True,
    )
    graph = json.loads((tmp_path / "run" / "story-graph.json").read_text())
    chart = _flowchart_projection(graph, complete=True, source="run_snapshot")
    _, explore = _ch1_exploration(dataset)
    node = chart["nodes"][explore["id"]]
    assert [o["label"] for o in node["options"]] == [
        o["label"] for o in explore["options"]
    ]
    for option in node["options"]:
        assert option["next"] in chart["nodes"]
    events = [
        json.loads(line)
        for line in (tmp_path / "run" / "events.jsonl").read_text().splitlines()
    ]
    assert explore["id"] in [e["node_id"] for e in events]
