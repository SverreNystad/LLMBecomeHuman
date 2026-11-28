"""Only a revolution that wins frees Kara's camp, not merely a Markus who lives through 32.6."""

import pytest

from detroit_benchmark.engine import effect_flags
from tests.dataset import load_dataset, play_story, resolve

GRAPH = load_dataset()
NODES = GRAPH["nodes"]
CAPTURED = {"ch30_1_00055": "SURRENDER", "ch30_1_00052": "OBEY"}
REVOLUTION = {"ch31_1_00006": "REVOLUTION"}
FENCE = "ch32_2_00030"


def camp_branch(**flags) -> dict:
    step = resolve("ch32_9_x0001", flags)
    assert not step.assumed and step.branch_index is not None
    return NODES["ch32_9_x0001"]["branches"][step.branch_index]


def test_a_run_starts_with_no_revolution_won():
    assert GRAPH["initial_flags"]["markus_revolution_won"] is False


@pytest.mark.slow
def test_winning_the_assault_records_the_victory(tmp_path):
    run = play_story(tmp_path, {**CAPTURED, **REVOLUTION, FENCE: "WAIT"})
    assert "ch32_6_00039" in run.nodes  # "Assault successful"
    assert run.flags["markus_revolution_won"] is True
    assert run.flags["kara_freed_by_markus"] is True


@pytest.mark.parametrize(
    "waiting", ["together", "left_alice", "kara_died", "alice_died"]
)
def test_a_markus_who_survives_a_failed_assault_frees_nobody(waiting):
    taken = camp_branch(
        kara_awaiting_markus=waiting,
        markus_alive=True,
        markus_revolution_won=False,
        markus_demonstration_outcome="none",
    )
    assert not effect_flags(taken).get("kara_freed_by_markus")
    assert "nobody" in taken["condition_text"]
