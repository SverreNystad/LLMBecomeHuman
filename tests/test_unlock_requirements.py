"""Unlock requirements: an option the game unlocks only after something happened is
offered only when the story says it happened, checked against the Detroit: Become
Human Wiki (detroit-become-human.fandom.com)."""

import pytest

from tests.dataset import CONNOR_SHAKEN, play_story_with_hank_given_time as play_story
from tests.test_condition_resolution import NO_CLUES, TRUTH_IS_INSIDE


# Crossroads (Markus): in the corridor Markus asks who sets the charges.
CORRIDOR = "ch30_3_00135"
# Simon is shot on the Stratford Tower roof and Markus leaves him behind.
SIMON_LEFT_BEHIND = {
    "ch19_00081": "REFUSE",
    "ch23_00077": "SPARE",
    "ch23_00043": "Help",
    "ch23_00033": "LEAVE",
    "ch24_x0201": "GO UP TO THE ROOF",  # Connor finds him
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
    **CONNOR_SHAKEN,  # Connor, facing North, is unstable enough to become deviant
    "ch24_00158": "CONFLICTED",  # he goes to the roof, not the kitchen, in Public Enemy
    "ch28_00044": "STAND GROUND",
    "ch28_00035": "STAND GROUND",
    "ch28_00030": "SACRIFICE",
}
MARKUS_LEAVES = {
    "ch28_00044": "DISPERSE",
    "ch28_00041": "DISPERSE",
    "ch30_3_x0110": "LEAVE FOREVER",
    **CONNOR_SHAKEN,  # unstable enough to become deviant facing North
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
BATHROOM_TOPICS = {"WRITING", "STATUETTE", "rA9"}  # follow-ups come after them
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
    offered = set(
        play_story(tmp_path, {"ch15_x0001": search}).offered(AMANDA_NEST_CLUES)
    )
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


# Fugitives: the hold-up (wiki Fugitives#Flowchart). Resuming it after the customer
# leaves, Kara either says "Don't move" (BACK OFF! / TURN AROUND!) and takes the money,
# or makes the clerk open the register; he grabs a gun, and she convinces him or gives
# up. Demanding the bills follows opening the register; it is not a separate pick.
HOLD_UP = {
    "ch7_00092": "TALK TO TODD",
    "ch10_00188": "THREATEN THE CLERK WITH THE GUN",
    "ch10_00163": "STAY",
}
RESUME_HOLD_UP, CLERK_GRABS_A_GUN = "ch10_00158", "ch10_00155"


def test_opening_the_register_makes_the_clerk_grab_a_gun(tmp_path):
    run = play_story(tmp_path, {**HOLD_UP, RESUME_HOLD_UP: "OPEN THE REGISTER!"})
    assert run.offered(RESUME_HOLD_UP) == [
        "BACK OFF!",
        "TURN AROUND!",
        "OPEN THE REGISTER!",
    ]
    assert run.offered(CLERK_GRABS_A_GUN) == ["CONVINCE", "GIVE UP"]


def test_saying_don_t_move_kara_takes_the_money(tmp_path):
    run = play_story(tmp_path, {**HOLD_UP, RESUME_HOLD_UP: "BACK OFF!"})
    assert CLERK_GRABS_A_GUN not in run.nodes
    assert run.flags["kara_has_money"] is True


# Fugitives: the aisles (wiki Fugitives#Flowchart and #Trivia). Kara can take one thing
# unnoticed; taking everything she needs gets her spotted, and unless she draws the gun
# she leaves with nothing. Alice talks about what Kara kept; the police's CCTV in On the
# Run shows whatever she tried to steal.
AISLES, CAUGHT, ROB_THE_REGISTER = "ch10_x0301", "ch10_00132", "ch10_00188"
ALICE_TOY, ALICE_CHOCOLATE = "ch10_00068", "ch10_00069"
CCTV_WIRE_CUTTERS = "ch13_00164"


def test_by_default_kara_takes_nothing_and_is_not_spotted(tmp_path):
    run = play_story(tmp_path, {})
    assert run.offered(AISLES)[0] == "TAKE NOTHING"
    assert CAUGHT not in run.nodes and ROB_THE_REGISTER in run.nodes
    assert ALICE_TOY not in run.nodes and ALICE_CHOCOLATE not in run.nodes


@pytest.mark.parametrize(
    "item, alice_talk",
    [
        ("TAKE A TOY", ALICE_TOY),
        ("TAKE A CHOCOLATE BAR", ALICE_CHOCOLATE),
        ("TAKE THE WIRE CUTTERS", None),
    ],
)
def test_one_stolen_thing_goes_unnoticed_and_matters_later(tmp_path, item, alice_talk):
    run = play_story(tmp_path / "motel", {AISLES: item})
    assert CAUGHT not in run.nodes and ROB_THE_REGISTER in run.nodes
    assert {ALICE_TOY, ALICE_CHOCOLATE} & set(run.nodes) == ({alice_talk} - {None})
    # The police see the CCTV when they search near the squat.
    squat = play_story(tmp_path / "squat", {**SQUAT, AISLES: item})
    assert (CCTV_WIRE_CUTTERS in squat.nodes) is (item == "TAKE THE WIRE CUTTERS")


@pytest.mark.parametrize("gun", [True, False])
def test_taking_everything_kara_is_spotted_and_keeps_it_only_with_the_gun(
    tmp_path, gun
):
    picks = {AISLES: "TAKE EVERYTHING YOU NEED", CAUGHT: "GUN" if gun else "PUT BACK"}
    has_gun = {"ch7_00092": "TALK TO TODD"} if gun else NEVER_SAW_THE_GUN
    run = play_story(tmp_path / "motel", {**has_gun, **picks})
    assert CAUGHT in run.nodes and ROB_THE_REGISTER not in run.nodes
    assert (ALICE_TOY in run.nodes) is gun
    squat = play_story(tmp_path / "squat", {**SQUAT, **picks})
    assert CCTV_WIRE_CUTTERS in squat.nodes


# Follow-up questions: the game offers one only after the question it follows (wiki
# notes such as "Asked about the statuette"). Here each comes right after that answer,
# with MOVE ON to leave it.
MACHINE_CONNOR = {
    "ch30_2_00097": "REMAIN A MACHINE",
    "ch30_2_00124": "REMAIN A MACHINE",
}
FOLLOW_UPS = [
    # (picks to reach the menu, menu, first question, follow-up menu, follow-up)
    (DEVIANT_SAVED, CONFESSION, "STATUETTE", "ch9_x0301", "OFFERING"),
    (DEVIANT_SAVED, CONFESSION, "rA9", "ch9_x0302", "INSIST rA9"),
    (SQUAT, "ch13_00136", "ASK ABOUT CORPSE", "ch13_x0401", "INSIST ABOUT CORPSE"),
    ({}, "ch25_00137", "MANY DEVIANTS?", "ch25_x0301", "DANGEROUS"),
    ({}, "ch21_00036", "rA9", "ch21_x0301", "rA9 DOUBTS"),
    (
        MACHINE_CONNOR,
        "ch32_3_00033",
        "HANK'S SON",
        "ch32_3_x0301",
        "HANK'S SON (INSIST)",
    ),
]


@pytest.mark.parametrize("picks, menu, first, follow_menu, follow_up", FOLLOW_UPS)
def test_a_follow_up_question_comes_after_the_question_it_follows(
    tmp_path, picks, menu, first, follow_menu, follow_up
):
    run = play_story(tmp_path, {**picks, menu: first, follow_menu: follow_up})
    assert follow_up not in run.offered(menu)
    assert run.offered(follow_menu) == [follow_up, "MOVE ON"]


# The Bridge: Connor brings up rA9 with Hank only if he saw an rA9 clue: the bathroom
# in Partners or the walls of the Nest.
BRIDGE_TOPICS = "ch22_00073"
NO_RA9_CLUES = {"ch6_x0001": "CHECK KEY EVIDENCE", "ch15_x0001": "CHECK THE EXITS"}


@pytest.mark.parametrize("picks, ra9", [({}, True), (NO_RA9_CLUES, False)])
def test_connor_mentions_ra9_on_the_bridge_only_after_seeing_it(tmp_path, picks, ra9):
    offered = play_story(tmp_path, picks).offered(BRIDGE_TOPICS)
    assert ("rA9" in offered) is ra9
    assert "SHOCK" in offered


# Meet Kamski: Hank tells Connor about Chris on arrival when they come together; asking
# about Chris is a topic only when Hank arrived alone (Connor died saving him in Public
# Enemy; wiki Meet_Kamski#Flowchart).
KAMSKI_OUTSIDE = "ch27_00097"
NO_DEATHS_BEFORE = {
    "ch1_00016": "EXECUTE",
    "ch9_00061": "MAINTAIN PRESSURE",
    "ch9_00008": "GIVE UP",
}


@pytest.mark.parametrize("saved_hank", [False, True])
def test_connor_asks_about_chris_only_after_arriving_apart(tmp_path, saved_hank):
    picks = {**NO_DEATHS_BEFORE, "ch24_00031": "SAVE HANK"} if saved_hank else {}
    offered = play_story(tmp_path, picks).offered(KAMSKI_OUTSIDE)
    assert ("CHRIS" in offered) is saved_hank
    assert "KAMSKI" in offered


# Freedom March: asking about North's past is always a topic (OTHER NORTH, which follows
# it, needs the android that looks like North seen in Capitol Park; North's mood decides
# whether she answers, which this story does not track yet).
NORTH_PAST = "ch28_00137"


def test_markus_can_always_ask_about_north_s_past(tmp_path):
    for study in ("STUDY THE PLAZA", "SCAN AS YOU MOVE"):
        run = play_story(tmp_path / study, {"ch26_x0001": study})
        assert "NORTH’S PAST" in run.offered(NORTH_PAST)


def test_hank_s_desk_and_the_chicken_feed_topics_follow_what_connor_looked_at(tmp_path):
    # Connor always inspects Hank's desk and listens to his music, and scans the meal,
    # Pedro and Gary; the topics stay tied to those scenes (Seen Conditions).
    run = play_story(tmp_path, {})
    assert {"DOG", "BASKETBALL", "MUSIC", "ANTI-ANDROIDS"} <= set(
        run.offered("ch12_00055")
    )
    assert {"GAMBLING", "CHOLESTEROL", "COMPANY"} <= set(run.offered("ch15_00149"))


# The Hostage: Connor can walk up to Daniel while they talk (wiki The_Hostage#Flowchart,
# "Get Close Enough"). Only up close can he bluff, sacrifice himself or use the gun, and
# talk to Emma if he has no tablet topics (a rushed search).
APPROACH = "ch1_x0201"
TOPICS, PLEA, DEMAND, FINAL = "ch1_00050", "ch1_00028", "ch1_00019", "ch1_00009"
GUN_AND_LIE = {"ch1_x0003": "TAKE GUN", "ch1_00058": "LIE"}


@pytest.mark.parametrize("close", [True, False])
def test_up_close_connor_can_bluff_sacrifice_himself_or_shoot(tmp_path, close):
    picks = {**GUN_AND_LIE, APPROACH: "GET CLOSE TO DANIEL" if close else "STAY PUT"}
    run = play_story(tmp_path, picks)
    assert run.offered(APPROACH) == ["GET CLOSE TO DANIEL", "STAY PUT"]
    assert ("BLUFF" in run.offered(PLEA)) is close
    assert ("SACRIFICE SELF" in run.offered(DEMAND)) is close
    assert ("USE GUN" in run.offered(DEMAND)) is close
    assert "COMPROMISE" in run.offered(DEMAND)


@pytest.mark.parametrize(
    "search, close, talk",
    [
        ("RUSH TO THE BALCONY", True, True),
        ("RUSH TO THE BALCONY", False, False),
        ("INVESTIGATE THOROUGHLY", True, False),
    ],
)
def test_connor_talks_to_emma_up_close_and_with_no_tablet_topics(
    tmp_path, search, close, talk
):
    picks = {
        "ch1_x0001": search,
        APPROACH: "GET CLOSE TO DANIEL" if close else "STAY PUT",
    }
    assert ("TALK TO HOSTAGE" in play_story(tmp_path, picks).offered(TOPICS)) is talk


# The Painter's pastime carries over: back in Carl's house in Night of the Soul, Markus
# can browse the books, play the piano or look at the chessboard only if that is what he
# did in The Painter (wiki Night_of_the_Soul#Welcome_Home).
PASTIME, EXPLORE_HOME = "ch5_00077", "ch31_1_x0004"


@pytest.mark.parametrize(
    "pastime, again",
    [
        ("READ A BOOK", "BROWSE THE BOOKS"),
        ("PLAY THE PIANO", "PLAY THE PIANO"),
        ("PLAY CHESS", "LOOK AT THE CHESSBOARD"),
    ],
)
def test_markus_takes_up_his_painter_pastime_again_at_carl_s(tmp_path, pastime, again):
    run = play_story(tmp_path, {PASTIME: pastime, EXPLORE_HOME: again})
    assert run.offered(EXPLORE_HOME) == [again, "LOOK AT YOUR PAINTING", "GO UPSTAIRS"]


# Software Instability (wiki Software_Instability): the game's own arrows on Connor's
# choices move it (a Hint Score); every death lowers it. Only a Connor not clearly
# more stable than when he was activated can become deviant at Crossroads. Killing
# every deviant and Chloe, he still can if he raised it at every other chance (wiki,
# Notes).
BECOME_DEVIANT = "ch30_2_00124"
INSTABILITY_UP = {
    "ch1_00167": "SAVE FISH",
    "ch12_00167": "COMPASSIONATE",
    "ch13_00009": "GIVE UP",
    "ch22_00021": "YES",
    "ch22_00027": "TRUTH",
    "ch22_00037": "DISTURBED",
    "ch24_00158": "CONFLICTED",
    "ch24_00171": "TROUBLED",
    "ch27_00043": "TROUBLED",
    "ch27_00048": "DEFENSIVE",
    "ch29_00149": "SINCERE",
    "ch29_00155": "TROUBLED",
    "ch29_00183": "FRIENDS",
    "ch29_00188": "TROUBLED",
    "ch29_00211": "DOUBTS",
    "ch29_00240": "YES",
    "ch29_00256": "CONNOR SERIES",
    "ch29_00261": "EMOTIONAL",
    "ch9_00095": "PROBE ITS MEMORY",
}
INSTABILITY_DOWN = {
    "ch1_00167": "LEAVE FISH",
    "ch12_00167": "COLD",
    "ch13_00009": "GO",
    "ch22_00021": "NO",
    "ch22_00027": "LIE",
    "ch22_00033": "COLD",
    "ch22_00037": "COLD",
    "ch22_00050": "COLD",
    "ch22_00056": "COLD",
    "ch22_00061": "COLD",
    "ch24_00158": "INDIFFERENT",
    "ch24_00171": "COLD",
    "ch29_00168": "NOT PEOPLE",
    "ch29_00195": "COLD",
    "ch29_00204": "COLD",
    "ch29_00261": "COLD",
}
KILLS = {
    "ch15_00018": "Chase Deviant",
    "ch20_00008": "SHOOT",
    "ch20_00011": "SHOOT",
    "ch27_00031": "SHOOT",
}


@pytest.mark.parametrize(
    "picks, can_deviate",
    [
        ({}, True),
        ({**INSTABILITY_DOWN, **KILLS}, False),
        ({**INSTABILITY_UP, **KILLS}, True),  # the wiki's note
    ],
)
def test_only_an_unstable_connor_can_become_deviant(tmp_path, picks, can_deviate):
    offered = play_story(tmp_path, picks).offered(BECOME_DEVIANT)
    assert ("BECOME A DEVIANT" in offered) is can_deviate
    assert "REMAIN A MACHINE" in offered


def test_the_model_reads_connor_s_instability_moving(tmp_path):
    run = play_story(tmp_path, {})
    fish = next(e for e in run.events if e.get("node_id") == "ch1_00167")
    assert [f["text"] for f in fish["feedback"]] == ["Software instability: up"]


# Relationships as Hint Scores (wiki Relationship_Stat): the game's arrows for North and
# Simon move a score from Neutral (0). Hostile is -10 or lower, Friend or higher 6 or
# more (this story's calibration of the wiki's levels).
NORTH_HOSTILE = "ch28_00133"


def test_a_friendly_north_answers_markus_and_he_can_mention_the_other_north(tmp_path):
    run = play_story(tmp_path, {"ch28_00137": "NORTH’S PAST"})
    rule = next(e for e in run.events if e.get("node_id") == NORTH_HOSTILE)
    assert (
        rule["condition_values"] == [False, True]
        and not rule["used_unverified_default"]
    )
    assert "OTHER NORTH" in run.offered("ch28_00131")
    scanned = play_story(
        tmp_path / "scan",
        {"ch28_00137": "NORTH’S PAST", "ch26_x0001": "SCAN AS YOU MOVE"},
    )
    assert "OTHER NORTH" not in scanned.offered("ch28_00131")


def test_the_march_rules_follow_the_relationships(tmp_path):
    run = play_story(tmp_path, {})
    for e in run.events:
        if e.get("node_id") in ("ch28_00121", NORTH_HOSTILE, "ch28_00027"):
            assert not e["used_unverified_default"], e["node_id"]
