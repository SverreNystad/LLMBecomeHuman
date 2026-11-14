"""Crossroads at Jericho follows the wiki (#47).

Jericho is raided only if Connor found it in Last Chance, Connor; otherwise Kara,
Alice and Luther leave, and Markus stays alone with his thoughts. A voted-out Markus
chooses to leave forever or go back.
"""

import pytest

from tests.dataset import load_dataset, play_story

NO_CLUES = {
    "ch27_00031": "DON'T SHOOT",
    "ch15_x0001": "CHECK KEY POINTS",
    "ch15_00018": "Save Hank",
    "ch20_00008": "SPARE",
    "ch20_00011": "SPARE",
    "ch24_00048": "PROBE MEMORY",
}
KARA_ATTACKED, KARA_LEFT = "ch30_1_00126", "ch30_1_x0110"
CORRIDOR, MARKUS_ALONE = "ch30_3_00138", "ch30_3_x0106"
NORTH_CABIN, MARKUS_CABIN = "ch30_3_00160", "ch30_3_00229"
OUSTED, ROOFTOP, LEFT_JERICHO = "ch30_3_00208", "ch30_3_x0110", "ch30_3_x0108"
FLED_THE_MARCH = {"ch28_00044": "DISPERSE", "ch28_00041": "DISPERSE"}


@pytest.mark.parametrize("found", [True, False])
def test_jericho_is_raided_only_if_connor_found_it(tmp_path, found):
    run = play_story(tmp_path, {} if found else NO_CLUES)
    assert run.flags["connor_knows_jericho"] is found
    assert (KARA_ATTACKED in run.nodes, KARA_LEFT in run.nodes) == (found, not found)
    assert (CORRIDOR in run.nodes, MARKUS_ALONE in run.nodes) == (found, not found)


def test_with_markus_dead_north_holds_the_cabin(tmp_path):
    nobody_saves_markus = {
        "ch19_00081": "REFUSE",
        "ch23_00077": "SPARE",
        "ch23_00043": "Help",
        "ch23_00033": "LEAVE",
        "ch28_00044": "STAND GROUND",
        "ch28_00035": "STAND GROUND",
        "ch28_00030": "SACRIFICE",
    }
    run = play_story(tmp_path, nobody_saves_markus)
    assert NORTH_CABIN in run.nodes
    assert MARKUS_CABIN not in run.nodes
    assert CORRIDOR not in run.nodes


@pytest.mark.parametrize(
    "label, left", [("LEAVE FOREVER", True), ("GO BACK TO JERICHO", False)]
)
def test_a_voted_out_markus_chooses_to_leave_or_go_back(tmp_path, label, left):
    run = play_story(tmp_path, {**FLED_THE_MARCH, ROOFTOP: label})
    assert OUSTED in run.nodes
    assert NORTH_CABIN not in run.nodes
    assert run.flags["markus_left_jericho"] is left
    assert (CORRIDOR in run.nodes) is not left


def test_voted_out_without_a_raid_markus_simply_leaves(tmp_path):
    run = play_story(tmp_path, {**FLED_THE_MARCH, **NO_CLUES})
    assert LEFT_JERICHO in run.nodes
    assert ROOFTOP not in run.nodes
    assert run.flags["markus_left_jericho"] is True


def test_reaching_the_gun_stays_a_quick_time_event():
    # The player controls Markus in this struggle: a test of reflexes, not a decision.
    assert load_dataset()["nodes"]["ch30_2_00010"]["resolution"] == "qte"


# 30.2 Connor: one path per Run (the wiki's Crossroads flowchart).
MARKUS_CABIN_30_2, NORTH_CABIN_30_2 = "ch30_2_00149", "ch30_2_00117"
CARGO_HALL, DEVIANT_CORRIDOR = "ch30_2_00033", "ch30_2_00090"
CONNOR_ESCAPED = "ch30_2_x0103"
MACHINE_WITH_MARKUS = {"ch30_2_00124": "REMAIN A MACHINE"}
MARKUS_DIES_IN_THE_MARCH = {
    "ch19_00081": "REFUSE",
    "ch23_00077": "SPARE",
    "ch23_00043": "Help",
    "ch23_00033": "LEAVE",
    "ch28_00044": "STAND GROUND",
    "ch28_00035": "STAND GROUND",
    "ch28_00030": "SACRIFICE",
}


def test_a_deviant_connor_who_finds_markus_warns_him_and_lives(tmp_path):
    run = play_story(tmp_path, {})
    assert MARKUS_CABIN_30_2 in run.nodes
    assert not {NORTH_CABIN_30_2, CARGO_HALL, DEVIANT_CORRIDOR} & set(run.nodes)
    assert run.flags["connor_deviant"] is True
    assert run.flags["connor_died_in_crossroads"] is False


def test_with_markus_gone_a_deviant_connor_blows_up_jericho_and_escapes(tmp_path):
    run = play_story(tmp_path, MARKUS_DIES_IN_THE_MARCH)
    assert NORTH_CABIN_30_2 in run.nodes and DEVIANT_CORRIDOR in run.nodes
    assert not {MARKUS_CABIN_30_2, CARGO_HALL} & set(run.nodes)
    assert CONNOR_ESCAPED in run.nodes
    assert run.flags["connor_deviant"] is True
    assert run.flags["connor_died_in_crossroads"] is False


THIN_ICE = "ch31_2_00051"


@pytest.mark.parametrize("markus_here", [True, False])
def test_a_machine_connor_is_destroyed_in_the_hold(tmp_path, markus_here):
    picks = MACHINE_WITH_MARKUS if markus_here else {
        **MARKUS_DIES_IN_THE_MARCH,
        "ch30_2_00097": "REMAIN A MACHINE",
    }
    run = play_story(tmp_path / "machine", picks)
    deviant = play_story(tmp_path / "deviant", {} if markus_here else MARKUS_DIES_IN_THE_MARCH)
    assert CARGO_HALL in run.nodes and DEVIANT_CORRIDOR not in run.nodes
    assert run.flags["connor_died_in_crossroads"] is True
    assert run.flags["connor_deaths"] == deviant.flags["connor_deaths"] + 1
    assert THIN_ICE in run.nodes


def test_running_from_the_soldier_gets_connor_shot(tmp_path):
    run = play_story(tmp_path, {**MACHINE_WITH_MARKUS, "ch30_2_00029": "RUN"})
    assert run.flags["connor_died_in_crossroads"] is True
    assert "ch30_2_00019" not in run.nodes  # never reaches the hold
