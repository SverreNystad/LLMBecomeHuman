"""What happens at CyberLife Tower (32.4) carries on (#45)."""

import pytest

from tests.dataset import play_story

HOSTAGE, AFTER_SAVING, NEW_CONNOR = "ch32_4_00086", "ch32_4_00069", "ch32_4_00082"
SON = "ch32_4_00042"
HANK_DEAD_CHOICE = "ch32_4_00106"
FIGHT = "ch32_4_00066"
HOSTILE_HANK = {"ch6_00134": "FIRM", "ch15_00018": "Chase Deviant"}
ZEN_GARDEN = "32.7"


def outcome(run):
    return (
        run.flags["connor_androids_woke"],
        run.flags["connor_story_ended"],
        ZEN_GARDEN in run.chapters,
    )


def test_hank_knows_his_partner_and_the_androids_wake(tmp_path):
    run = play_story(tmp_path, {})
    assert FIGHT in run.nodes
    assert outcome(run) == (True, False, True)
    assert run.flags["hank_alive"] is True


def test_the_wrong_son_hank_kills_connor_and_the_androids_stay_dormant(tmp_path):
    run = play_story(tmp_path, {SON: "ANTHONY"})
    assert outcome(run) == (False, True, False)


def test_doing_nothing_the_new_connor_kills_connor(tmp_path):
    run = play_story(tmp_path, {AFTER_SAVING: "DO NOTHING"})
    assert outcome(run) == (False, True, False)


def test_interposing_starts_the_fight(tmp_path):
    run = play_story(tmp_path, {AFTER_SAVING: "INTERPOSE"})
    assert FIGHT in run.nodes


@pytest.mark.parametrize(
    "label, connor_dies", [("TRANSFER", False), ("STAND UP", True), ("SHOOT", True)]
)
def test_sacrificing_hank_the_androids_wake_whatever_happens_to_connor(
    tmp_path, label, connor_dies
):
    run = play_story(tmp_path, {HOSTAGE: "SACRIFICE HANK", NEW_CONNOR: label})
    assert run.flags["hank_alive"] is False
    assert outcome(run) == (True, connor_dies, not connor_dies)


@pytest.mark.parametrize("label, woke", [("TRANSFER", True), ("STAND UP", False)])
def test_without_hank_only_swapping_bodies_finishes_the_conversion(tmp_path, label, woke):
    run = play_story(tmp_path, {**HOSTILE_HANK, HANK_DEAD_CHOICE: label})
    assert HOSTAGE not in run.nodes
    assert outcome(run) == (woke, not woke, woke)


def test_the_media_credit_connor_only_if_the_androids_woke(tmp_path):
    peaceful_markus_succeeds = {
        "ch26_00070": "REFUSE",
        "ch28_00044": "DISPERSE",
        "ch28_00041": "DISPERSE",
        "ch30_3_x0110": "GO BACK TO JERICHO",
        "ch32_5_00076": "REFUSE DEAL",
        "ch32_5_00045": "SING",
    }
    woke = play_story(tmp_path / "a", peaceful_markus_succeeds)
    dormant = play_story(tmp_path / "b", {**peaceful_markus_succeeds, SON: "ANTHONY"})
    assert "ch32_5_00002" in woke.nodes
    assert "ch32_5_00002" not in dormant.nodes
