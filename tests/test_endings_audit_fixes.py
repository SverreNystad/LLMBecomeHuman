"""Fixes from the audit of the endings: Final Routes, Fates and the Ending Summary."""

import pytest

from detroit_benchmark.engine import effect_flags, pick_branch
from tests.dataset import load_dataset, play_story
from tests.test_night_of_the_soul import MACHINE, NOBODY_SAVES_MARKUS

# Battle for Detroit 32.6: "Markus is dead: North is leading the revolution".
NORTH_LEADS = "ch32_6_00011"
NORTH_SHOT_BY_SOLDIERS = "ch32_6_x0114"
CONNOR_FACES_NORTH = "ch32_6_00002"
MARKUS_GONE = "final_x0903"


def _next(node_id: str, flags: dict) -> str:
    node = load_dataset()["nodes"][node_id]
    idx, _, unknown = pick_branch(node, flags)
    assert not unknown
    return node["branches"][idx]["next"] if idx is not None else node["next"]


def test_with_markus_dead_north_leads_the_revolution_and_falls(tmp_path):
    run = play_story(tmp_path, NOBODY_SAVES_MARKUS)
    assert run.flags["markus_alive"] is False
    assert "32.5" not in run.chapters
    assert NORTH_LEADS in run.nodes
    # A deviant Connor is not there to face her: the soldiers shoot her.
    assert NORTH_SHOT_BY_SOLDIERS in run.nodes
    assert run.flags["north_alive"] is False


def test_with_markus_dead_a_machine_connor_faces_north(tmp_path):
    run = play_story(tmp_path, {**MACHINE, **NOBODY_SAVES_MARKUS})
    assert NORTH_LEADS in run.nodes
    assert CONNOR_FACES_NORTH in run.nodes


@pytest.mark.parametrize(
    "flags",
    [
        {"markus_alive": False, "markus_left_jericho": False},
        {"markus_alive": True, "markus_left_jericho": True},
    ],
)
def test_north_leads_whenever_markus_is_gone_and_she_lives(flags):
    assert _next(MARKUS_GONE, {**flags, "north_alive": True}) == NORTH_LEADS
    assert _next(MARKUS_GONE, {**flags, "north_alive": False}) == "final_x0902"


def test_markus_at_hart_plaza_plays_his_own_segment():
    flags = {"markus_alive": True, "markus_left_jericho": False, "north_alive": True}
    assert _next(MARKUS_GONE, flags) == "route_markus_final"


def _reachable(start: str) -> set[str]:
    nodes, seen, todo = load_dataset()["nodes"], set(), [start]
    while todo:
        nid = todo.pop()
        if nid in seen or nodes[nid]["chapter"] != nodes[start]["chapter"]:
            continue
        seen.add(nid)
        node = nodes[nid]
        todo += [o["next"] for o in node.get("options", []) + node.get("branches", [])]
        todo += [node["next"]] if node.get("next") else []
    return seen


def _option(node_id: str, label: str) -> dict:
    options = load_dataset()["nodes"][node_id]["options"]
    return next(o for o in options if o["label"] == label)


def test_refusing_north_s_heart_markus_dies_and_the_revolution_fails():
    # Wiki: Refuse → "Markus Died and the Revolution Failed"; North leads only a
    # revolution Markus did not live to start.
    after = _reachable(_option("ch32_6_00068", "SACRIFICE SELF")["next"])
    assert "ch32_6_x0113" in after and NORTH_LEADS not in after


# The dirty bomb going off: "An Explosion Shakes Detroit" at the demonstration,
# "Markus (and North) Watched Detroit Burn" in the store.
@pytest.mark.parametrize(
    "node_id, label",
    [
        ("ch32_5_00045", "DIRTY BOMB"),
        ("ch32_6_00013", "PRESS"),
        ("ch32_6_00031", "DIRTY BOMB"),
        ("ch32_6_00024", "DETONATE THE BOMB"),
    ],
)
def test_every_detonation_records_the_dirty_bomb(node_id, label):
    assert effect_flags(_option(node_id, label))["markus_dirty_bomb_detonated"] is True


PEACEFUL_WITH_DETONATOR = {
    "ch26_00070": "REFUSE",
    "ch30_3_00171": "KEEP",
    "ch32_5_00076": "REFUSE DEAL",
    "ch32_5_00045": "DIRTY BOMB",
}


def test_the_bomb_at_the_demonstration_goes_off(tmp_path):
    run = play_story(tmp_path, PEACEFUL_WITH_DETONATOR)
    assert run.labels.get("ch32_5_00045") == "DIRTY BOMB"
    assert run.flags["markus_dirty_bomb_detonated"] is True


# Night of the Soul: "killed by Markus by choosing Don't Trust"; CyberLife sends
# another Connor.
def test_markus_killing_connor_counts_as_one_of_his_deaths(tmp_path):
    trusted = play_story(tmp_path / "trust", {"ch31_1_00041": "TRUST"})
    killed = play_story(tmp_path / "kill", {"ch31_1_00041": "DON'T TRUST"})
    assert killed.labels["ch31_1_00041"] == "DON'T TRUST"
    assert killed.flags["connor_deaths"] == trusted.flags["connor_deaths"] + 1


# Kara Captured: "Kara & Alice Escaped on Truck", or Markus frees the camp.
CAPTURED = {"ch30_1_00055": "SURRENDER", "ch30_1_00052": "OBEY"}
FENCE = "ch32_2_00030"


@pytest.mark.parametrize(
    "picks",
    [{FENCE: "PROTECT ALICE"}, {FENCE: "WAIT", "ch31_1_00006": "REVOLUTION"}],
)
def test_kara_who_gets_out_of_the_camp_is_recorded_as_escaped(tmp_path, picks):
    run = play_story(tmp_path, {**CAPTURED, **picks})
    assert run.flags["kara_captured"] is True and run.flags["kara_alive"] is True
    assert run.flags["kara_escaped_camp"] is True


KAMSKI_ENDING = {
    "connor_story_ended": True,
    "connor_knows_jericho": False,
    "kara_alive": False,
    "markus_alive": False,
    "markus_left_jericho": False,
    "hank_alive": True,
}


@pytest.mark.parametrize(
    "change, hank_dies",
    [
        ({}, True),
        ({"markus_alive": True, "markus_left_jericho": True}, True),
        ({"kara_alive": True}, False),
        ({"markus_alive": True}, False),
    ],
)
def test_hank_kills_himself_when_nobody_is_left(change, hank_dies):
    # Wiki (Hank Anderson): Connor deactivated for failing to find Jericho, Kara
    # dead, Markus dead or banned from Jericho: Hank shoots himself in the credits.
    nodes = load_dataset()["nodes"]
    gate = nodes["final_x0901"]
    idx, _, _ = pick_branch(gate, KAMSKI_ENDING)
    credits = nodes[gate["branches"][idx]["next"]]
    idx, _, unknown = pick_branch(credits, {**KAMSKI_ENDING, **change})
    assert not unknown
    flags = effect_flags(credits["branches"][idx]) if idx is not None else {}
    assert (flags.get("hank_alive") is False) is hank_dies
    assert (credits["branches"][idx]["next"] if idx is not None else credits["next"]) == MARKUS_GONE


def test_kara_s_skip_gates_say_her_story_ended_not_how():
    # Death, capture or leaving Alice also end Kara's story, not only Stormy Night.
    for nid, node in load_dataset()["nodes"].items():
        for branch in node.get("branches", []):
            if branch.get("when") == {"flag": "kara_story_ended", "equals": True}:
                assert "Todd killed Alice" not in branch["condition_text"], nid


def test_kara_recycled_in_the_camp_did_not_escape(tmp_path):
    run = play_story(tmp_path, {**CAPTURED, FENCE: "WAIT"})
    assert run.flags["kara_alive"] is False
    assert run.flags["kara_escaped_camp"] is False
