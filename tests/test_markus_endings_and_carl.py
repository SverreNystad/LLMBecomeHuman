"""Markus's dirty-bomb endings, the failed assault's store endings (32.6), and Carl's Fate.

Sources: the Battle for Detroit wiki flowchart and the Markus page (via the MediaWiki
API), and the game text of the Detroit Become Text transcript (press-dirty-bomb)."""

import pytest

from detroit_benchmark.engine import effect_flags
from detroit_benchmark.ending import ending_summary
from tests.dataset import load_dataset, play_story, reachable, resolve
from tests.test_night_of_the_soul import MACHINE

# 32.5: the detonator at the barricade.
BARRICADE = "ch32_5_00045"
PRESS_OR_GIVE_UP = "ch32_5_x0112"
BARRICADE_WITHOUT_BOMB = "ch32_5_x0114"
VICTORY_SPEECH = "ch32_5_00034"
BOMB_NEWS, WARREN_NUKE, WE_ARE_FREE = "ch32_5_x0115", "ch32_5_x0120", "ch32_5_x0123"
WITH_DETONATOR = {
    "ch26_00070": "REFUSE",
    "ch30_3_00171": "KEEP",
    "ch32_5_00076": "REFUSE DEAL",
    BARRICADE: "DIRTY BOMB",
}

# 32.6: the failed assault's CyberLife store.
STORE_WITH_NORTH_PRESS = "ch32_6_00013"
STORE_ALONE = "ch32_6_00031"
STORE_SUICIDE = "ch32_6_00015"
AFTER_GIVING_UP_THE_BOMB = "ch32_6_x0122"
AFTER_PUTTING_DOWN_THE_GUN = "ch32_6_x0141"
STORE_WHO_IS_THERE = "ch32_6_00033"
CONNOR_SHOOT_OR_SPARE, AFTER_CONNOR = "ch32_6_00026", "ch32_6_00025"
CONNOR_WALKS_AWAY = "ch32_6_x0142"
STORE_WE_ARE_FREE = "ch32_6_x0139"

# Carl.
BROKEN, CARL_ANGER_1, CARL_ANGER_2 = "ch8_00019", "ch31_1_00076", "ch31_1_00073"


def _nodes() -> dict:
    return load_dataset()["nodes"]


def _option(node_id: str, label: str) -> dict:
    return next(o for o in _nodes()[node_id]["options"] if o["label"] == label)


def _labels(node_id: str) -> list[str]:
    return [o["label"] for o in _nodes()[node_id]["options"]]


def _spoken(run, node_id: str) -> list[str]:
    event = next(e for e in run.events if e.get("node_id") == node_id)
    return [line["text"] for line in event["visible_to_agent"].get("dialogue", [])]


# --- The dirty bomb at the demonstration (32.5) ---


def test_the_detonator_asks_press_or_give_up():
    # Wiki flowchart, Defending the Barricade: "Observe Detonator → Give Up (loops back
    # to same choice) / Press → An Explosion Shakes Detroit".
    assert _option(BARRICADE, "DIRTY BOMB")["next"] == PRESS_OR_GIVE_UP
    assert "markus_dirty_bomb_detonated" not in effect_flags(
        _option(BARRICADE, "DIRTY BOMB")
    )
    assert _labels(PRESS_OR_GIVE_UP) == ["PRESS", "GIVE UP"]
    assert effect_flags(_option(PRESS_OR_GIVE_UP, "PRESS"))[
        "markus_dirty_bomb_detonated"
    ] is True
    give_up = _option(PRESS_OR_GIVE_UP, "GIVE UP")
    assert give_up["next"] == BARRICADE_WITHOUT_BOMB
    assert _labels(BARRICADE_WITHOUT_BOMB) == [
        label for label in _labels(BARRICADE) if label != "DIRTY BOMB"
    ]


def test_the_bomb_ending_plays_the_news_warren_and_we_are_free(tmp_path):
    run = play_story(tmp_path, WITH_DETONATOR)
    assert run.labels[PRESS_OR_GIVE_UP] == "PRESS"
    assert run.flags["markus_demonstration_outcome"] == "free_in_the_debris"
    assert run.flags["markus_alive"] is True
    # He does not give the victory speech of a won demonstration.
    assert VICTORY_SPEECH not in run.nodes
    assert {BOMB_NEWS, WARREN_NUKE, WE_ARE_FREE} <= set(run.nodes)
    assert _spoken(run, WE_ARE_FREE)[-5:] == [
        "We!..",
        "May God bless you all",
        "Are!..",
        "and may God bless the United States of America.",
        "Free!",
    ]
    face = _nodes()[WE_ARE_FREE]["description"]
    assert "face" in face and "flag" in face


def test_with_a_machine_connor_the_bomb_ends_his_story_with_his_mission_failed(
    tmp_path,
):
    run = play_story(tmp_path, {**MACHINE, **WITH_DETONATOR})
    assert run.flags["connor_deviant"] is False
    assert run.flags["markus_dirty_bomb_detonated"] is True
    assert run.flags["connor_story_ended"] is True
    assert run.flags["connor_mission_failed"] is True
    # Connor does not appear: no crowd scene after the demonstration (ADR 0004).
    assert "32.8" not in run.chapters


def test_a_deviant_connor_s_story_goes_on_after_the_bomb(tmp_path):
    run = play_story(tmp_path, WITH_DETONATOR)
    assert run.flags["connor_deviant"] is True
    assert run.flags["connor_mission_failed"] is False


# --- The failed assault's store (32.6) ---


@pytest.mark.parametrize("node_id, label", [(STORE_WITH_NORTH_PRESS, "PRESS"),
                                            (STORE_ALONE, "DIRTY BOMB")])
def test_the_bomb_in_the_store_plays_the_same_ending(node_id, label):
    after = set(reachable(_option(node_id, label)["next"], within_chapter=True))
    assert {"ch32_6_x0128", "ch32_6_x0133", STORE_WE_ARE_FREE} <= after


def test_putting_down_the_gun_does_not_end_the_story_alive():
    # The game keeps the soldiers outside: PUT DOWN returns to the choice, without
    # suicide this time, so every way out sets Markus's Fate or sets off the bomb.
    put_down = _option(STORE_SUICIDE, "PUT DOWN")
    assert put_down["next"] == AFTER_PUTTING_DOWN_THE_GUN
    # No flag records it: nothing would read it.
    assert effect_flags(put_down) == {}
    assert "markus_store_put_down_gun" not in load_dataset()["initial_flags"]
    assert "SUICIDE" not in _labels(AFTER_PUTTING_DOWN_THE_GUN)
    surrender = _option(AFTER_PUTTING_DOWN_THE_GUN, "SURRENDER")
    assert effect_flags(surrender)["markus_alive"] is False
    # Every way on from there ends the segment with a Fate or the bomb, never alive
    # in the store, and never back at the suicide choice.
    after = set(reachable(AFTER_PUTTING_DOWN_THE_GUN, within_chapter=True))
    assert STORE_SUICIDE not in after and AFTER_GIVING_UP_THE_BOMB not in after
    assert STORE_WE_ARE_FREE in after


def test_a_decommissioned_connor_does_not_come_to_the_store():
    flags = {"north_alive": False, "connor_deviant": False, "connor_story_ended": True}
    step = resolve(STORE_WHO_IS_THERE, flags)
    assert not step.assumed and step.branch_index is not None
    assert step.next == "ch32_6_00032"  # Markus alone


def test_connor_sparing_markus_without_the_bomb_walks_away():
    # Wiki, Markus: "if Connor spares Markus he will walk away".
    assert _option(CONNOR_SHOOT_OR_SPARE, "SPARE")["next"] == AFTER_CONNOR
    step = resolve(AFTER_CONNOR, {"markus_took_detonator": False})
    assert (step.next, step.branch_index, step.assumed) == (CONNOR_WALKS_AWAY, None, False)
    assert "walks away" in _nodes()[CONNOR_WALKS_AWAY]["description"]


# --- Carl's Fate ---


def test_carl_starts_alive():
    assert load_dataset()["initial_flags"]["carl_alive"] is True


def test_enduring_leo_kills_carl(tmp_path):
    run = play_story(tmp_path, {BROKEN: "ENDURE"})
    assert run.flags["carl_alive"] is False


def test_pushing_leo_keeps_carl_alive(tmp_path):
    run = play_story(tmp_path, {BROKEN: "PUSH LEO"})
    assert run.flags["carl_alive"] is True


def test_persistent_anger_in_night_of_the_soul_kills_carl(tmp_path):
    # Wiki, Carl Manfred: "If Markus persists in this behavior, then Carl will die of a
    # heart attack."
    run = play_story(
        tmp_path, {BROKEN: "PUSH LEO", CARL_ANGER_1: "ANGER", CARL_ANGER_2: "ANGER"}
    )
    assert run.labels[CARL_ANGER_2] == "ANGER"
    assert run.flags["carl_alive"] is False


# --- The Ending Summary ---


def _summary(flags: dict) -> dict:
    return ending_summary(flags, [], [], finished=True)


def test_the_ending_summary_lists_carl_s_fate():
    fates = {f["name"]: f for f in _summary({"carl_alive": False})["fates"]}
    assert fates["Carl"]["fate"] == "dead" and fates["Carl"]["text"] == "Dead"
    unknown = {f["name"]: f for f in _summary({})["fates"]}["Carl"]
    assert unknown["fate"] == "unknown" and unknown["text"] == "Unknown"


def test_the_ending_summary_says_connor_s_mission_failed():
    flags = {
        "connor_deviant": False,
        "connor_deaths": 0,
        "connor_story_ended": True,
        "connor_mission_failed": True,
    }
    connor = _summary(flags)["characters"][0]
    assert connor["sentence"] == (
        "Connor stayed a machine. He never died. His mission failed and his story ended."
    )


# --- Coordinating the attack (32.6) ---
# Wiki flowchart, Markus Revolution: "Reach Machine Gun → Coordinate Attack: Send North to
# her Death / Attack Successful / Attack Unsuccessful → Androids Have to Fall Back".
# Wiki, Markus: "If Markus commands North's group to charge without enough cover fire,
# he sends her to her death"; an unsuccessful attack gets Simon and North (below
# companion) shot, and Markus takes shelter in a CyberLife store.

REVOLUTION = {"ch31_1_00006": "REVOLUTION"}
COORDINATE = "ch32_6_x0101"
MACHINE_GUN = "ch32_6_00054"
ASSAULT_FAILED = "ch32_6_00038"


def test_coordinating_the_attack_is_a_choice_at_the_machine_gun():
    assert _nodes()[COORDINATE]["type"] == "choice"
    assert _nodes()[MACHINE_GUN]["next"] == COORDINATE
    assert _labels(COORDINATE) == ["COVER FIRE", "SEND NORTH'S GROUP", "FALL BACK"]
    send = _option(COORDINATE, "SEND NORTH'S GROUP")
    assert {"flag": "north_alive", "equals": True} in send["requires"]
    assert effect_flags(send)["north_alive"] is False


def test_covering_the_charge_wins_the_assault(tmp_path):
    run = play_story(tmp_path, REVOLUTION)
    assert run.labels[COORDINATE] == "COVER FIRE"
    assert ASSAULT_FAILED not in run.nodes
    assert run.flags["markus_revolution_won"] is True


def test_sending_north_in_without_cover_kills_her(tmp_path):
    run = play_story(tmp_path, {**REVOLUTION, COORDINATE: "SEND NORTH'S GROUP"})
    assert run.flags["north_alive"] is False
    assert run.flags["markus_revolution_won"] is True


def test_falling_back_fails_the_assault_and_reaches_the_store(tmp_path):
    run = play_story(tmp_path, {**REVOLUTION, COORDINATE: "FALL BACK"})
    assert ASSAULT_FAILED in run.nodes
    assert run.flags["markus_revolution_won"] is False
    assert STORE_WHO_IS_THERE in run.nodes
    # North is still alive here, so Simon is not the one shot falling back.
    assert run.flags["simon_alive"] is True
    assert run.flags["markus_alive"] is False  # the first store option is deadly
    routes = [e for e in run.events if e["type"] == "route"]
    summary = ending_summary(run.flags, routes, [], finished=True)
    assert summary["characters"][2]["sentence"] == (
        "Markus led a violent revolution. He died before it was over."
    )
    assert summary["world"]["sentence"].startswith("The revolution turned violent.")


def test_with_a_machine_connor_the_failed_assault_brings_him_to_the_store(tmp_path):
    run = play_story(tmp_path, {**MACHINE, **REVOLUTION, COORDINATE: "FALL BACK"})
    assert run.flags["north_alive"] is False  # not his lover: shot falling back
    assert CONNOR_SHOOT_OR_SPARE in run.nodes
    assert run.flags["markus_revolution_won"] is False


# Wiki flowchart: "Simon Gets Shot (if North died in Crossroads, Simon is still
# alive…)", "North Gets Shot (if North is still alive and status is below COMPANION)".
@pytest.mark.parametrize(
    "flags, deaths",
    [
        ({"north_alive": True, "markus_kissed_north": True}, {}),
        ({"north_alive": True, "markus_kissed_north": False}, {"north_alive": False}),
        ({"north_alive": False, "markus_kissed_north": False}, {"simon_alive": False}),
    ],
)
def test_falling_back_shoots_simon_only_when_north_is_dead(flags, deaths):
    node = _nodes()["ch32_6_x0148"]
    step = resolve("ch32_6_x0148", {"markus_barricade_kiss": False, **flags})
    idx = step.branch_index
    assert not step.assumed and idx is not None
    assert (node["branches"][idx].get("effects") or {}).get("flags", {}) == deaths


def test_detonating_in_front_of_connor_fails_his_mission():
    flags = effect_flags(_option("ch32_6_00024", "DETONATE THE BOMB"))
    assert flags["connor_story_ended"] is True
    assert flags["connor_mission_failed"] is True


@pytest.mark.parametrize("nid", ["ch32_5_x0117", "ch32_5_x0121", "ch32_6_x0130",
                                 "ch32_6_x0134", "ch32_6_x0136"])
def test_the_new_rule_nodes_say_what_they_approximate(nid):
    assert _nodes()[nid].get("note")


def test_the_second_detonator_choice_has_its_own_description():
    node = _nodes()["ch32_6_x0144"]
    assert node["description"] and node["description"] != node["heading"]


# Kara's camp, freed by a won demonstration: the Summary says so only for a won one.
def test_the_summary_names_the_demonstration_only_when_it_was_won():
    base = {"kara_alive": True, "kara_captured": True, "kara_escaped_camp": True,
            "kara_freed_by_markus": True}
    won = _summary({**base, "markus_peaceful": False,
                    "markus_demonstration_outcome": "won"})["characters"][1]
    revolution = _summary({**base, "markus_peaceful": True,
                           "markus_demonstration_outcome": "none"})["characters"][1]
    assert "demonstration" in won["sentence"]
    assert "Markus's androids freed her" in revolution["sentence"]
