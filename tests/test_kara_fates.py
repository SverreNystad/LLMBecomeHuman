"""Kara's and Alice's Fates in Crossroads (30.1) and Kara Captured (32.2) (#39)."""

import pytest

from tests.dataset import load_dataset, play_story

KARA_LATER = {"32.1", "32.2"}
# Crossroads: Kara flees for the breach.
SHOT_AT, SHOT_IN_THE_LEG, LEG_AGAIN = "ch30_1_00055", "ch30_1_00038", "ch30_1_00015"
SOLDIERS_CLOSE_IN, AFTER_SURRENDER = "ch30_1_00005", "ch30_1_00052"
LUTHER_SACRIFICES = "ch30_1_00018"
KARA_SHOT_IN_THE_LEG = "ch30_1_00039"
RETURNING_TO_ALICE, ALICE_GONE = "ch30_1_00131", "ch30_1_x0103"
LUTHER_DIES_AT_THE_RANCH = {"ch25_x0001": "WAIT FOR ROSE", "ch25_00076": "UPSTAIRS"}


def test_crawling_with_a_shot_leg_kara_and_alice_die(tmp_path):
    run = play_story(
        tmp_path, {SHOT_AT: "RUN", SHOT_IN_THE_LEG: "GET UP", LEG_AGAIN: "CRAWL"}
    )
    assert run.flags["kara_alive"] is False
    assert run.flags["alice_alive"] is False
    assert not KARA_LATER & set(run.chapters)


def test_defending_alice_luther_sacrifices_himself_and_they_escape(tmp_path):
    run = play_story(tmp_path, {SHOT_AT: "PLAY DEAD", SOLDIERS_CLOSE_IN: "DEFEND ALICE"})
    assert LUTHER_SACRIFICES in run.nodes
    assert run.flags["luther_alive"] is False
    assert "32.1" in run.chapters


def test_defending_alice_without_luther_kara_and_alice_die(tmp_path):
    run = play_story(
        tmp_path,
        {**LUTHER_DIES_AT_THE_RANCH, SHOT_AT: "PLAY DEAD", SOLDIERS_CLOSE_IN: "DEFEND ALICE"},
    )
    assert run.flags["kara_alive"] is False
    assert run.flags["alice_alive"] is False
    assert not KARA_LATER & set(run.chapters)


def test_running_after_surrendering_kara_is_shot_in_the_leg(tmp_path):
    run = play_story(tmp_path, {SHOT_AT: "SURRENDER", AFTER_SURRENDER: "RUN"})
    assert KARA_SHOT_IN_THE_LEG in run.nodes


def test_staying_distant_alice_leaves_and_kara_can_run_alone(tmp_path):
    run = play_story(tmp_path, {RETURNING_TO_ALICE: "DISTANT", ALICE_GONE: "RUN AWAY"})
    assert run.flags["kara_alive"] is True
    assert not KARA_LATER & set(run.chapters)


def test_staying_distant_kara_can_go_back_for_alice(tmp_path):
    run = play_story(tmp_path, {RETURNING_TO_ALICE: "DISTANT", ALICE_GONE: "FIND ALICE"})
    assert KARA_LATER & set(run.chapters)


# Kara Captured
CAPTURED = {SHOT_AT: "SURRENDER", AFTER_SURRENDER: "OBEY"}
FENCE = "ch32_2_00030"
PANIC = "ch32_2_00053"
TALK_TO_LUTHER = "ch32_2_00039"
LANDFILL_HUG = "ch32_2_00004"
FREED_BY_MARKUS, RECYCLED = "ch32_2_00007", "ch32_2_00009"
REVOLUTION = {"ch31_1_00006": "REVOLUTION"}


def test_fleeing_over_the_barbed_wire_the_soldier_shoots_them(tmp_path):
    run = play_story(tmp_path, {**CAPTURED, FENCE: "FLEE"})
    assert "32.2" in run.chapters
    assert run.flags["kara_alive"] is False
    assert run.flags["alice_alive"] is False
    assert LANDFILL_HUG not in run.nodes


def test_fighting_the_soldier_kara_and_alice_escape_on_a_truck(tmp_path):
    run = play_story(tmp_path, {**CAPTURED, FENCE: "PROTECT ALICE"})
    assert LANDFILL_HUG in run.nodes
    assert run.flags["kara_alive"] is True
    assert run.flags["alice_alive"] is True


@pytest.mark.parametrize("revolution", [True, False])
def test_only_markus_revolution_frees_the_camp(tmp_path, revolution):
    picks = {**CAPTURED, FENCE: "WAIT"} | (REVOLUTION if revolution else {})
    run = play_story(tmp_path, picks)
    assert (FREED_BY_MARKUS in run.nodes, RECYCLED in run.nodes) == (
        revolution,
        not revolution,
    )
    assert run.flags["kara_alive"] is revolution
    assert LANDFILL_HUG not in run.nodes


def test_alice_never_panics_because_quick_time_events_succeed(tmp_path):
    run = play_story(tmp_path, CAPTURED)
    assert PANIC not in run.nodes


@pytest.mark.parametrize("luther_dead", [True, False])
def test_a_dead_luther_never_appears_in_the_camp(tmp_path, luther_dead):
    picks = {**CAPTURED, FENCE: "WAIT"} | (LUTHER_DIES_AT_THE_RANCH if luther_dead else {})
    run = play_story(tmp_path, picks)
    assert "32.2" in run.chapters
    assert (TALK_TO_LUTHER in run.nodes) is not luther_dead


def test_kara_captured_options_are_not_engine_strings():
    labels = [o["label"] for o in load_dataset()["nodes"][FENCE]["options"]]
    assert labels == ["FLEE", "PROTECT ALICE", "WAIT"]
