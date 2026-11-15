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
