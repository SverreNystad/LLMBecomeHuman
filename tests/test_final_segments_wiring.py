"""Wiring between the Characters' last Chapter Segments after the wiki audit (ADR 0004)."""

import pytest

from detroit_benchmark.engine import effect_flags, pick_branch
from tests.dataset import load_dataset

NODES = load_dataset()["nodes"]

MACHINE_CONNOR_AT_THE_SPEECH = {
    "connor_deviant": False, "connor_story_ended": False, "markus_alive": True,
    "markus_left_jericho": False, "markus_peaceful": True, "markus_barricade_response": "sing",
}


def taken(nid: str, flags: dict) -> dict | None:
    idx, _, unknown = pick_branch(NODES[nid], flags)
    assert not unknown
    return None if idx is None else NODES[nid]["branches"][idx]


@pytest.mark.parametrize(
    "outcome, in_the_crowd",
    [("won", True), ("betrayed", False), ("died_with_his_people", False), ("free_in_the_debris", False)],
)
def test_connor_is_in_the_crowd_only_after_a_won_demonstration(outcome, in_the_crowd):
    branch = taken("final_x0910", {**MACHINE_CONNOR_AT_THE_SPEECH, "markus_demonstration_outcome": outcome})
    assert (branch is not None and branch["next"] == "ch32_8_x0101") is in_the_crowd


@pytest.mark.parametrize("before", range(0, 7))
def test_markus_defeating_connor_counts_as_one_of_connor_s_deaths(before):
    let_markus_win = next(o for o in NODES["ch32_6_x0119"]["options"] if o["label"] == "LET MARKUS WIN")
    counter = let_markus_win["next"]
    branch = taken(counter, {"connor_deaths": before})
    assert effect_flags(branch)["connor_deaths"] == before + 1
    assert branch["next"] == "ch32_6_00045"


def _scenes_from(nid: str) -> list[str]:
    seen = []
    while NODES[nid]["type"] == "scene":
        seen.append(nid)
        nid = NODES[nid]["next"]
    return seen + [nid]


@pytest.mark.parametrize("counter", ["ch32_3_x0104", "ch32_3_x0105", "ch32_3_x0106", "ch32_3_x0107"])
def test_a_connor_who_dies_on_the_rooftop_does_not_head_down_to_hart_plaza(counter):
    after = _scenes_from(NODES[counter]["branches"][0]["next"])
    assert "ch32_3_00010" not in after
    assert after[-1] == "ch32_3_00001"


def test_connor_can_let_captain_allen_win():
    fight = NODES["ch32_3_00050"]
    assert fight["type"] == "choice"
    let_win = next(o for o in fight["options"] if o["label"] == "LET THEM WIN")
    assert let_win["next"] == "ch32_3_x0106"  # Allen destroys Connor: Connor's Deaths +1


def test_markus_can_lose_the_final_fight_against_connor():
    control_markus = next(o for o in NODES["ch32_6_00046"]["options"] if o["label"] == "CONTROL MARKUS")
    fight = NODES[control_markus["next"]]
    assert fight["type"] == "choice"
    lose = next(o for o in fight["options"] if o["label"] == "LOSE THE FIGHT")
    assert effect_flags(lose)["markus_alive"] is False
    assert lose["next"] == "ch32_6_x0120"  # the revolution fails


def test_32_9_keeps_the_ids_of_the_nodes_moved_out_of_32_2():
    for nid in ["ch32_2_00007", "ch32_2_00017", "ch32_2_00020", "ch32_2_x0103", "ch32_2_x0106", "ch32_2_x0212"]:
        assert NODES[nid]["chapter"] == "32.9"
    assert not [nid for nid in NODES if nid.startswith("ch32_9_") and "_x0" not in nid]
