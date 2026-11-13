"""Kara's early choices are real choices, gated on what she found (#43)."""

import pytest

from tests.dataset import play_story

RUSH_UPSTAIRS = {"ch4_x0003": "MOVE THROUGH QUICKLY"}  # never cleans Todd's room
TIDY_UPSTAIRS = {"ch4_x0003": "TIDY UP"}  # sees the gun, doesn't air Alice's room

# Stormy Night: locked in Alice's room.
LOCK_ROOM = {"ch7_00033": "LOCK ROOM"}
LOCKED_IN = "ch7_x0101"
WINDOW = "ch7_00017"
TAKE_GUN = "ch7_00076"
AFTER_TODD = {"ch7_00092": "TALK TO TODD"}


@pytest.mark.parametrize(
    "upstairs, window", [({}, True), (TIDY_UPSTAIRS, False), (RUSH_UPSTAIRS, False)]
)
def test_the_window_is_a_way_out_only_if_kara_found_it(tmp_path, upstairs, window):
    run = play_story(tmp_path, {**upstairs, **LOCK_ROOM, LOCKED_IN: "OPEN WINDOW"})
    assert ("OPEN WINDOW" in run.offered(LOCKED_IN)) is window
    assert "TALK TO ALICE" in run.offered(LOCKED_IN)
    assert (WINDOW in run.nodes) is window


@pytest.mark.parametrize("upstairs, gun", [({}, True), (RUSH_UPSTAIRS, False)])
def test_kara_can_take_the_gun_only_if_she_saw_it(tmp_path, upstairs, gun):
    run = play_story(tmp_path, {**upstairs, **AFTER_TODD})
    assert ("TAKE THE GUN" in run.offered(TAKE_GUN)) is gun
    assert run.flags["kara_took_gun"] is gun


def test_waiting_in_alices_room_is_a_choice_not_a_timeout(tmp_path):
    run = play_story(tmp_path, {})
    assert "OUT OF TIME" not in run.offered("ch7_00033")
    assert "WAIT" in run.offered("ch7_00033")


# Fugitives: the store. The first options take Kara to the store.
STORE = "ch10_00188"
DIVERSION = "ch10_00187"
NO_GUN = {**RUSH_UPSTAIRS, **AFTER_TODD}


def test_without_the_gun_kara_uses_alice_as_a_diversion(tmp_path):
    run = play_story(tmp_path, NO_GUN)
    assert run.offered(STORE) == ["USE ALICE AS A DIVERSION"]
    assert DIVERSION in run.nodes


def test_with_the_gun_robbing_the_store_is_a_choice(tmp_path):
    run = play_story(tmp_path, {**AFTER_TODD, STORE: "USE ALICE AS A DIVERSION"})
    assert set(run.offered(STORE)) == {
        "THREATEN THE CLERK WITH THE GUN",
        "USE ALICE AS A DIVERSION",
    }
    assert DIVERSION in run.nodes


# On the Run: changing appearance in each shelter.
SHELTERS = {
    "motel": ({}, "ch13_x0201"),
    "squat": ({"ch10_00109": "DON'T STEAL", "ch10_00039": "STAY"}, "ch13_x0211"),
    "car": (
        {"ch10_00109": "DON'T STEAL", "ch10_00039": "LEAVE", "ch10_00013": "STAY HERE"},
        "ch13_x0221",
    ),
}


@pytest.mark.parametrize("shelter", sorted(SHELTERS))
def test_kara_chooses_her_disguise(tmp_path, shelter):
    picks, hair = SHELTERS[shelter]
    run = play_story(tmp_path, {**picks, hair: "BLONDE"})
    assert set(run.offered(hair)) == {"BROWN", "BLACK", "WHITE", "BLONDE"}
    assert run.flags["kara_hair_color"] == "blonde"


def test_changing_clothes_in_the_squat_kara_can_forget_the_gun(tmp_path):
    picks, _ = SHELTERS["squat"]
    run = play_story(tmp_path, {**picks, "ch13_x0213": "FORGET THE GUN"})
    assert run.flags["kara_took_gun"] is False


# Zlatko
FREE, LEFT = "ch17_00005", "ch17_00006"
CELL, ESCAPE = "ch17_x0101", "ch17_00037"


@pytest.mark.parametrize("free", [True, False])
def test_freeing_zlatkos_androids_is_a_choice_that_comes_back(tmp_path, free):
    run = play_story(tmp_path, {CELL: "FREE THEM" if free else "LEAVE THEM"})
    assert (FREE in run.nodes, LEFT in run.nodes) == (free, not free)


@pytest.mark.parametrize("label, scene", [("SET FIRE", "ch17_00016"), ("HIDE", "ch17_00036")])
def test_kara_chooses_to_hide_or_set_fire(tmp_path, label, scene):
    run = play_story(tmp_path, {ESCAPE: label})
    assert scene in run.nodes
    assert {"SET FIRE", "HIDE"} == set(run.offered(ESCAPE))
