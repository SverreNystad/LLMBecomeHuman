"""Markus's final Chapter Segments (32.5 Demonstration, 32.6 Revolution) play only the
version the choices led to, and every way Markus dies sets his Fate (issue #38)."""

import pytest

from tests.dataset import load_dataset, play_story

# 32.5: hearing Perkins out, then his deal.
GO_TALK, GO_TALK_AFTER_REFUSING = "ch32_5_00093", "ch32_5_00090"
DEAL = "ch32_5_00076"
DEAL_AFTER_QUESTION = "ch32_5_x0101"
I_NEED_TO_HEAR_HIM = "ch32_5_00087"
BARRICADE_ATTACKED = "ch32_5_00054"
RETURN_AFTER_REFUSING = "ch32_5_00061"
NORTH_SHOT = "ch32_5_00025"
PERKINS_SHOOTS_MARKUS = "ch32_5_x0105"
VICTORY_SPEECH = "ch32_5_00034"
NORTH_SAVES_MARKUS = "ch32_5_00048"
REFUSE_DEAL = {DEAL: "REFUSE DEAL"}
LEAVE_NORTH = {"ch30_3_00040": "RUN"}  # North is shot in Crossroads and left behind
# No Molotov in Capitol Park and no violence in the Freedom March: public opinion
# stays positive.
PEACEFUL = {
    "ch26_00070": "REFUSE",
    "ch28_00014": "DISPERSE",
    "ch28_00018": "ABANDON",
    "ch28_00030": "RUN AWAY",
    "ch28_00035": "DISPERSE",
    "ch28_00040": "RUN AWAY",
    "ch28_00041": "DISPERSE",
    "ch28_00044": "DISPERSE",
}

# 32.6: the revolution.
REVOLUTION = {"ch31_1_00006": "REVOLUTION"}
HEART = "ch32_6_00068"
NORTH_LEADS = "ch32_6_00010"
ASSAULT_SUCCESSFUL, ASSAULT_FAILED = "ch32_6_00049", "ch32_6_00038"
NOBODY_TO_SAVE_MARKUS = "ch32_6_x0111"

# 32.7 (ADR 0002): Connor's ending with Markus, or alone.
KAMSKI_WITH_MARKUS, KAMSKI_ALONE = "ch32_7_00030", "ch32_7_00031"


def test_hearing_perkins_out_changes_no_fate(tmp_path):
    run = play_story(tmp_path, {GO_TALK: "ACCEPT", **REFUSE_DEAL})
    assert I_NEED_TO_HEAR_HIM in run.nodes
    assert run.flags["markus_alive"] is True
    assert run.flags["north_alive"] is True
    assert KAMSKI_WITH_MARKUS in run.nodes


def test_refusing_twice_to_talk_goes_straight_to_the_attack(tmp_path):
    run = play_story(tmp_path, {GO_TALK: "REFUSE", GO_TALK_AFTER_REFUSING: "REFUSE"})
    assert I_NEED_TO_HEAR_HIM not in run.nodes
    assert DEAL not in run.nodes
    assert BARRICADE_ATTACKED in run.nodes


@pytest.mark.parametrize("north_alive", [True, False])
def test_accepting_perkins_deal_gets_markus_shot(tmp_path, north_alive):
    picks = {DEAL: "ACCEPT DEAL"} | ({} if north_alive else LEAVE_NORTH)
    run = play_story(tmp_path, picks)
    assert PERKINS_SHOOTS_MARKUS in run.nodes
    assert (NORTH_SHOT in run.nodes) is north_alive
    assert not {RETURN_AFTER_REFUSING, BARRICADE_ATTACKED, VICTORY_SPEECH} & set(
        run.nodes
    )
    assert run.flags["markus_alive"] is False
    assert run.flags["north_alive"] is False
    assert KAMSKI_ALONE in run.nodes and KAMSKI_WITH_MARKUS not in run.nodes


def test_a_question_to_perkins_is_not_a_refusal(tmp_path):
    run = play_story(
        tmp_path, {DEAL: "OTHER DEMONSTRATIONS", DEAL_AFTER_QUESTION: "ACCEPT DEAL"}
    )
    assert DEAL_AFTER_QUESTION in run.nodes
    assert RETURN_AFTER_REFUSING not in run.nodes
    assert run.flags["markus_alive"] is False


def test_a_failed_demonstration_has_no_victory_speech(tmp_path):
    # Sacrificing himself at the barricade: the soldiers fire.
    run = play_story(tmp_path, {**REFUSE_DEAL, "ch32_5_00045": "SACRIFICE"})
    assert VICTORY_SPEECH not in run.nodes
    assert run.flags["markus_alive"] is False
    # Quick-Time Events succeed: North never has to take a bullet for Markus.
    assert NORTH_SAVES_MARKUS not in run.nodes


def test_a_successful_demonstration_has_the_victory_speech(tmp_path):
    run = play_story(tmp_path, {**PEACEFUL, **REFUSE_DEAL, "ch32_5_00045": "SING"})
    assert VICTORY_SPEECH in run.nodes
    assert run.flags["markus_alive"] is True


def test_kissing_north_at_the_barricade_needs_her_alive_and_his_lover():
    kiss = next(
        o
        for o in load_dataset()["nodes"]["ch32_5_00045"]["options"]
        if o["label"] == "KISS NORTH"
    )
    assert {"flag": "north_alive", "equals": True} in kiss["requires"]
    assert {"flag": "markus_kissed_north", "equals": True} in kiss["requires"]


def test_a_successful_revolution_never_plays_the_failure(tmp_path):
    run = play_story(tmp_path, {**REVOLUTION, HEART: "SACRIFICE NORTH"})
    assert ASSAULT_SUCCESSFUL in run.nodes
    assert ASSAULT_FAILED not in run.nodes
    assert NORTH_LEADS not in run.nodes
    assert run.flags["markus_alive"] is True
    assert run.flags["north_alive"] is False
    assert KAMSKI_WITH_MARKUS in run.nodes


def test_refusing_north_s_heart_kills_markus_and_north_leads(tmp_path):
    run = play_story(tmp_path, {**REVOLUTION, HEART: "SACRIFICE SELF"})
    assert NORTH_LEADS in run.nodes
    assert ASSAULT_SUCCESSFUL not in run.nodes
    assert run.flags["markus_alive"] is False
    assert KAMSKI_ALONE in run.nodes


def test_with_north_and_simon_dead_nobody_saves_markus(tmp_path):
    simon_left_on_the_roof = {
        "ch23_00077": "SPARE",
        "ch23_00043": "Help",
        "ch23_00033": "LEAVE",
    }
    run = play_story(
        tmp_path, {**REVOLUTION, **LEAVE_NORTH, **simon_left_on_the_roof}
    )
    assert NOBODY_TO_SAVE_MARKUS in run.nodes
    assert NORTH_LEADS not in run.nodes
    assert run.flags["markus_alive"] is False


ENGINE_LABELS = ("TIME OUT", "TIMEOUT", "DEFAULT", "CommonTranslationKey", "OUT OF TIME")
FIXED_CHAPTERS = {"7", "28", "32.5", "32.6"}


def test_no_option_label_is_an_engine_or_timeout_string():
    for nid, node in load_dataset()["nodes"].items():
        if node["type"] != "choice" or str(node["chapter"]) not in FIXED_CHAPTERS:
            continue
        for option in node["options"]:
            assert not any(s in option["label"] for s in ENGINE_LABELS), (
                nid,
                option["label"],
            )
