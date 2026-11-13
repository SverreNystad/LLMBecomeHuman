"""Night of the Soul (31.1, 31.2) plays only scenes that fit who is alive (#40)."""

import pytest

from tests.dataset import play_story

MACHINE = {"ch30_2_00097": "REMAIN A MACHINE", "ch30_2_00124": "REMAIN A MACHINE"}
SIMON_LEFT_ON_THE_ROOF = {
    "ch23_00077": "SPARE",
    "ch23_00043": "Help",
    "ch23_00033": "LEAVE",
}
NOBODY_SAVES_MARKUS = {
    "ch19_00081": "REFUSE",
    **SIMON_LEFT_ON_THE_ROOF,
    "ch28_00044": "STAND GROUND",
    "ch28_00035": "STAND GROUND",
    "ch28_00030": "SACRIFICE",
}
HOSTILE_HANK = {"ch6_00134": "FIRM", "ch15_00018": "Chase Deviant"}
NO_CLUES = {
    "ch27_00031": "DON'T SHOOT",
    "ch15_x0001": "CHECK KEY POINTS",
    "ch15_00018": "Save Hank",
    "ch20_00008": "SPARE",
    "ch20_00011": "SPARE",
    "ch24_00048": "PROBE MEMORY",
}
# 31.1 Markus
SIMON_TALKS, CONNOR_TRUST, CHURCH = "ch31_1_00059", "ch31_1_00041", "ch31_1_00062"
SPEECH = "ch31_1_00006"
# 31.2 Connor
AMANDA = ("ch31_2_00051", "ch31_2_00052")
HANKS_HOUSE, CONNOR_CHURCH = "ch31_2_00048", "ch31_2_00031"
NORTH_CALLS_MARKUS_DEAD = "ch31_2_00004"


def test_a_dead_simon_never_speaks(tmp_path):
    run = play_story(tmp_path, SIMON_LEFT_ON_THE_ROOF)
    assert CHURCH in run.nodes
    assert SIMON_TALKS not in run.nodes and "ch31_1_00061" not in run.nodes


def test_a_machine_connor_is_never_offered_trust(tmp_path):
    run = play_story(tmp_path, MACHINE)
    assert CONNOR_TRUST not in run.nodes


def test_with_markus_dead_north_calls_the_androids_to_arms(tmp_path):
    run = play_story(tmp_path, NOBODY_SAVES_MARKUS)
    assert "31.1" not in run.chapters
    assert not {"32.5", "32.6"} & set(run.chapters)
    assert CONNOR_CHURCH in run.nodes
    assert NORTH_CALLS_MARKUS_DEAD in run.nodes


def test_a_machine_connor_reports_to_amanda_not_to_the_church(tmp_path):
    run = play_story(tmp_path, {**MACHINE, **NOBODY_SAVES_MARKUS})
    assert set(AMANDA) & set(run.nodes)
    assert CONNOR_CHURCH not in run.nodes


def test_a_deviant_connor_meets_markus_in_his_own_segment(tmp_path):
    run = play_story(tmp_path, {})
    assert CONNOR_TRUST in run.nodes
    assert not set(AMANDA) & set(run.nodes)
    assert CONNOR_CHURCH not in run.nodes


@pytest.mark.parametrize("hostile", [True, False])
def test_hank_quits_and_kills_himself_only_if_hostile(tmp_path, hostile):
    picks = {**MACHINE} | (HOSTILE_HANK if hostile else {})
    run = play_story(tmp_path, picks)
    assert (HANKS_HOUSE in run.nodes) is hostile
    assert run.flags["hank_alive"] is not hostile


def test_without_a_raid_markus_speaks_to_the_people_not_in_the_church(tmp_path):
    run = play_story(tmp_path, NO_CLUES)
    assert CHURCH not in run.nodes
    assert SPEECH in run.nodes
