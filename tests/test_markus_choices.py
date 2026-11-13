"""Markus's early choices are real choices, and his missions can fail (#44)."""

import pytest

from tests.dataset import play_story

# The Painter
COPY, THEME = "ch5_x0101", "ch5_x0102"
PIANO_MOOD = "ch5_x0106"


def test_markus_chooses_what_to_paint(tmp_path):
    run = play_story(
        tmp_path, {COPY: "COPY THE STATUE", THEME: "IDENTITY", "ch5_x0105": "DOUBTS"}
    )
    assert run.offered(COPY) == ["COPY CARL'S PAINTING", "COPY THE DESK", "COPY THE STATUE"]
    assert run.flags["markus_painting_copy"] == "statue"
    assert run.flags["markus_painting_theme"] == "identity"
    assert run.flags["markus_painting_subject"] == "doubts"


def test_playing_the_piano_markus_chooses_a_mood(tmp_path):
    run = play_story(tmp_path, {"ch5_00077": "PLAY THE PIANO", PIANO_MOOD: "HOPEFUL"})
    assert run.flags["markus_piano_mood"] == "hopeful"


# Spare Parts: the truck, full bags, or failure.
TRUCK, FULL_BAGS, RAN, FAILED = "ch19_00007", "ch19_00010", "ch19_00013", "ch19_00021"
GUARD = "ch19_00108"
JOHN_JOINS, KEY, METHOD = "ch19_00081", "ch19_00065", "ch19_00050"


@pytest.mark.parametrize(
    "picks, outcome",
    [
        ({METHOD: "CREATE A BLACKOUT"}, TRUCK),
        ({METHOD: "THREATEN THE GUARDS"}, TRUCK),
        ({KEY: "LEAVE"}, FULL_BAGS),
        ({JOHN_JOINS: "REFUSE"}, FULL_BAGS),
        ({GUARD: "Run away"}, RAN),
    ],
    ids=["blackout", "threaten", "no-key", "no-john", "ran"],
)
def test_spare_parts_ends_the_way_the_choices_led(tmp_path, picks, outcome):
    run = play_story(tmp_path, picks)
    ends = {TRUCK, FULL_BAGS, RAN, FAILED}
    assert ends & set(run.nodes) == {outcome}
    assert METHOD not in run.nodes or "CREATE A BLACKOUT" in run.offered(METHOD)


# Capitol Park
SECURE = "ch26_x0101"
MISSION_FAILED, ALL_TEAMS_SUCCEEDED = "ch26_00006", "ch26_00007"
WE_FAILED = "ch26_00092"
CONVERT, POLICE_CAR = "ch26_00090", "ch26_00146"
MESSAGE = "ch26_00075"
DID_NOTHING = "ch26_00054"


def test_securing_the_store_converts_the_androids_without_failing(tmp_path):
    run = play_story(tmp_path, {SECURE: "SECURE THE AREA FIRST", POLICE_CAR: "HIDE"})
    assert CONVERT in run.nodes
    assert not {WE_FAILED, MISSION_FAILED} & set(run.nodes)


@pytest.mark.parametrize(
    "picks",
    [{SECURE: "RAM THE STORE NOW"}, {SECURE: "SECURE THE AREA FIRST", POLICE_CAR: "Abandon Mission"}],
    ids=["ram", "abandon"],
)
def test_capitol_park_can_fail_and_then_nobody_is_converted(tmp_path, picks):
    run = play_story(tmp_path, picks)
    assert MISSION_FAILED in run.nodes
    assert CONVERT not in run.nodes
    assert MESSAGE not in run.nodes


def test_the_message_is_markus_choice(tmp_path):
    picks = {SECURE: "SECURE THE AREA FIRST", POLICE_CAR: "HIDE"}
    tag = play_story(tmp_path / "a", {**picks, MESSAGE: "TAG THE STATUE"})
    assert tag.flags["markus_capitol_park_statue"] == "tagged"
    nothing = play_story(tmp_path / "b", {**picks, MESSAGE: "DO NOTHING"})
    assert DID_NOTHING in nothing.nodes
    assert "ch26_00070" not in nothing.nodes  # no Molotov offered


# Freedom March
REFUSE_DEAL = {"ch32_5_00076": "REFUSE DEAL"}  # Markus survives Battle for Detroit
POLICE_BLOCK, FIRST_FIRE = "ch28_00044", "ch28_00035"
FIGHT, SACRIFICE_GATE, RUN = "ch28_00013", "ch28_00027", "ch28_00029"
JOHN_SAVES, SIMON_SAVES, MARKUS_SHOT = "ch28_00021", "ch28_00023", "ch28_00026"


@pytest.mark.parametrize(
    "picks",
    [
        {POLICE_BLOCK: "STAND GROUND", FIRST_FIRE: "ATTACK"},
        {POLICE_BLOCK: "STAND GROUND", FIRST_FIRE: "STAND GROUND", "ch28_00030": "CHARGE"},
        {POLICE_BLOCK: "DISPERSE", "ch28_00041": "CHARGE"},
    ],
    ids=["attack", "charge-under-fire", "charge-after-leaving"],
)
def test_charging_the_police_is_a_fight(tmp_path, picks):
    run = play_story(tmp_path, picks)
    assert FIGHT in run.nodes
    assert run.flags["markus_march_violent"] is True


@pytest.mark.parametrize(
    "picks, saved_by, markus_alive",
    [
        ({JOHN_JOINS: "ACCEPT", KEY: "GET THE KEY"}, JOHN_SAVES, True),
        ({JOHN_JOINS: "REFUSE"}, SIMON_SAVES, True),
    ],
    ids=["john", "simon"],
)
def test_sacrificing_himself_someone_dies_for_markus(tmp_path, picks, saved_by, markus_alive):
    run = play_story(
        tmp_path,
        {**picks, POLICE_BLOCK: "DISPERSE", "ch28_00041": "STAY", **REFUSE_DEAL},
    )
    assert SACRIFICE_GATE in run.nodes
    assert saved_by in run.nodes
    assert run.flags["markus_alive"] is markus_alive


def test_with_nobody_to_save_him_markus_is_shot(tmp_path):
    simon_left_on_the_roof = {
        "ch23_00077": "SPARE",
        "ch23_00043": "Help",
        "ch23_00033": "LEAVE",
    }
    run = play_story(
        tmp_path,
        {
            JOHN_JOINS: "REFUSE",
            **simon_left_on_the_roof,
            POLICE_BLOCK: "STAND GROUND",
            FIRST_FIRE: "STAND GROUND",
            "ch28_00030": "SACRIFICE",
        },
    )
    assert MARKUS_SHOT in run.nodes
    assert run.flags["markus_alive"] is False


def test_running_away_from_the_police_markus_flees(tmp_path):
    run = play_story(tmp_path, {POLICE_BLOCK: "DISPERSE", "ch28_00041": "DISPERSE"})
    assert RUN in run.nodes
    assert run.flags["markus_march_fled"] is True
