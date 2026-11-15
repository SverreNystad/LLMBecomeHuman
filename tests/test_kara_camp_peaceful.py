"""Kara's camp is freed by a peaceful win too (the maintainers' decision): a Markus who
wins his demonstration frees the Recall Center camp, as a revolution that wins does.
Luther, if he is in the camp, is freed with them. Alice's fear in the line is visible."""

import pytest

from detroit_benchmark.ending import ending_summary
from detroit_benchmark.engine import effect_flags, pick_branch
from tests.dataset import load_dataset, play_story
from tests.test_markus_endings import PEACEFUL, REFUSE_DEAL

GRAPH = load_dataset()
NODES = GRAPH["nodes"]
CAPTURED = {"ch30_1_00055": "SURRENDER", "ch30_1_00052": "OBEY"}
WIN = {**PEACEFUL, **REFUSE_DEAL, "ch32_5_00045": "SING"}
LOSE = {**REFUSE_DEAL, "ch32_5_00045": "SACRIFICE"}
FENCE = "ch32_2_00030"
CAMP_OUTCOME = "ch32_9_x0001"
PEACEFUL_FREEING = "ch32_9_x0010"
REVOLUTION_ARRIVES = "ch32_2_00007"  # "They're coming! They're coming!"
LUTHER_FREED = "ch32_9_x0015"
LEFT_ALICE = {"ch32_2_00202": "VOLUNTEER", "ch32_2_x0210": "CLIMB INTO THE TRUCK"}


def taken(nid: str, **flags) -> dict:
    idx, _, unknown = pick_branch(NODES[nid], flags)
    assert not unknown and idx is not None, (nid, flags)
    return NODES[nid]["branches"][idx]


WAITING = ["ch32_2_00010", "ch32_2_x0105", "ch32_2_x0102", "ch32_2_x0211"]


@pytest.mark.parametrize("nid", WAITING)
def test_32_2_waits_for_a_peaceful_markus_in_jericho(nid):
    peaceful = taken(nid, markus_peaceful=True, markus_alive=True, markus_left_jericho=False)
    assert "kara_awaiting_markus" in effect_flags(peaceful)
    gone = taken(nid, markus_peaceful=True, markus_alive=True, markus_left_jericho=True)
    assert "kara_awaiting_markus" not in effect_flags(gone)


def test_32_5_hands_over_to_kara_s_32_9_before_connor_s_last_segments():
    assert NODES["ch32_5_00001"]["next"] == "final_x0920"
    assert NODES["final_x0920"]["next"] == "final_x0902"
    assert NODES["ch32_9_x0009"]["next"] == "final_x0902"


def test_a_won_demonstration_frees_kara_and_alice(tmp_path):
    run = play_story(tmp_path, {**CAPTURED, **WIN, FENCE: "WAIT"})
    chapters = list(dict.fromkeys(run.chapters))
    assert chapters.index("32.2") < chapters.index("32.5") < chapters.index("32.9")
    assert "32.6" not in chapters
    for later in ("32.7", "32.8"):
        if later in chapters:
            assert chapters.index("32.9") < chapters.index(later)
    assert run.flags["markus_demonstration_outcome"] == "won"
    assert PEACEFUL_FREEING in run.nodes and REVOLUTION_ARRIVES not in run.nodes
    assert run.flags["kara_alive"] is True and run.flags["alice_alive"] is True
    assert run.flags["kara_freed_by_markus"] is True
    kara = ending_summary(run.flags, [], [], finished=True)["characters"][1]
    assert kara["outcome"] == "escaped" and kara["alice_with_her"] is True
    assert "demonstration" in kara["sentence"] and "androids freed" not in kara["sentence"]


def test_the_peaceful_freeing_is_heard_from_the_distance_and_nobody_is_destroyed():
    text = NODES[PEACEFUL_FREEING]["description"]
    assert "distance" in text and "Markus" in text
    assert "storm" not in text


def test_a_lost_demonstration_frees_nobody(tmp_path):
    run = play_story(tmp_path, {**CAPTURED, **LOSE, FENCE: "WAIT"})
    chapters = list(dict.fromkeys(run.chapters))
    assert chapters.index("32.5") < chapters.index("32.9")
    assert run.flags["kara_alive"] is False and run.flags["alice_alive"] is False
    assert not run.flags.get("kara_freed_by_markus")


@pytest.mark.parametrize(
    "outcome, freed",
    [("won", True), ("died_with_his_people", False), ("betrayed", False),
     ("died_protecting_his_people", False), ("free_in_the_debris", False)],
)
@pytest.mark.parametrize("waiting", ["together", "left_alice", "kara_died", "alice_died"])
def test_32_9_frees_the_camp_only_when_the_demonstration_is_won(waiting, outcome, freed):
    flags = {"kara_awaiting_markus": waiting, "markus_peaceful": True,
             "markus_alive": outcome in ("won", "free_in_the_debris"),
             "markus_revolution_won": False, "markus_demonstration_outcome": outcome,
             "kara_alive": waiting != "kara_died", "alice_alive": waiting != "alice_died"}
    branch = taken(CAMP_OUTCOME, **flags)
    flags |= effect_flags(branch)
    alice = waiting != "alice_died" and freed
    kara = waiting != "kara_died" and (freed or waiting == "left_alice")
    assert (flags["kara_alive"], flags["alice_alive"]) == (kara, alice)
    assert flags.get("kara_freed_by_markus", False) is (
        freed and waiting in ("together", "alice_died")
    )
    if freed:
        assert "storm" not in (NODES[branch["next"]].get("description") or "")


@pytest.mark.parametrize("violent", [True, False])
def test_luther_in_the_camp_is_freed_with_them(tmp_path, violent):
    picks = {**CAPTURED, **LEFT_ALICE, **({"ch31_1_00006": "REVOLUTION"} if violent else WIN)}
    run = play_story(tmp_path, picks)
    assert run.flags["kara_awaiting_markus"] == "left_alice"
    assert run.flags["alice_alive"] is True and run.flags["luther_alive"] is True
    assert LUTHER_FREED in run.nodes
    assert "Luther" in NODES[LUTHER_FREED]["description"]


def test_a_dead_luther_is_not_freed():
    after = taken("ch32_9_x0014", luther_alive=False)
    assert after["next"] == "ch32_9_x0009"
    assert taken("ch32_9_x0014", luther_alive=True)["next"] == LUTHER_FREED


# Alice's fear: the rule stays (two discouraging answers make her panic), and the
# scene after each answer shows how she takes it.
FRIGHTENING = [("ch32_2_00075", "TRUTH"), ("ch32_2_00069", "ORDER"), ("ch32_2_00065", "POWERLESS")]
SOOTHING = [("ch32_2_00075", "LIE"), ("ch32_2_00069", "CALM DOWN"),
            ("ch32_2_00065", "REASSURING"), ("ch32_2_00065", "OPTIMISTIC")]


def alice_s_reaction(choice: str, label: str) -> str:
    """The first narrated scene after an answer, before the story moves on."""
    nid = next(o for o in NODES[choice]["options"] if o["label"] == label)["next"]
    while NODES[nid]["type"] == "scene":
        if NODES[nid].get("description") and not NODES[nid]["dialogue"]:
            return NODES[nid]["description"]
        nid = NODES[nid]["next"]
    return ""


@pytest.mark.parametrize("choice, label", FRIGHTENING)
def test_alice_s_growing_fear_shows_after_a_frightening_answer(choice, label):
    text = alice_s_reaction(choice, label)
    assert "Alice" in text and ("afraid" in text or "fear" in text)


@pytest.mark.parametrize("choice, label", SOOTHING)
def test_alice_calms_after_a_soothing_answer(choice, label):
    text = alice_s_reaction(choice, label)
    assert "Alice" in text and "calm" in text


def test_the_reactions_lead_to_the_same_rule():
    rule = NODES["ch32_2_x0101"]
    assert rule["resolution"] == "rule" and len(rule["branches"]) == 2
    for choice, label in FRIGHTENING[2:] + SOOTHING[2:]:
        nid = next(o for o in NODES[choice]["options"] if o["label"] == label)["next"]
        assert NODES[NODES[nid]["next"]]["next"] == "ch32_2_x0101"


def test_the_checkpoint_shooting_sets_no_unused_flag():
    assert "kara_checkpoint_shooting" not in GRAPH["initial_flags"]
    for nid in ("ch32_1_00308", "ch32_1_00311"):
        shoot = next(o for o in NODES[nid]["options"] if o["label"] == "SHOOT")
        assert "kara_checkpoint_shooting" not in effect_flags(shoot)
        assert shoot["effects"]["news"]
