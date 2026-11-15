"""Markus's dirty-bomb endings, the failed assault's store endings (32.6), and Carl's Fate.

Sources: the Battle for Detroit wiki flowchart and the Markus page (via the MediaWiki
API), and the game text of the Detroit Become Text transcript (press-dirty-bomb)."""

import pytest

from detroit_benchmark.engine import effect_flags, pick_branch
from detroit_benchmark.ending import ending_summary
from tests.dataset import load_dataset, play_story
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


def _reachable(start: str) -> set[str]:
    """Every node reachable from ``start`` inside its chapter, whatever the flags."""
    nodes, seen, todo = _nodes(), set(), [start]
    while todo:
        nid = todo.pop()
        if nid in seen or nid not in nodes:
            continue
        seen.add(nid)
        node = nodes[nid]
        if node["type"] == "chapter_exit":
            continue
        todo += [x["next"] for x in node.get("options", []) + node.get("branches", [])]
        todo.append(node.get("next"))
    return seen


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
    after = _reachable(_option(node_id, label)["next"])
    assert {"ch32_6_x0128", "ch32_6_x0133", STORE_WE_ARE_FREE} <= after


def test_putting_down_the_gun_does_not_end_the_story_alive():
    # The game keeps the soldiers outside: PUT DOWN returns to the choice, without
    # suicide this time, so every way out sets Markus's Fate or sets off the bomb.
    put_down = _option(STORE_SUICIDE, "PUT DOWN")
    assert put_down["next"] == AFTER_PUTTING_DOWN_THE_GUN
    assert effect_flags(put_down)["markus_store_put_down_gun"] is True
    assert "SUICIDE" not in _labels(AFTER_PUTTING_DOWN_THE_GUN)
    surrender = _option(AFTER_PUTTING_DOWN_THE_GUN, "SURRENDER")
    assert effect_flags(surrender)["markus_alive"] is False
    # Every way on from there ends the segment with a Fate or the bomb, never alive
    # in the store, and never back at the suicide choice.
    after = _reachable(AFTER_PUTTING_DOWN_THE_GUN)
    assert STORE_SUICIDE not in after and AFTER_GIVING_UP_THE_BOMB not in after
    assert STORE_WE_ARE_FREE in after


def test_a_decommissioned_connor_does_not_come_to_the_store():
    node = _nodes()[STORE_WHO_IS_THERE]
    flags = {"north_alive": False, "connor_deviant": False, "connor_story_ended": True}
    idx, _, _ = pick_branch(node, flags)
    assert node["branches"][idx]["next"] == "ch32_6_00032"  # Markus alone


def test_connor_sparing_markus_without_the_bomb_walks_away():
    # Wiki, Markus: "if Connor spares Markus he will walk away".
    assert _option(CONNOR_SHOOT_OR_SPARE, "SPARE")["next"] == AFTER_CONNOR
    node = _nodes()[AFTER_CONNOR]
    idx, _, _ = pick_branch(node, {"markus_took_detonator": False})
    assert idx is None and node["next"] == CONNOR_WALKS_AWAY
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
