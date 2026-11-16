"""Unlock requirements: an option the game unlocks only after something happened is
offered only when the story says it happened, checked against the Detroit: Become
Human Wiki (detroit-become-human.fandom.com)."""

import pytest

from tests.dataset import play_story_with_hank_given_time as play_story
from tests.test_condition_resolution import NO_CLUES, TRUTH_IS_INSIDE


# Crossroads (Markus): in the corridor Markus asks who sets the charges.
CORRIDOR = "ch30_3_00135"
# Simon is shot on the Stratford Tower roof and Markus leaves him behind.
SIMON_LEFT_BEHIND = {
    "ch19_00081": "REFUSE",
    "ch23_00077": "SPARE",
    "ch23_00043": "Help",
    "ch23_00033": "LEAVE",
}


@pytest.mark.parametrize("simon_dead", [False, True])
def test_markus_asks_simon_only_if_simon_is_alive(tmp_path, simon_dead):
    run = play_story(tmp_path, SIMON_LEFT_BEHIND if simon_dead else {})
    offered = run.offered(CORRIDOR)
    assert ("SIMON AND JOSH" in offered) is not simon_dead
    assert ("JOSH" in offered) is simon_dead


# Freedom March: on the roof Markus reflects on the message he sent in Capitol Park
# (wiki Freedom_March#Trivia: failing to send one unlocks its own topic).
ROOF_TOPICS = "ch28_00157"
FREE_THE_ANDROIDS = {"ch26_00146": "HIDE"}  # not "Abandon Mission" at the police car


@pytest.mark.parametrize(
    "picks, topic",
    [
        (FREE_THE_ANDROIDS, "APPEAL OF POWER"),  # destroyed the statue: aggressive
        ({**FREE_THE_ANDROIDS, "ch26_00075": "TAG THE STATUE"}, "FOLLOWERS"),
        ({"ch26_00146": "Abandon Mission"}, "FAILED"),
    ],
)
def test_markus_reflects_on_the_message_he_actually_sent(tmp_path, picks, topic):
    offered = play_story(tmp_path, picks).offered(ROOF_TOPICS)
    others = {"FOLLOWERS", "APPEAL OF POWER", "FAILED"} - {topic}
    assert topic in offered and not others & set(offered)


# Connor's topics that recall earlier chapters: with Amanda in Russian Roulette (18)
# and Public Enemy (24).
AMANDA_RR, AMANDA_PE_TONE = "ch18_00071", "ch24_00171"
GENTLE = {
    "ch15_00018": "Save Hank",  # The Nest
    "ch20_00008": "SPARE",  # The Eden Club
    "ch20_00011": "SPARE",
}
# Neither Daniel nor the deviant kills Connor before Russian Roulette.
NO_DEATHS = {
    "ch1_00016": "EXECUTE",
    "ch9_00061": "MAINTAIN PRESSURE",
    "ch9_00008": "GIVE UP",
}


def test_by_default_connor_recalls_his_deaths_but_no_rescue_or_mercy(tmp_path):
    # The default run chases Rupert, shoots a Traci and dies twice.
    run = play_story(tmp_path, {})
    assert run.flags["connor_deaths"] == 2
    assert "SAVING HANK" not in run.offered(AMANDA_RR)
    assert "CONNOR’S DEATH" in run.offered(AMANDA_RR)
    assert "SINCERE" not in run.offered(AMANDA_PE_TONE)


def test_a_gentle_connor_recalls_saving_hank_and_sparing_the_tracis(tmp_path):
    run = play_story(tmp_path, GENTLE)
    assert "SAVING HANK" in run.offered(AMANDA_RR)
    assert "SINCERE" in run.offered(AMANDA_PE_TONE)


def test_a_connor_who_never_died_has_no_death_to_recall(tmp_path):
    run = play_story(tmp_path, NO_DEATHS)
    assert "CONNOR’S DEATH" not in run.offered(AMANDA_RR)
    assert "NEGATIVE" in run.offered(AMANDA_RR)


# Night of the Soul (Connor): North leads Jericho's survivors; Connor asks about
# Markus only if Markus is dead, not if he walked away.
NORTH_TALK = "ch31_2_00024"
MARKUS_DIES = {
    **SIMON_LEFT_BEHIND,
    "ch28_00044": "STAND GROUND",
    "ch28_00035": "STAND GROUND",
    "ch28_00030": "SACRIFICE",
}
MARKUS_LEAVES = {
    "ch28_00044": "DISPERSE",
    "ch28_00041": "DISPERSE",
    "ch30_3_x0110": "LEAVE FOREVER",
}


@pytest.mark.parametrize("picks, dead", [(MARKUS_DIES, True), (MARKUS_LEAVES, False)])
def test_connor_asks_north_about_markus_only_if_he_died(tmp_path, picks, dead):
    run = play_story(tmp_path, picks)
    assert run.flags["markus_alive"] is not dead
    offered = run.offered(NORTH_TALK)
    assert "SITUATION" in offered  # the conversation happens either way
    assert ("MARKUS" in offered) is dead


# Partners clues: the rA9 signs, the "I AM ALIVE" message and the statuette are in the
# bathroom (wiki The_Interrogation#Notes), which only a thorough search reaches. The
# deviant's confession (9) and the saved deviant at the station (12) bring them up.
CONFESSION, SAVED_DEVIANT_TALK = "ch9_00056", "ch12_00161"
BATHROOM_TOPICS = {"WRITING", "STATUETTE", "OFFERING", "rA9", "INSIST rA9"}
KEY_EVIDENCE_ONLY = {"ch6_x0001": "CHECK KEY EVIDENCE"}
# Connor convinces the deviant and intervenes when Chris takes it (The Interrogation).
DEVIANT_SAVED = TRUTH_IS_INSIDE


@pytest.mark.parametrize("thorough", [True, False])
def test_the_bathroom_clues_need_a_thorough_search_in_partners(tmp_path, thorough):
    picks = DEVIANT_SAVED if thorough else {**DEVIANT_SAVED, **KEY_EVIDENCE_ONLY}
    run = play_story(tmp_path, picks)
    confession = set(run.offered(CONFESSION))
    assert "ATTIC" in confession
    assert confession & BATHROOM_TOPICS == (BATHROOM_TOPICS if thorough else set())
    assert ("STATUETTE" in run.offered(SAVED_DEVIANT_TALK)) is thorough
    assert "rA9" in run.offered(SAVED_DEVIANT_TALK)


def test_connor_shows_the_photos_only_if_he_looked_at_the_files(tmp_path):
    rushed = play_story(tmp_path, {"ch9_x0001": "START THE INTERROGATION"})
    assert "SHOW PHOTOS" not in rushed.offered("ch9_00123")
    assert "NAME" in rushed.offered("ch9_00123")


# Kara's gun (taken in Stormy Night, seen upstairs in A New Home): Ralph's hospitality
# answers a Kara without one. CHECK GUN is offered only to a Kara who took it in Stormy
# Night and left it upstairs in the squat: she checks and it is gone (wiki
# On_the_Run#Trivia, "Forgot Gun").
SQUAT = {"ch7_00092": "TALK TO TODD", "ch10_00109": "DON'T STEAL", "ch10_00039": "STAY"}
NEVER_SAW_THE_GUN = {"ch4_x0003": "MOVE THROUGH QUICKLY"}
FORGOT_THE_GUN = {"ch13_x0213": "FORGET THE GUN"}
FENCE, RALPH_TALK = "ch10_00047", "ch13_00151"


@pytest.mark.parametrize(
    "picks, gun, check_gun",
    [
        ({}, True, False),  # takes the gun back
        (FORGOT_THE_GUN, True, True),
        (NEVER_SAW_THE_GUN, False, False),
    ],
)
def test_kara_s_gun_topics_follow_what_she_did_with_it(tmp_path, picks, gun, check_gun):
    run = play_story(tmp_path, {**SQUAT, **picks})
    assert ("GUN" in run.offered(FENCE)) is gun
    assert ("HOSPITALITY" in run.offered(FENCE)) is not gun
    assert ("CHECK GUN" in run.offered(RALPH_TALK)) is check_gun
    assert "WORRIED" in run.offered(RALPH_TALK)


# The Nest: Amanda asks what Connor found. The diary and the deviant's ID need a
# thorough search; the rA9 signs on the walls are seen unless Connor only checks the
# exits (wiki The_Nest#Flowchart).
AMANDA_NEST_CLUES = "ch18_00085"


@pytest.mark.parametrize(
    "search, clues",
    [
        ("SEARCH EVERYTHING", {"DEVIANT", "DIARY", "SIGNS ON WALLS"}),
        ("CHECK KEY POINTS", {"SIGNS ON WALLS"}),
        ("CHECK THE EXITS", set()),
    ],
)
def test_connor_tells_amanda_only_what_he_found_in_the_nest(tmp_path, search, clues):
    offered = set(play_story(tmp_path, {"ch15_x0001": search}).offered(AMANDA_NEST_CLUES))
    assert offered & {"DEVIANT", "DIARY", "SIGNS ON WALLS"} == clues
    assert "BIRDS" in offered


# Battle for Detroit, Markus Demonstration: the President speaks of the assault on
# Jericho only if there was one, i.e. Connor found Jericho (Crossroads).
PRESIDENT = "ch32_5_00203"


@pytest.mark.parametrize("found", [True, False])
def test_the_president_mentions_the_jericho_assault_only_after_one(tmp_path, found):
    run = play_story(tmp_path, {} if found else NO_CLUES)
    assert run.flags["connor_knows_jericho"] is found
    assert ("JERICHO ASSAULT" in run.offered(PRESIDENT)) is found
    assert "ARMY" in run.offered(PRESIDENT)


# Waiting for Hank...: THANKS is locked in the game by a bug (wiki
# Waiting_for_Hank...#Trivia), so it is never offered. START WORKING ends the small talk
# and leads to the deviant files and the AX400 lead, so it always is.
HANK_ARRIVES, HANK_TOPICS = "ch12_00060", "ch12_00055"
FILES = "ch12_00044"  # "243 files… The first dates back nine months…"


@pytest.mark.parametrize("picks", [{}, DEVIANT_SAVED])
def test_thanks_is_locked_and_start_working_leads_to_the_files(tmp_path, picks):
    run = play_story(tmp_path, {**picks, HANK_TOPICS: "START WORKING"})
    assert "THANKS" not in run.offered(HANK_ARRIVES)
    assert "START WORKING" in run.offered(HANK_TOPICS)
    assert FILES in run.nodes
