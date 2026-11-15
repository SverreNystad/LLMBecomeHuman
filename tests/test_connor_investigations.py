"""Connor's investigations can fail, and later chapters follow what happened (#42)."""

import pytest

from tests.dataset import load_dataset, play_story

# Partners: reporting to Hank. The correct reconstruction is: it started in the
# kitchen, with the bat, the android stabbed the victim, who fled to the living
# room, and the android killed him with the knife.
WHERE, WEAPON, WHAT, FLED, KILLED = (
    "ch6_00050",
    "ch6_00042",
    "ch6_00037",
    "ch6_00031",
    "ch6_00025",
)
CORRECT = {
    WHERE: "…IN THE KITCHEN",
    WEAPON: "…WITH THE BAT.",
    WHAT: "THE ANDROID STABBED THE VICTIM.",
    FLED: "… THE LIVING ROOM.",
    KILLED: "…WITH THE KNIFE",
}
CRIME_UNSOLVED, SEARCH_THE_ATTIC = "ch6_x0101", "ch6_00006"
TOO_MANY_WRONG_ANSWERS = "ch6_00011"
INTERROGATION = "9"
# Amanda in chapter 12.
DISAPPOINTED, DEBRIEF = "ch12_00220", "ch12_00228"
CONTINUE_INVESTIGATION = "ch12_00202"
# Amanda in chapter 18: "Two investigations, two failures…"
TWO_FAILURES, ONE_FAILURE = "ch18_00091", "ch18_00092"


def test_a_correct_reconstruction_finds_the_deviant(tmp_path):
    run = play_story(tmp_path, CORRECT)
    assert SEARCH_THE_ATTIC in run.nodes
    assert not {CRIME_UNSOLVED, TOO_MANY_WRONG_ANSWERS} & set(run.nodes)
    assert INTERROGATION in run.chapters
    assert DEBRIEF in run.nodes and DISAPPOINTED not in run.nodes


def test_hank_forgives_a_first_wrong_guess_about_where_it_started(tmp_path):
    run = play_story(tmp_path, {**CORRECT, WHERE: "…IN THE BATHROOM"})
    assert SEARCH_THE_ATTIC in run.nodes


@pytest.mark.parametrize(
    "wrong", [{KILLED: "…WITH THE BAT."}, {WHAT: "THE ANDROID THREW THE CHAIR."}]
)
def test_wrong_answers_leave_the_crime_unsolved(tmp_path, wrong):
    run = play_story(tmp_path, {**CORRECT, **wrong})
    assert CRIME_UNSOLVED in run.nodes
    assert SEARCH_THE_ATTIC not in run.nodes
    # The suspect was never found, so there is no interrogation.
    assert INTERROGATION not in run.chapters
    assert DISAPPOINTED in run.nodes
    assert DEBRIEF not in run.nodes
    assert CONTINUE_INVESTIGATION in run.nodes


@pytest.mark.parametrize("found", [True, False])
def test_amanda_in_russian_roulette_remembers_partners(tmp_path, found):
    wrong = {} if found else {KILLED: "…WITH THE BAT."}
    # Saving Hank on the roof in The Nest, Connor lets Rupert get away.
    run = play_story(tmp_path, {**CORRECT, **wrong, "ch15_00018": "Save Hank"})
    assert (TWO_FAILURES in run.nodes) is not found
    assert (ONE_FAILURE in run.nodes) is found


# Waiting for Hank: Hank's lead depends on whether Kara died in Stormy Night.
HANKS_LEAD_KARA_ALIVE, HANKS_LEAD_KARA_DEAD = "ch12_00005", "ch12_00007"


@pytest.mark.parametrize("kara_dies", [True, False])
def test_hanks_lead_follows_whether_kara_died(tmp_path, kara_dies):
    picks = {"ch7_00092": "STAND STILL"} if kara_dies else {}
    run = play_story(tmp_path, picks)
    assert (HANKS_LEAD_KARA_DEAD in run.nodes) is kara_dies
    assert (HANKS_LEAD_KARA_ALIVE in run.nodes) is not kara_dies


# On the Run: Connor at the squat.
SQUAT = {"ch10_00109": "DON'T STEAL", "ch10_00039": "STAY"}
SEARCH_SQUAT = "ch13_x0101"
PURSUIT = "ch13_00009"
KARA_UNDISCOVERED = "ch13_00083"


def test_at_the_squat_connor_can_leave_without_finding_kara(tmp_path):
    run = play_story(tmp_path, {**SQUAT, SEARCH_SQUAT: "LEAVE"})
    assert KARA_UNDISCOVERED in run.nodes
    assert PURSUIT not in run.nodes
    assert run.flags["connor_highway_pursuit"] is False


def test_searching_under_the_stairs_connor_finds_kara_and_pursues(tmp_path):
    run = play_story(tmp_path, {**SQUAT, SEARCH_SQUAT: "CHECK UNDER THE STAIRS"})
    assert PURSUIT in run.nodes
    assert KARA_UNDISCOVERED not in run.nodes


def test_a_threatened_ralph_informs_and_connor_pursues(tmp_path):
    run = play_story(tmp_path, {**SQUAT, "ch13_00136": "THREATEN"})
    assert SEARCH_SQUAT not in run.nodes
    assert PURSUIT in run.nodes
    assert KARA_UNDISCOVERED not in run.nodes


@pytest.mark.parametrize(
    "nid",
    ["ch12_00241", "ch12_00008", "ch18_00093", "ch12_00203", "ch12_00127", "ch12_00153"],
)
def test_lines_about_partners_and_kara_follow_a_rule(nid):
    assert load_dataset()["nodes"][nid]["resolution"] == "rule"
