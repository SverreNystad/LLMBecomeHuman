"""Markus's chapters checked against the wiki's flowcharts (round 2 of the audit)."""

import pytest

from detroit_benchmark.engine import effect_flags
from tests.dataset import load_dataset, play_story, reachable, resolve
from tests.test_markus_endings import PEACEFUL, REFUSE_DEAL
from tests.test_night_of_the_soul import MACHINE

REVOLUTION = {"ch31_1_00006": "REVOLUTION"}


def _node(nid: str) -> dict:
    return load_dataset()["nodes"][nid]


def _option(nid: str, label: str) -> dict:
    return next(o for o in _node(nid)["options"] if o["label"] == label)


def _next(nid: str, flags: dict) -> str:
    step = resolve(nid, flags)
    assert not step.assumed, nid
    return step.next


# Night of the Soul: "If Markus decides to not trust Connor, he will ... [execute]
# him"; "deviant Connor will die and another, non-deviant RK800 will be deployed".
def test_not_trusting_connor_kills_him_and_cyberlife_sends_a_machine(tmp_path):
    run = play_story(tmp_path, {"ch31_1_00041": "DON'T TRUST"})
    assert run.flags["connor_deviant"] is False
    assert run.flags["connor_killed_by_markus"] is True
    assert "32.3" in run.chapters and "32.4" not in run.chapters


def test_simon_s_josh_topic_needs_josh_dead():
    josh = _option("ch31_1_00059", "JOSH")
    assert josh["requires"] == [{"flag": "josh_alive", "equals": False}]
    assert not josh["requirements_unverified"]


# 32.6 opens on one rule, so Connor's rooftop scene can sit between 32.5 and 32.6.
ENTRY = "ch32_6_x0118"
REVOLT, NORTH_LEADS, END = "ch32_6_00125", "ch32_6_00011", "ch32_6_00001"
ALIVE = {
    "markus_alive": True, "markus_left_jericho": False, "north_alive": True,
    "markus_demonstration_outcome": "none", "connor_shot_deviant_leader": False,
}


@pytest.mark.parametrize(
    "flags, dest",
    [
        ({"markus_peaceful": False}, REVOLT),
        ({"markus_peaceful": True, "markus_demonstration_outcome": "won"}, END),
        # Markus died at the demonstration: there is no revolution for North to lead.
        ({"markus_peaceful": True, "markus_demonstration_outcome": "died_with_his_people",
          "markus_alive": False}, END),
        # Markus died before the battle, or left Jericho.
        ({"markus_peaceful": False, "markus_alive": False}, NORTH_LEADS),
        ({"markus_peaceful": False, "markus_left_jericho": True}, NORTH_LEADS),
        # The demonstration itself ended Markus's story: nothing more to play.
        ({"markus_peaceful": True, "markus_alive": False,
          "markus_demonstration_outcome": "died_with_his_people"}, END),
        ({"markus_peaceful": False, "markus_alive": False, "north_alive": False}, END),
    ],
)
def test_32_6_opens_on_markus_s_fate_and_the_demonstration(flags, dest):
    assert _next(ENTRY, {**ALIVE, **flags}) == dest


def test_every_way_into_32_6_goes_through_its_entry_rule():
    nodes = load_dataset()["nodes"]
    assert nodes["route_markus_final"]["if_false"] == ENTRY
    into = [b["next"] for b in nodes["final_x0903"]["branches"]]
    assert NORTH_LEADS not in into and ENTRY in into


# 32.5 records how the demonstration ended, for 32.6 and Connor's rooftop.
@pytest.mark.parametrize(
    "picks, outcome, alive",
    [
        ({**PEACEFUL, **REFUSE_DEAL, "ch32_5_00045": "SING"}, "won", True),
        ({**REFUSE_DEAL, "ch32_5_00045": "SACRIFICE"}, "died_with_his_people", False),
        ({**REFUSE_DEAL, "ch32_5_00045": "DO NOTHING"}, "died_with_his_people", False),
        ({"ch32_5_00076": "ACCEPT DEAL"}, "betrayed", False),
        ({"ch26_00070": "REFUSE", "ch30_3_00171": "KEEP", **REFUSE_DEAL,
          "ch32_5_00045": "DIRTY BOMB"}, "free_in_the_debris", True),
    ],
)
def test_the_demonstration_records_its_outcome(tmp_path, picks, outcome, alive):
    run = play_story(tmp_path, picks)
    assert run.flags["markus_demonstration_outcome"] == outcome
    assert run.flags["markus_alive"] is alive


# Simon and Josh wiki pages: if Markus "sacrifices himself, or does nothing, Simon and
# the rest of the group are killed".
@pytest.mark.parametrize("response", ["SACRIFICE", "DO NOTHING"])
def test_sacrifice_or_doing_nothing_kills_everyone_at_the_barricade(tmp_path, response):
    run = play_story(tmp_path, {**PEACEFUL, **REFUSE_DEAL, "ch32_5_00045": response})
    for fate in ("markus_alive", "north_alive", "simon_alive", "josh_alive"):
        assert run.flags[fate] is False, fate
    assert "ch32_5_00034" not in run.nodes


# Public Opinion: "Choosing 'provoke' or 'accuse' when talking to the army" lowers it.
def test_provoking_and_accusing_the_army_turns_the_song_into_a_massacre(tmp_path):
    hostile = {"ch32_5_00170": "PROVOKE", "ch32_5_00164": "ACCUSE"}
    run = play_story(tmp_path, {**PEACEFUL, **REFUSE_DEAL, **hostile,
                                "ch32_5_00045": "SING"})
    assert run.flags["markus_public_opinion"] == "negative"
    assert run.flags["markus_alive"] is False


def test_staying_firm_keeps_public_opinion_positive(tmp_path):
    run = play_story(tmp_path, {**PEACEFUL, **REFUSE_DEAL, "ch32_5_00045": "SING"})
    assert run.flags["markus_public_opinion"] == "positive"


# Defending the Barricade: "Fail to Save Androids → North Takes a Bullet for Markus
# ... OR Markus Shot → Markus Died Protecting His People".
def test_a_failed_defence_without_north_kills_markus():
    after = {"markus_alive": True, "north_alive": False}
    dest = _next("ch32_5_x0107", after)
    assert "ch32_5_00045" not in reachable(dest, after)


@pytest.mark.parametrize(
    "nid, labels",
    [
        ("ch32_5_x0108", ["RAISE FIST", "HANDS IN THE AIR", "SIT", "KNEEL"]),
        ("ch32_5_00149", ["USE THE ABANDONED CAR", "USE THE BILLBOARD", "USE THE BENCH"]),
        ("ch32_5_x0109", ["WE ARE ALIVE", "WE WANT FREEDOM", "EQUAL RIGHTS FOR ANDROIDS",
                          "LET OUR PEOPLE GO"]),
    ],
)
def test_the_demonstration_offers_the_wiki_s_choices(tmp_path, nid, labels):
    run = play_story(tmp_path, {})
    assert run.offered(nid) == labels


# 32.6 Revolution.
def test_markus_can_leave_simon_behind_and_simon_dies(tmp_path):
    run = play_story(tmp_path, {**REVOLUTION, "ch32_6_x0124": "KEEP GOING"})
    assert run.flags["simon_alive"] is False
    saved = play_story(tmp_path / "saved", REVOLUTION)
    assert saved.flags["simon_alive"] is True and "ch32_6_00058" in saved.nodes


def test_josh_dies_whether_or_not_markus_reaches_him(tmp_path):
    run = play_story(tmp_path, {**REVOLUTION, "ch32_6_x0123": "KEEP GOING"})
    assert run.flags["josh_alive"] is False and "ch32_6_00104" not in run.nodes


def test_markus_cannot_refuse_simon_s_heart():
    heart = _node("ch32_6_x0112")
    assert heart["type"] == "condition" and heart["resolution"] == "rule"
    assert [b["effects"]["flags"] for b in heart["branches"]] == [{"simon_alive": False}]


# Final Assault, machine Connor: "Control Connor → Win the Fight → Connor Stopped The
# Revolution; Lose the Fight → Markus Defeats Connor".
FIGHT, AS_CONNOR = "ch32_6_00046", "ch32_6_x0119"


def test_who_to_control_in_the_final_fight_is_a_choice(tmp_path):
    run = play_story(tmp_path, {**REVOLUTION, **MACHINE})
    assert run.offered(FIGHT) == ["CONTROL MARKUS", "CONTROL CONNOR"]
    assert run.flags["markus_alive"] is True and "ch32_6_00039" in run.nodes


def test_connor_winning_the_fight_stops_the_revolution(tmp_path):
    picks = {**REVOLUTION, **MACHINE, FIGHT: "CONTROL CONNOR", AS_CONNOR: "WIN THE FIGHT"}
    run = play_story(tmp_path, picks)
    assert run.flags["markus_alive"] is False
    assert run.flags["connor_stopped_the_revolution"] is True
    assert "ch32_6_00039" not in run.nodes


def test_connor_letting_markus_win_lets_the_assault_succeed(tmp_path):
    picks = {**REVOLUTION, **MACHINE, FIGHT: "CONTROL CONNOR", AS_CONNOR: "LET MARKUS WIN"}
    run = play_story(tmp_path, picks)
    assert run.flags["markus_alive"] is True and "ch32_6_00039" in run.nodes


# Alone in Store, machine Connor: "Shoot → Markus is Shot → Connor Executed Markus /
# Detonate Bomb"; "(if Markus accepted the dirty bomb but does not detonate) Connor
# Executed Markus".
def test_markus_shot_by_connor_can_still_detonate_the_bomb():
    assert _option("ch32_6_00026", "SHOOT")["next"] == "ch32_6_00025"


def test_not_detonating_after_connor_spares_him_gets_markus_executed():
    assert effect_flags(_option("ch32_6_00024", "DO NOT DETONATE"))["markus_alive"] is False


# Inside Store with North: kissing her and giving up the bomb go back to the choice.
def test_the_store_kiss_and_giving_up_the_bomb_return_to_the_choice():
    kiss = _option("ch32_6_00019", "KISS")
    assert not kiss["requirements_unverified"] and kiss["requires"]
    assert {o["label"] for o in _node(kiss["next"])["options"]} == {
        "DIRTY BOMB", "SUICIDE", "SURRENDER"}
    gave_up = _node(_option("ch32_6_00013", "GIVE UP")["next"])["next"]
    assert {o["label"] for o in _node(gave_up)["options"]} == {"SUICIDE", "SURRENDER"}


@pytest.mark.parametrize("nid, label", [("ch32_6_00013", "PRESS"),
                                        ("ch32_6_00031", "DIRTY BOMB")])
def test_every_detonation_is_public_news(nid, label):
    assert _option(nid, label)["effects"]["news"]


# Quick-Time Event rule: the final fight and coordinating the attack (failing it on
# purpose sends North to her death or fails the assault) are decisions; others stay
# reflexes.
def test_only_the_decision_quick_time_events_became_choices():
    nodes = load_dataset()["nodes"]
    assert nodes[FIGHT]["type"] == "choice"
    assert nodes["ch32_6_x0101"]["type"] == "choice"
    for nid in ("ch19_00119", "ch23_00041", "ch26_00156", "ch28_00012",
                "ch30_3_00035", "ch30_3_00076", "ch30_3_00095", "ch32_5_x0103"):
        assert nodes[nid]["resolution"] == "qte", nid


# Crossroads: Josh fighting a soldier, "Intervene" is always offered.
def test_intervening_for_josh_has_no_wounded_requirement():
    assert not _option("ch30_3_00078", "INTERVENE")["requirements_unverified"]


# Broken: "Check studio without Carl OR Check studio with Carl".
def test_markus_chooses_whether_carl_comes_to_the_studio(tmp_path):
    run = play_story(tmp_path, {"ch8_00051": "CHECK THE STUDIO WITH CARL"})
    assert "ch8_00050" in run.nodes and "ch8_00049" not in run.nodes


# Shades of Color: "Protesters harass Markus (side option)"; The Painter: "Carl
# notices Markus' clothes - happens if Markus encounters the protestors".
@pytest.mark.parametrize("label, harassed", [("WALK PAST THE PROTESTERS", True),
                                             ("GO AROUND THEM", False)])
def test_carl_notices_the_torn_clothes_only_after_the_protesters(tmp_path, label, harassed):
    run = play_story(tmp_path, {"ch3_x0003": label})
    assert ("ch3_00013" in run.nodes) is harassed
    assert ("ch5_00115" in run.nodes) is harassed
