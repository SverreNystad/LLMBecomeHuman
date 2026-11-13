"""Kara Leaving Detroit (32.1) plays one route, and every death sets the Fates (#46)."""

import pytest

from tests.dataset import load_dataset, play_story

TICKETS = "ch32_1_00270"
TODD_APPROACH = "ch32_1_00253"
NO_TODD = "ch32_1_x0104"
SECURITY = "ch32_1_00209"
COASTGUARD, OTHER_SIDE = "ch32_1_00167", "ch32_1_00119"
BORDER_LINE = "ch32_1_00067"
AT_THE_BORDER, AT_THE_RIVER = "ch32_1_00113", "ch32_1_00205"
TODD = "ch32_1_00256"
KILLED_TODD = {"ch7_00092": "TALK TO TODD"}  # Kara takes the gun; Todd is shot
RIVER = {TICKETS: "RETURN TICKETS", TODD_APPROACH: "YOUR STORY"}
REVOLUTION = {"ch31_1_00006": "REVOLUTION"}
# The family asks again after the first refusal; keeping them both times.
KEEP = {TICKETS: "KEEP TICKETS", "ch32_1_00266": "KEEP TICKETS"}


def test_keeping_the_tickets_kara_takes_the_bus_to_the_border(tmp_path):
    run = play_story(tmp_path, KEEP)
    assert AT_THE_BORDER in run.nodes
    assert AT_THE_RIVER not in run.nodes
    assert TODD not in run.nodes


def test_with_adams_help_kara_crosses_the_river_and_never_the_border(tmp_path):
    run = play_story(tmp_path, RIVER)
    assert AT_THE_RIVER in run.nodes
    assert AT_THE_BORDER not in run.nodes


def test_failing_to_persuade_todd_without_luther_the_soldiers_execute_them(tmp_path):
    run = play_story(tmp_path, {TICKETS: "RETURN TICKETS", TODD_APPROACH: "APPEAL"})
    assert run.flags["kara_alive"] is False
    assert run.flags["alice_alive"] is False
    assert AT_THE_RIVER not in run.nodes and AT_THE_BORDER not in run.nodes


def test_persuading_todd_needs_alices_box(tmp_path):
    rushed = {"ch4_x0003": "TIDY UP", TICKETS: "RETURN TICKETS"}
    run = play_story(tmp_path, rushed)
    assert "YOUR STORY" not in run.offered(TODD_APPROACH)


def test_a_todd_that_kara_shot_never_comes_back(tmp_path):
    run = play_story(tmp_path, {**KILLED_TODD, TICKETS: "RETURN TICKETS"})
    assert TODD not in run.nodes
    assert NO_TODD in run.nodes


@pytest.mark.parametrize("label", ["FLEE", "PAPERS"])
def test_at_the_security_check_fleeing_or_handing_over_id_is_fatal(tmp_path, label):
    run = play_story(
        tmp_path,
        {**KILLED_TODD, TICKETS: "RETURN TICKETS", NO_TODD: "WAIT FOR ANOTHER BUS", SECURITY: label},
    )
    assert run.flags["kara_alive"] is False
    assert AT_THE_RIVER not in run.nodes


def test_surrendering_to_the_coastguard_the_group_dies(tmp_path):
    run = play_story(tmp_path, {**RIVER, COASTGUARD: "Surrender"})
    assert run.flags["kara_alive"] is False
    assert run.flags["alice_alive"] is False
    assert "t(CommonTranslationKey.DefaultChoice)" not in run.offered(COASTGUARD)


@pytest.mark.parametrize(
    "label, kara, alice", [("KEEP LIVING", True, False), ("GIVE UP", False, False)]
)
def test_when_alice_shuts_down_kara_lives_on_or_gives_up(tmp_path, label, kara, alice):
    run = play_story(tmp_path, {**RIVER, COASTGUARD: "Accelerate", OTHER_SIDE: label})
    assert (run.flags["kara_alive"], run.flags["alice_alive"]) == (kara, alice)
    assert AT_THE_BORDER not in run.nodes


@pytest.mark.parametrize("revolution", [True, False])
def test_with_no_sacrifice_the_border_guard_judges_by_markus(tmp_path, revolution):
    picks = {**KEEP, BORDER_LINE: "NO SACRIFICE"}
    run = play_story(tmp_path, picks | (REVOLUTION if revolution else {}))
    assert run.flags["kara_alive"] is not revolution
    assert run.flags["alice_alive"] is not revolution


def test_sacrificing_herself_kara_dies_and_alice_crosses(tmp_path):
    run = play_story(tmp_path, {**KEEP, BORDER_LINE: "SACRIFICE SELF"})
    assert run.flags["kara_alive"] is False
    assert run.flags["alice_alive"] is True


def test_hiding_behind_luther_needs_luther():
    options = {o["label"]: o for o in load_dataset()["nodes"][COASTGUARD]["options"]}
    assert options["Use Luther"]["requires"] == [{"flag": "luther_alive", "equals": True}]
    assert options["Hide"]["requires"] == [{"flag": "luther_alive", "equals": False}]
