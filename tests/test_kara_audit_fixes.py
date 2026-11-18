"""Kara's chapters, checked against the game's flowcharts (Kara fidelity audit)."""

import pytest

from detroit_benchmark.engine import effect_flags
from tests.dataset import load_dataset, play_story, reachable

NODES = load_dataset()["nodes"]


def reach(start: str, **flags) -> set[str]:
    return set(reachable(start, flags))


def option(nid: str, label: str) -> dict:
    return next(o for o in NODES[nid]["options"] if o["label"] == label)


# On the Run (13)
TRAIN_REACHED, SPOTTED, PURSUIT = "ch13_x0303", "ch13_00028", "ch13_00023"
MOTEL_SEARCH = "ch13_x0301"
# Fugitives choices that send Kara to each shelter (see test_condition_resolution).
SHELTER_PICKS = {
    "motel": {},
    "car": {"ch10_00109": "DON'T STEAL", "ch10_00039": "LEAVE", "ch10_00013": "STAY HERE"},
}
SQUAT = {"ch10_00109": "DON'T STEAL", "ch10_00039": "STAY"}


@pytest.mark.parametrize("shelter", sorted(SHELTER_PICKS))
def test_sneaking_past_the_police_kara_reaches_the_train_unseen(tmp_path, shelter):
    run = play_story(tmp_path, SHELTER_PICKS[shelter])
    assert TRAIN_REACHED in run.nodes
    assert SPOTTED not in run.nodes and PURSUIT not in run.nodes
    assert run.flags["kara_chased_by_connor"] is False


def test_the_kara_model_never_decides_connor_s_motel_search():
    # Kara has already left room 28 when Hank and Connor reach it ("It's gone…").
    search = NODES[MOTEL_SEARCH]
    assert search["type"] == "condition" and search["resolution"] == "rule"
    assert PURSUIT not in {b["next"] for b in search["branches"]} | {search["next"]}
    assert TRAIN_REACHED in reach(MOTEL_SEARCH, kara_ch10_shelter="motel")


def test_kara_who_threatened_ralph_is_found_and_chased(tmp_path):
    run = play_story(tmp_path, {**SQUAT, "ch13_00136": "THREATEN"})
    assert PURSUIT in run.nodes and TRAIN_REACHED not in run.nodes
    assert run.flags["kara_chased_by_connor"] is True


def test_kara_found_in_the_squat_is_chased():
    assert PURSUIT in reach(option("ch13_x0101", "CHECK UNDER THE STAIRS")["next"])
    assert effect_flags(option("ch13_x0101", "CHECK UNDER THE STAIRS"))[
        "ralph_attacked_connor"
    ]


# Zlatko (17) and The Pirates' Cove (21): the news follows what happened.
CHASE_NEWS, ROBBERY_UNIFORM, ROBBERY_CLOTHES = "ch17_00079", "ch17_00076", "ch17_00077"


@pytest.mark.parametrize("chased", [True, False])
def test_the_chase_newsflash_plays_only_after_a_chase(chased):
    seen = reach("ch17_00080", kara_chased_by_connor=chased, kara_robbed_store=False)
    assert (CHASE_NEWS in seen) is chased


@pytest.mark.parametrize(
    "robbed, clothes, news",
    [(False, False, None), (True, False, ROBBERY_UNIFORM), (True, True, ROBBERY_CLOTHES)],
)
def test_the_robbery_newsflash_follows_the_store_robbery(robbed, clothes, news):
    seen = reach("ch17_00078", kara_robbed_store=robbed, kara_stole_clothes=clothes)
    assert {ROBBERY_UNIFORM, ROBBERY_CLOTHES} & seen == ({news} if news else set())


def test_robbing_the_store_at_gunpoint_is_remembered_and_reported():
    for nid, label in [("ch10_00132", "GUN"), ("ch10_00188", "THREATEN THE CLERK WITH THE GUN")]:
        chosen = option(nid, label)
        assert effect_flags(chosen)["kara_robbed_store"] is True
        assert chosen["effects"]["news"]
    for chosen in NODES["ch10_00228"]["options"]:
        assert effect_flags(chosen)["kara_robbed_store"] is False


@pytest.mark.parametrize("escape, news", [("fire", True), ("hide", False)])
def test_the_house_fire_news_plays_only_if_kara_set_the_fire(escape, news):
    assert ("ch21_00134" in reach("ch21_00135", kara_zlatko_escape=escape)) is news


def test_a_dead_todd_never_chases_kara_in_the_crossroads_flashback():
    # Kara took the gun (Todd died), then left it behind in the squat.
    seen = reach("ch30_1_00137", kara_todd_killed=True, kara_took_gun=False)
    assert "ch30_1_00136" not in seen
    assert "ch30_1_00136" in reach("ch30_1_00137", kara_todd_killed=False)


def test_the_motel_tv_reports_todd_dead_only_if_he_died():
    assert "ch13_00064" in reach("ch13_00069", kara_todd_killed=True)
    assert "ch13_00068" in reach("ch13_00069", kara_todd_killed=False)


# The Pirates' Cove (21): the shadows attack.
STANCE, REACTION = "ch21_x0201", "ch21_00019"


def test_kara_can_grab_the_gun_only_if_she_still_has_it():
    grab = option(STANCE, "GRAB THE GUN")
    assert grab["requires"] == [{"flag": "kara_took_gun", "equals": True}]
    assert {o["next"] for o in NODES[STANCE]["options"]} == {REACTION}
    assert NODES["ch21_00020"]["next"] == STANCE


def test_kara_fires_a_warning_shot_only_with_the_gun_in_hand():
    shot = option(REACTION, "SHOOT IN THE AIR")
    assert shot["requires"] == [{"flag": "kara_ch21_stance", "equals": "gun"}]
    stances = {effect_flags(o)["kara_ch21_stance"] for o in NODES[STANCE]["options"]}
    assert stances == {"gun", "stick", "shield", "fire"}


def test_the_ra9_topics_need_the_writing_seen_in_the_tavern():
    # rA9 DOUBTS follows rA9 (tests/test_unlock_requirements.py), so it needs it too.
    assert option("ch21_00036", "rA9")["requires"] == [
        {"not": {"flag": "kara_ch21_exploration", "equals": "rush"}}
    ]


# Battle for Detroit, Kara leaving Detroit (32.1)
SAVE_LUTHER = "ch32_1_00405"


def test_luther_left_behind_in_jericho_is_found_in_the_west_side():
    seen = reach("ch32_1_00428", connor_knows_jericho=True, luther_alive=True)
    assert SAVE_LUTHER in seen


def test_hurrying_past_luther_gets_him_executed():
    assert effect_flags(option(SAVE_LUTHER, "KEEP GOING"))["luther_alive"] is False
    assert "luther_alive" not in effect_flags(option(SAVE_LUTHER, "SAVE LUTHER"))


def test_luther_dies_distracting_the_soldiers_when_todd_reveals_them():
    luther_there = next(
        b
        for b in NODES["ch32_1_00239"]["branches"]
        if b["when"] == {"flag": "luther_alive", "equals": True}
    )
    assert effect_flags(luther_there)["luther_alive"] is False


def test_hiding_behind_luther_on_the_boat_kills_him():
    flags = effect_flags(option("ch32_1_00167", "Use Luther"))
    assert flags["luther_alive"] is False
    assert flags["luther_body_on_boat"] is True


def test_kara_can_cast_luther_overboard_only_if_his_body_is_aboard():
    assert option("ch32_1_00139", "PUT OVERBOARD")["requires"] == [
        {"flag": "luther_body_on_boat", "equals": True}
    ]
    for label in ("Accelerate", "Protect Alice", "Hide", "Plunge"):
        assert effect_flags(option("ch32_1_00167", label))["luther_body_on_boat"] is False
    for nid in ("ch32_1_00143", "ch32_1_00148", "ch32_1_00156"):
        (dies,) = NODES[nid]["branches"]
        assert effect_flags(dies) == {"luther_alive": False, "luther_body_on_boat": True}


def test_luther_shooting_at_the_checkpoint_is_public_news():
    news = option("ch32_1_00311", "SHOOT")["effects"]["news"]
    assert news == option("ch32_1_00308", "SHOOT")["effects"]["news"]


def test_luther_shooting_at_the_checkpoint_records_the_same_shooting_as_kara_s():
    # Nothing later in the transcript tells the two shootings apart.
    luther = effect_flags(option("ch32_1_00311", "SHOOT"))
    assert luther == effect_flags(option("ch32_1_00308", "SHOOT"))
    assert "luther_checkpoint_shooting" not in luther


# Kara Captured (32.2)
ENCLOSURE = "ch32_2_x0001"
LUTHER_SCENES = {"ch32_2_00127", "ch32_2_00119", "ch32_2_00087", "ch32_2_00039"}
# Their diversion scenes sit behind the ASK RALPH / ASK THE SCARRED ANDROID options,
# whose requirements tests/test_kara_wiki_audit.py checks.
RALPH_SCENES = {"ch32_2_00159", "ch32_2_00085"}
SCARRED_SCENES = {"ch32_2_00136", "ch32_2_00080"}


@pytest.mark.parametrize(
    "flag, scenes",
    [
        ("luther_alive", LUTHER_SCENES),
        ("ralph_attacked_connor", RALPH_SCENES),
        ("kara_freed_zlatkos_androids", SCARRED_SCENES),
    ],
)
@pytest.mark.parametrize("present", [True, False])
def test_luther_ralph_and_the_scarred_android_are_in_the_camp_only_if_they_can_be(
    flag, scenes, present
):
    seen = reach(ENCLOSURE, **{flag: present})
    assert scenes & seen == (scenes if present else set())


CAPTURED = {"ch30_1_00055": "SURRENDER", "ch30_1_00052": "OBEY"}
VOLUNTEER = {"ch32_2_00202": "VOLUNTEER"}
REVOLUTION = {"ch31_1_00006": "REVOLUTION"}


@pytest.mark.parametrize("revolution", [True, False])
def test_kara_can_leave_the_camp_on_the_truck_without_alice(tmp_path, revolution):
    picks = {**CAPTURED, **VOLUNTEER, "ch32_2_x0210": "CLIMB INTO THE TRUCK"}
    run = play_story(tmp_path, picks | (REVOLUTION if revolution else {}))
    assert run.flags["kara_left_alone"] is True
    assert run.flags["kara_alive"] is True
    assert run.flags["alice_alive"] is revolution
    assert "ch32_2_00188" not in run.nodes


def test_going_back_after_carrying_the_body_kara_returns_to_the_enclosure(tmp_path):
    run = play_story(tmp_path, {**CAPTURED, **VOLUNTEER, "ch32_2_x0210": "GO BACK"})
    assert "ch32_2_00188" in run.nodes
    assert not run.flags.get("kara_left_alone")
