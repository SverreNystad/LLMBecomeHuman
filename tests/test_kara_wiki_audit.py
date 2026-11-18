"""Kara's chapters, re-audited against the wiki's flowcharts (wiki audit round 2)."""

import pytest

from detroit_benchmark.dashboard import DETROIT_CHAPTER_TITLES
from detroit_benchmark.ending import ending_summary
from detroit_benchmark.engine import effect_flags
from tests.dataset import load_dataset, play_story, reachable, resolve
from tests.test_night_of_the_soul import NOBODY_SAVES_MARKUS

NODES = load_dataset()["nodes"]
GRAPH = load_dataset()


def reach(start: str, **flags) -> set[str]:
    return set(reachable(start, flags))


def option(nid: str, label: str) -> dict:
    return next(o for o in NODES[nid]["options"] if o["label"] == label)


def branch_taken(nid: str, **flags) -> dict:
    step = resolve(nid, flags)
    assert not step.assumed and step.branch_index is not None, (nid, flags)
    return NODES[nid]["branches"][step.branch_index]


CAPTURED = {"ch30_1_00055": "SURRENDER", "ch30_1_00052": "OBEY"}
REVOLUTION = {"ch31_1_00006": "REVOLUTION"}
FENCE = "ch32_2_00030"
CAMP_OUTCOME = "ch32_9_x0001"


# Kara's camp outcome waits for Markus's revolution (32.2 -> 32.6 -> 32.9).
def test_kara_waiting_in_the_camp_is_settled_after_markus_s_revolution(tmp_path):
    run = play_story(tmp_path, {**CAPTURED, **REVOLUTION, FENCE: "WAIT"})
    chapters = list(dict.fromkeys(run.chapters))
    assert chapters.index("32.2") < chapters.index("32.6") < chapters.index("32.9")
    assert "ch32_2_00007" in run.nodes  # "They're coming! They're coming!"
    assert run.flags["kara_awaiting_markus"] == "together"
    assert run.flags["kara_alive"] is True and run.flags["alice_alive"] is True
    assert run.flags["kara_freed_by_markus"] is True


def test_with_markus_dead_kara_s_camp_story_ends_in_32_2(tmp_path):
    # A peaceful Markus now settles the camp in 32.9 too (tests/test_kara_camp_peaceful.py).
    run = play_story(tmp_path, {**CAPTURED, **NOBODY_SAVES_MARKUS, FENCE: "WAIT"})
    assert run.flags["markus_alive"] is False
    assert "32.9" not in run.chapters
    assert run.flags["kara_alive"] is False and run.flags["alice_alive"] is False


WAITING = ["ch32_2_00010", "ch32_2_x0105", "ch32_2_x0102", "ch32_2_x0211"]


@pytest.mark.parametrize("nid", WAITING)
@pytest.mark.parametrize(
    "markus, pending",
    [
        ({"markus_peaceful": False, "markus_alive": True, "markus_left_jericho": False}, True),
        # A peaceful Markus can free the camp too, by winning his demonstration
        # (maintainers' decision, tests/test_kara_camp_peaceful.py).
        ({"markus_peaceful": True, "markus_alive": True, "markus_left_jericho": False}, True),
        ({"markus_alive": False, "markus_left_jericho": False}, False),
        # Banished from Jericho: North leads the attack, and it fails.
        ({"markus_alive": True, "markus_left_jericho": True}, False),
    ],
)
def test_32_2_waits_only_while_markus_still_leads_jericho(nid, markus, pending):
    taken = branch_taken(nid, **markus)
    assert ("kara_awaiting_markus" in effect_flags(taken)) is pending
    assert not str(NODES[nid].get("next") or "").startswith("ch32_9")


@pytest.mark.parametrize(
    "waiting, freed, kara, alice",
    [
        ("together", True, True, True),
        ("together", False, False, False),
        ("left_alice", True, True, True),
        ("left_alice", False, True, False),
        ("kara_died", True, False, True),
        ("kara_died", False, False, False),
        ("alice_died", True, True, False),
        ("alice_died", False, False, False),
    ],
)
def test_32_9_settles_kara_and_alice_from_markus_s_final_fate(waiting, freed, kara, alice):
    before = {"together": (True, True), "left_alice": (True, True),
              "kara_died": (False, True), "alice_died": (True, False)}[waiting]
    flags = {"kara_awaiting_markus": waiting, "markus_alive": freed,
             "markus_revolution_won": freed, "markus_demonstration_outcome": "none",
             "kara_alive": before[0], "alice_alive": before[1]}
    flags |= effect_flags(branch_taken(CAMP_OUTCOME, **flags))
    assert (flags["kara_alive"], flags["alice_alive"]) == (kara, alice)
    assert flags.get("kara_freed_by_markus", False) is (freed and kara and waiting != "left_alice")


def test_32_9_plays_after_markus_and_before_connor_s_last_segments():
    gate = NODES["final_x0920"]
    assert NODES["ch32_6_00001"]["next"] == "final_x0920"
    assert NODES["final_x0903"]["branches"][1]["next"] == "final_x0920"
    assert gate["next"] == "final_x0902"
    assert branch_taken("final_x0920", kara_awaiting_markus="together")["next"] == CAMP_OUTCOME
    assert NODES["ch32_9_x0009"]["next"] == "final_x0902"
    assert GRAPH["chapter_entries"]["32.9"] == CAMP_OUTCOME
    assert "32.9" in DETROIT_CHAPTER_TITLES
    assert all(n["character"] == "Kara" for n in NODES.values() if n["chapter"] == "32.9")


def test_the_ending_summary_says_markus_freed_kara():
    flags = {"kara_alive": True, "kara_captured": True, "kara_escaped_camp": True,
             "kara_freed_by_markus": True, "alice_alive": True}
    kara = ending_summary(flags, [], [], finished=True)["characters"][1]
    assert kara["outcome"] == "escaped" and kara["alice_with_her"] is True
    assert "Markus" in kara["sentence"]


# In line with Alice: Luther's farewell, the drone, Alice's stress and the diversion.
LUTHER_FAREWELL = "ch32_2_00033"


def test_luther_says_farewell_at_the_machine_only_if_kara_waits(tmp_path):
    waited = play_story(tmp_path / "wait", {**CAPTURED, FENCE: "WAIT"})
    fought = play_story(tmp_path / "fight", {**CAPTURED, FENCE: "PROTECT ALICE"})
    assert LUTHER_FAREWELL in waited.nodes and waited.flags["luther_alive"] is False
    assert LUTHER_FAREWELL not in fought.nodes and fought.flags["luther_alive"] is True
    assert "ch32_2_00026" in fought.nodes  # Luther escapes with them


def test_kara_wounded_by_the_drone_cannot_follow_alice_over_the_wire(tmp_path):
    run = play_story(tmp_path, {**CAPTURED, "ch32_2_x0214": "MOVE", FENCE: "PROTECT ALICE"})
    assert run.flags["kara_wounded_in_camp"] is True
    assert "ch32_2_x0224" in run.nodes
    assert run.flags["kara_alive"] is False
    assert run.flags["alice_alive"] is True and run.flags["luther_alive"] is True


@pytest.mark.parametrize(
    "answers, panics",
    [
        ({}, False),
        ({"ch32_2_00075": "TRUTH", "ch32_2_00069": "CALM DOWN"}, False),
        ({"ch32_2_00075": "TRUTH", "ch32_2_00069": "CALM DOWN", "ch32_2_00065": "POWERLESS"}, True),
    ],
)
def test_alice_panics_when_kara_fails_to_reassure_her_twice(tmp_path, answers, panics):
    run = play_story(tmp_path, {**CAPTURED, **answers})
    assert NODES["ch32_2_x0101"]["resolution"] == "rule"
    assert ("ch32_2_00053" in run.nodes) is panics


def test_kara_chooses_who_creates_the_diversion(tmp_path):
    run = play_story(tmp_path, {**CAPTURED, "ch32_2_x0226": "ASK LUTHER"})
    assert {"ASK JERRY", "ASK LUTHER"} <= set(run.offered("ch32_2_x0226"))
    assert "ASK RALPH" not in run.offered("ch32_2_x0226")
    assert "ch32_2_x0227" in run.nodes and run.flags["luther_alive"] is False
    assert "ch32_2_00039" not in run.nodes  # no Luther in line with Alice
    assert "ch32_2_x0206" not in NODES and "ch32_2_x0207" not in NODES
    assert option("ch32_2_x0226", "ASK RALPH")["requires"] == [
        {"flag": "ralph_attacked_connor", "equals": True},
        {"flag": "kara_ch32_ralph_killed", "equals": False},
    ]
    assert option("ch32_2_x0226", "ASK THE SCARRED ANDROID")["requires"] == [
        {"flag": "kara_freed_zlatkos_androids", "equals": True}
    ]


def test_only_the_android_kara_saved_thanks_her():
    assert "ch32_2_00137" in reach("ch32_2_x0230", kara_ch32_volunteered=True)
    assert "ch32_2_00137" not in reach("ch32_2_x0230", kara_ch32_volunteered=False)
    assert effect_flags(option("ch32_2_00202", "VOLUNTEER"))["kara_ch32_volunteered"] is True


def test_ralph_killed_by_the_drone_is_not_in_the_line():
    assert effect_flags(option("ch32_2_00145", "INSIST"))["kara_ch32_ralph_killed"] is True
    gone = reach("ch32_2_x0204", ralph_attacked_connor=True, kara_ch32_ralph_killed=True)
    assert "ch32_2_00085" not in gone
    assert "ch32_2_00085" in reach(
        "ch32_2_x0204", ralph_attacked_connor=True, kara_ch32_ralph_killed=False
    )


# Kara Leaving Detroit (32.1): the detour around the checkpoint.
SAVES = {"ch32_1_00358": "SAVE THE JERRYS", "ch32_1_00381": "SAVE THE JERRYS",
         "ch32_1_00405": "SAVE LUTHER"}
HURRIES = {nid: "KEEP GOING" for nid in SAVES}


@pytest.mark.parametrize("stopped, late", [(True, True), (False, False)])
def test_the_detour_makes_kara_late_only_if_she_stopped_to_save_someone(
    tmp_path, stopped, late
):
    run = play_story(tmp_path, {**(SAVES if stopped else HURRIES), "ch32_1_x0111": "TAKE THE DETOUR"})
    assert "ch32_1_x0112" in run.nodes and "ch32_1_00336" not in run.nodes
    assert ("ch32_1_00297" in run.nodes) is late


# Crossroads (30.1): failing the cabin fight on purpose spares the soldier.
CABIN = {"ch30_1_00067": "OPEN"}


@pytest.mark.parametrize("label, captured", [("FIGHT BACK", False), ("GIVE UP", True)])
def test_kara_decides_whether_to_fight_the_soldier_in_the_cabin(tmp_path, label, captured):
    run = play_story(tmp_path, {**CABIN, "ch30_1_00062": label})
    assert NODES["ch30_1_00062"]["type"] == "choice"
    assert "ch30_1_00062" in run.nodes
    assert ("32.2" in run.chapters) is captured
