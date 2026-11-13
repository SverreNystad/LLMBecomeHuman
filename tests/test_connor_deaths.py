"""Connor's Deaths (GLOSSARY.md): every way Connor can die adds one, and the lines
that depend on it follow what happened (issue #41)."""

import pytest

from tests.dataset import load_dataset, play_story

# The Hostage
CONNOR_SHOT_DANIEL, DANIEL_SHOT_CONNOR = "ch1_x0101", "ch1_x0102"
DIED_PROTECTING_EMMA = "ch1_x0103"
FINAL_PLEA = "ch1_00009"
EXECUTE = {"ch1_00016": "EXECUTE"}
# The Interrogation: leaving the deviant to self-destruct (no death).
LET_IT_SELF_DESTRUCT = {"ch9_00008": "GIVE UP"}
# The Bridge
HOSTILE_HANK = {"ch6_00134": "FIRM", "ch15_00018": "Chase Deviant"}
HANK_SHOT_CONNOR = "ch22_x0101"
WHY_DID_YOU_SHOOT_ME, COIN = "ch24_00149", "ch24_00151"
HE_SHOT_ME_IN_THE_HEAD, PROBLEMATIC = "ch24_00173", "ch24_00175"
# Lines that depend on Connor's Deaths.
PREVIOUS_CONNOR = "ch12_00201"  # Amanda: pick up where the previous Connor left off
YOU_WOULD_COME_BACK = "ch22_00023"  # Hank: you'd just come back
I_REMEMBER_YOU, YOU_MUST_BE_MISTAKEN = "ch24_00092", "ch24_00094"
EVERY_TIME_YOU_DIED = "ch31_2_00036"


def test_shooting_daniel_plays_the_shot_and_never_negotiates_again(tmp_path):
    run = play_story(tmp_path, EXECUTE)
    assert CONNOR_SHOT_DANIEL in run.nodes
    assert FINAL_PLEA not in run.nodes
    assert run.flags["connor_died_in_hostage"] is False


def test_persuading_daniel_at_gunpoint_gets_connor_shot(tmp_path):
    run = play_story(tmp_path, {"ch1_00016": "INTIMIDATE", "ch1_00013": "CONVINCE"})
    assert DANIEL_SHOT_CONNOR in run.nodes
    assert FINAL_PLEA not in run.nodes
    assert run.flags["connor_died_in_hostage"] is True


def test_sacrificing_himself_connor_dies_protecting_emma(tmp_path):
    run = play_story(tmp_path, {"ch1_00019": "SACRIFICE SELF"})
    assert DIED_PROTECTING_EMMA in run.nodes
    assert FINAL_PLEA not in run.nodes
    assert run.flags["connor_died_in_hostage"] is True


def test_a_connor_who_never_died_is_remembered_as_alive(tmp_path):
    run = play_story(tmp_path, {**EXECUTE, **LET_IT_SELF_DESTRUCT})
    assert PREVIOUS_CONNOR not in run.nodes
    assert YOU_WOULD_COME_BACK not in run.nodes
    assert I_REMEMBER_YOU in run.nodes and YOU_MUST_BE_MISTAKEN not in run.nodes


def test_a_connor_who_died_twice_is_remembered_by_amanda_hank_and_the_cop(tmp_path):
    # Shot by Daniel in The Hostage, then by the deviant in The Interrogation. Only a
    # machine Connor whose Hank quit the force visits Hank in Night of the Soul.
    machine = {"ch30_2_00097": "REMAIN A MACHINE", "ch30_2_00124": "REMAIN A MACHINE"}
    run = play_story(
        tmp_path,
        {"ch1_00016": "INTIMIDATE", "ch1_00013": "CONVINCE", **machine, **HOSTILE_HANK},
    )
    assert {PREVIOUS_CONNOR, YOU_WOULD_COME_BACK, YOU_MUST_BE_MISTAKEN} <= set(
        run.nodes
    )
    assert EVERY_TIME_YOU_DIED in run.nodes


def test_each_way_connor_dies_adds_one(tmp_path):
    never = play_story(tmp_path / "a", {**EXECUTE, **LET_IT_SELF_DESTRUCT})
    hostage = play_story(tmp_path / "b", {**LET_IT_SELF_DESTRUCT})
    both = play_story(tmp_path / "c", {})
    saving_hank = play_story(
        tmp_path / "d",
        {**EXECUTE, **LET_IT_SELF_DESTRUCT, "ch24_00031": "SAVE HANK"},
    )
    base = never.flags["connor_deaths"]
    assert hostage.flags["connor_deaths"] == base + 1
    assert both.flags["connor_deaths"] == base + 2
    assert saving_hank.flags["connor_deaths"] == base + 1


@pytest.mark.parametrize("hostile", [True, False])
def test_a_hostile_hank_shoots_connor_on_the_bridge(tmp_path, hostile):
    picks = {**EXECUTE, **LET_IT_SELF_DESTRUCT} | (HOSTILE_HANK if hostile else {})
    run = play_story(tmp_path, picks)
    assert (HANK_SHOT_CONNOR in run.nodes) is hostile
    assert (WHY_DID_YOU_SHOOT_ME in run.nodes, COIN in run.nodes) == (
        hostile,
        not hostile,
    )
    assert (HE_SHOT_ME_IN_THE_HEAD in run.nodes) is hostile
    assert (PROBLEMATIC in run.nodes) is not hostile


DEATH_LINES = [
    "ch12_00203",
    "ch22_00024",
    "ch24_00097",
    "ch29_00206",
    "ch31_2_00038",
    "ch32_3_00030",
    "ch32_3_00058",
    "ch22_00004",
    "ch24_00152",
    "ch24_00176",
]


@pytest.mark.parametrize("nid", DEATH_LINES)
def test_lines_about_connors_deaths_follow_a_rule(nid):
    node = load_dataset()["nodes"][nid]
    assert node["resolution"] == "rule"
