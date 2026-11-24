"""Ending Summary sentences say what happened and where, from the Run's recorded route."""

import pytest
from dataset import load_dataset

from detroit_benchmark.ending import ENDINGS, ending_summary

NODES = load_dataset()["nodes"]
WHO = {"Connor": 0, "Kara": 1, "Markus": 2}


def _chose(node, label):
    return {"type": "decision", "node_id": node, "label": label}


def _branch(node, index):
    return {"type": "condition", "node_id": node, "branch_index": index}


def _scene(node):
    return {"type": "scene", "node_id": node}


def _sentence(name, flags, *events):
    summary = ending_summary(flags, list(events), [], finished=True)
    return summary["characters"][WHO[name]]["sentence"]


def _event(row):
    node, choice = row.key
    if choice is None:
        return _scene(node)
    return _chose(node, choice) if isinstance(choice, str) else _branch(node, choice)


BOTH_DEAD = {"kara_alive": False, "alice_alive": False, "kara_story_ended": True}
BOTH_ALIVE = {"kara_alive": True, "alice_alive": True}
ALICE_ONLY = {"kara_alive": False, "alice_alive": True}
KARA_ONLY = {"kara_alive": True, "alice_alive": False}


@pytest.mark.parametrize(
    ("flags", "events", "sentence"),
    [
        (
            {"alice_alive": False, "kara_story_ended": True},
            [_scene("ch7_x0001")],
            "Kara obeyed Todd, and he beat Alice to death. Her story ended there.",
        ),
        (
            BOTH_DEAD,
            [_chose("ch32_1_00209", "PAPERS"), _scene("ch32_1_x0105")],
            "Soldiers at the bus terminal saw through Kara's papers and executed her and Alice.",
        ),
        (
            BOTH_DEAD,
            [_scene("ch32_1_x0102")],
            "Soldiers stopped Kara and Alice and executed them.",
        ),
        (
            BOTH_DEAD,
            [_scene("ch32_1_x0106")],
            "Kara surrendered to the coastguard, who fired on the boat and killed her and Alice.",
        ),
        (
            ALICE_ONLY,
            [_chose("ch32_1_00067", "SACRIFICE SELF"), _scene("ch32_1_00008")],
            (
                "Kara gave her life at the border so that Alice could cross."
                " Alice went on with Rose."
            ),
        ),
        (
            BOTH_ALIVE,
            [_chose("ch32_1_00067", "SACRIFICE JERRY"), _scene("ch32_1_00010")],
            "Jerry gave his life at the border so that Kara and Alice could cross.",
        ),
        (
            BOTH_ALIVE,
            [_chose("ch32_1_00167", "Use Luther"), _branch("ch32_1_00130", 3)],
            (
                "Luther died covering their crossing."
                " Kara and Alice crossed the river into Canada."
            ),
        ),
        (
            ALICE_ONLY,
            [_scene("ch32_2_x0224")],
            "Kara was shot escaping the camp, but Luther got Alice out on a truck.",
        ),
        (
            {**BOTH_DEAD, "kara_awaiting_markus": "together"},
            [_scene("ch32_2_x0216"), _scene("ch32_9_x0005")],
            "Nobody freed the camp, and Kara and Alice died in the recycling machine.",
        ),
        (
            {"kara_alive": True, "kara_left_alone": True, "alice_alive": True},
            [_scene("ch30_1_x0106")],
            "Kara fled Jericho alone and left Alice behind. Alice is alive.",
        ),
    ],
)
def test_kara_s_sentence_says_what_happened_and_where(flags, events, sentence):
    assert _sentence("Kara", flags, *events) == sentence


@pytest.mark.parametrize(
    ("flags", "events", "sentence"),
    [
        (
            {"markus_alive": False},
            [_chose("ch28_00009", "SHOOT")],
            "Markus died during the freedom march.",
        ),
        (
            {"markus_peaceful": True, "markus_alive": False},
            [_branch("ch32_5_00022", 0), _scene("ch32_3_x0103")],
            "Markus's demonstration won, but Connor shot him during his speech.",
        ),
        (
            {"markus_peaceful": False, "markus_alive": False},
            [_chose("ch32_6_00026", "SHOOT"), _scene("ch32_6_x0142")],
            "Markus's assault failed, and Connor shot him.",
        ),
        (
            {"markus_peaceful": False, "markus_alive": True},
            [_chose("ch32_6_00026", "SPARE"), _scene("ch32_6_x0142")],
            "Markus's assault failed. Connor spared him.",
        ),
        (
            {"markus_peaceful": False, "markus_alive": False},
            [_chose("ch32_6_00019", "SURRENDER")],
            "Markus's assault failed. He surrendered and did not survive.",
        ),
    ],
)
def test_markus_s_sentence_says_what_happened_and_where(flags, events, sentence):
    assert _sentence("Markus", flags, *events) == sentence


@pytest.mark.parametrize(
    ("flags", "events", "sentence"),
    [
        (
            {"connor_deviant": True, "connor_deaths": 0, "connor_story_ended": True},
            [_scene("ch32_4_x0102")],
            "Connor became deviant. CyberLife security shot him in the tower elevator.",
        ),
        (
            {
                "connor_deviant": True,
                "connor_deaths": 2,
                "connor_androids_woke": True,
            },
            [_chose("ch32_4_00042", "COLE"), _scene("ch32_7_00034")],
            (
                "Connor became deviant. He died twice. He woke the androids at CyberLife Tower"
                " and broke free of Amanda's control."
            ),
        ),
        (
            # The roof death came first; killing Markus is the latest decisive event.
            {"connor_deviant": False, "connor_deaths": 1, "markus_alive": False},
            [_branch("ch32_3_x0105", 0), _scene("ch32_6_x0120")],
            (
                "Connor stayed a machine. He died once."
                " He killed Markus and stopped the revolution."
            ),
        ),
    ],
)
def test_connor_s_sentence_says_how_his_story_ended(flags, events, sentence):
    assert _sentence("Connor", flags, *events) == sentence


def test_waking_the_androids_is_told_once():
    summary = ending_summary(
        {"connor_deviant": True, "connor_androids_woke": True, "markus_peaceful": True},
        [_chose("ch32_4_00042", "COLE")],
        [],
        finished=True,
    )
    told = summary["characters"][0]["sentence"] + summary["world"]["sentence"]
    assert told.count("woke the androids") == 1


@pytest.mark.parametrize(
    "flags",
    [{"kara_alive": True, "alice_alive": True}, {"kara_alive": False}, {}],
)
def test_a_route_the_recorded_fates_contradict_or_omit_is_not_told(flags):
    assert "coastguard" not in _sentence("Kara", flags, _scene("ch32_1_x0106"))


def test_every_ending_is_a_moment_of_the_story():
    for rows in ENDINGS.values():
        for row in rows:
            for node, choice in filter(None, (row.key, row.after)):
                entry = NODES[node]
                if isinstance(choice, str):
                    assert choice in [o["label"] for o in entry["options"]], node
                elif choice is not None:
                    assert 0 <= choice < len(entry["branches"]), node
                else:
                    assert entry["type"] in ("scene", "condition"), node


def test_every_ending_is_told_by_the_event_and_outcomes_it_names():
    for name, rows in ENDINGS.items():
        for row in rows:
            events = [_event(row)]
            if row.after:
                node, choice = row.after
                events.insert(0, _chose(node, choice))
            assert row.text in _sentence(name, dict(row.needs), *events), row.key
