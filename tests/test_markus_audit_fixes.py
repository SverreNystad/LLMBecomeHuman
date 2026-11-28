"""Fixes from the audit of Markus's chapters against the game's transcripts."""

import pytest

from tests.dataset import flags_in, load_dataset, play_story, reachable
from tests.test_markus_endings import PEACEFUL

# Capitol Park: tearing down the statue is the violent message, whatever comes after.
CAPITOL_PARK = {"ch26_x0101": "SECURE THE AREA FIRST", "ch26_00146": "HIDE"}
MESSAGE, MOLOTOV = "ch26_00075", "ch26_00070"
AGGRESSIVE_MEDIA, PACIFIST_MEDIA = "ch26_00022", "ch26_00020"


@pytest.mark.slow
def test_destroying_the_statue_is_violent_even_without_the_molotov(tmp_path):
    run = play_story(
        tmp_path, {**CAPITOL_PARK, MESSAGE: "DESTROY THE STATUE", MOLOTOV: "REFUSE"}
    )
    assert run.flags["markus_capitol_park_violent"] is True
    assert AGGRESSIVE_MEDIA in run.nodes and PACIFIST_MEDIA not in run.nodes


@pytest.mark.slow
def test_tagging_the_statue_and_refusing_the_molotov_stays_peaceful(tmp_path):
    run = play_story(
        tmp_path, {**CAPITOL_PARK, MESSAGE: "TAG THE STATUE", MOLOTOV: "REFUSE"}
    )
    assert run.flags["markus_capitol_park_violent"] is False
    assert PACIFIST_MEDIA in run.nodes


# Night of the Soul: Josh and Simon speak of North's death only when her Fate ended.
JOSH_ON_NORTH, SIMON_ASKED = "ch31_1_00047", "ch31_1_00060"
JOSH_NORTH_LINE = "ch31_1_00046"


def test_night_of_the_soul_reads_north_s_fate():
    nodes = load_dataset()["nodes"]
    for nid in (JOSH_ON_NORTH, SIMON_ASKED):
        flags = set().union(*(flags_in(b["when"]) for b in nodes[nid]["branches"]))
        assert flags == {"north_alive"}, nid


@pytest.mark.slow
@pytest.mark.parametrize("north_dies", [True, False])
def test_josh_mourns_north_only_when_she_died(tmp_path, north_dies):
    run = play_story(tmp_path, {"ch30_3_00040": "RUN" if north_dies else "SAVE NORTH"})
    assert (JOSH_NORTH_LINE in run.nodes) is north_dies


# Battle for Detroit 32.5: when the soldiers fire on the barricade, "Markus and his
# people fell where they stood"; North, Simon and Josh are behind it with him.
BARRICADE, REFUSE_DEAL = "ch32_5_00045", {"ch32_5_00076": "REFUSE DEAL"}
VICTORY_SPEECH = "ch32_5_00034"
VIOLENT_RECORD = {**CAPITOL_PARK, MOLOTOV: "TAKE"}


@pytest.mark.slow
def test_singing_at_the_barricade_with_a_violent_record_kills_everyone_there(tmp_path):
    run = play_story(tmp_path, {**VIOLENT_RECORD, **REFUSE_DEAL, BARRICADE: "SING"})
    assert run.flags["markus_capitol_park_violent"] is True
    assert VICTORY_SPEECH not in run.nodes
    for fate in ("markus_alive", "north_alive", "simon_alive", "josh_alive"):
        assert run.flags[fate] is False, fate


@pytest.mark.slow
def test_singing_with_a_peaceful_record_leaves_everyone_alive(tmp_path):
    run = play_story(tmp_path, {**PEACEFUL, **REFUSE_DEAL, BARRICADE: "SING"})
    assert VICTORY_SPEECH in run.nodes
    assert run.flags["markus_alive"] is True and run.flags["north_alive"] is True


# Freedom March: after dispersing, the second volley's choices make the same Public
# News as the first volley's.
DISPERSED_UNDER_FIRE = "ch28_00041"


@pytest.mark.slow
@pytest.mark.parametrize(
    "label, headline",
    [
        ("STAY", "Android marchers stand motionless under police gunfire"),
        ("DISPERSE", "Android marchers flee downtown plaza under police fire"),
    ],
)
def test_the_second_volley_makes_the_news_its_choice_made(tmp_path, label, headline):
    run = play_story(tmp_path, {"ch28_00044": "DISPERSE", DISPERSED_UNDER_FIRE: label})
    decisions = [e for e in run.events if e["type"] == "decision"]
    at = next(
        i for i, e in enumerate(decisions) if e["node_id"] == DISPERSED_UNDER_FIRE
    )
    assert headline not in decisions[at]["input"].get("news", [])
    assert headline in decisions[at + 1]["input"]["news"]


# Quick-Time Event failures always succeed today, but a failure that kills someone in
# the transcript ends their Fate, ready for when failure becomes possible.
@pytest.mark.parametrize(
    "nid, branch, fates",
    [
        # "SIMON! Simon…" / "There was nothing you could do."
        (
            "ch23_00041",
            0,
            {"simon_alive": False, "markus_simon_fate": "killed_in_broadcast"},
        ),
        ("ch30_3_00037", 0, {"north_alive": False}),  # Markus can't save North
        (
            "ch30_3_00034",
            0,
            {"north_alive": False},
        ),  # North dies, Connor rescues Markus
        ("ch30_3_00034", 1, {"markus_alive": False}),  # Markus dies, North escapes
        ("ch30_3_00023", 1, {"markus_alive": False}),  # "Save our people…"
        ("ch32_5_x0107", 0, {"north_alive": False}),  # North takes the bullet
    ],
)
def test_a_deadly_quick_time_event_failure_ends_the_fate(nid, branch, fates):
    taken = load_dataset()["nodes"][nid]["branches"][branch]
    assert taken["effects"]["flags"] == fates


# 32.5: when the barricade falls, "a world that watched and did nothing": no suspension.
MEDIA_REACTS = "ch32_5_00022"
DESTRUCTION_SPEECH = "ch32_5_00020"
SUSPENSION_SPEECHES = {"ch32_5_00004", "ch32_5_00009", "ch32_5_00014"}


@pytest.mark.parametrize("response", ["kiss", "sing"])
def test_a_failed_demonstration_never_plays_the_suspension_speech(response):
    seen = set(
        reachable(
            MEDIA_REACTS,
            {
                "markus_barricade_response": response,
                "markus_public_opinion": "negative",
            },
        )
    )
    assert not SUSPENSION_SPEECHES & seen
    assert DESTRUCTION_SPEECH in seen


# Public News: what Markus decides in the church is private. The public learns of
# the demonstration from the Hart Plaza march itself (32.5).
@pytest.mark.slow
def test_markus_s_plan_in_the_church_is_not_public_news(tmp_path):
    church = load_dataset()["nodes"]["ch31_1_00006"]
    assert not any(o["effects"].get("news") for o in church["options"])
    run = play_story(tmp_path, {})
    first = next(
        str(e["chapter"])
        for e in run.events
        if e["type"] == "decision"
        and any("Hart Plaza" in h for h in e["input"].get("news", []))
    )
    assert first == "32.5"
