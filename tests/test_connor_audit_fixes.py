"""Connor's chapters follow the wiki's flowcharts: Fates and deaths are recorded where
they happen, and options appear only when the game offers them."""

import pytest

from detroit_benchmark.engine import pick_branch
from tests.dataset import load_dataset, play_story

MACHINE = {"ch30_2_00097": "REMAIN A MACHINE", "ch30_2_00124": "REMAIN A MACHINE"}
HOSTILE_HANK = {"ch6_00134": "FIRM", "ch15_00018": "Chase Deviant"}
KAMSKI_GAVE_JERICHO = {"ch27_00024": "JERICHO LOCATION"}  # and Connor shot Chloe

# The Hostage
FINAL_DEMAND, MOVE_CLOSER_OR_GIVE_UP, BLUFF_NODE = "ch1_00019", "ch1_00024", "ch1_00028"
FINAL_PLEA, DANIEL_JUMPS_WITH_EMMA = "ch1_00009", "ch1_x0104"
WOUNDED_COP = "ch1_00063"
# The Interrogation
APPROACH, CONFESSION, BACK_TO_THE_CELL = "ch9_00095", "ch9_00058", "ch9_x0103"
NO_CONFESSION_GAVIN = "ch12_00148"
# The Nest, Public Enemy, Meet Kamski, Last Chance
EMMA_SAVED_LINE, EMMA_DIED_LINE = "ch15_00110", "ch15_00115"
COP_FROM_THE_HOSTAGE = "ch24_00098"
HANK_GREETS_A_RETURNING_CONNOR = "ch27_00106"
REACTIVATE_DANIEL = "ch29_00029"
# The Bridge and the tower
BRIDGE_TOPICS, PASSWORD = "ch22_00080", "ch32_4_00042"
RUSHED_RUSSIAN_ROULETTE = {"ch18_x0001": "WAIT FOR HANK"}
# The Nest: asking Hank about the highway needs a chase that morning (On the Run).
HIGHWAY_TOPIC = "ch15_00132"
KARA_UNSEEN: dict[str, str] = {}  # from the motel Kara reaches the train unseen
# Kara threatened Ralph in the squat, so he gives her away and Connor chases her.
CHASE_THEN_STOPPED = {
    "ch10_00109": "DON'T STEAL", "ch10_00039": "STAY", "ch13_00136": "THREATEN",
    "ch13_00009": "GIVE UP",
}
# Night of the Soul
HANKS_HOUSE_SUICIDE = "ch31_2_00048"
# Connor's Last Mission (32.3)
HANK_ON_THE_ROOF, ALLEN_OR_HANK = "ch32_3_00047", "ch32_3_00066"
ROOFTOP_TALK, LEAVE_OR_ATTACK = "ch32_3_00033", "ch32_3_00020"
SPARE_OR_KILL, ALLEN_FIGHT_OR_FLEE = "ch32_3_00015", "ch32_3_00052"
DODGE = "ch32_3_00013"
# The crowd at Markus's speech plays after his demonstration, in 32.8 (docs/adr/0004).
CROWD, ZEN_GARDEN = "ch32_3_00008", "ch32_3_x0101"
MARKUS_SPEAKS = {
    "ch26_00070": "REFUSE", "ch28_00014": "DISPERSE", "ch28_00018": "ABANDON",
    "ch28_00030": "RUN AWAY", "ch28_00035": "DISPERSE", "ch28_00040": "RUN AWAY",
    "ch28_00041": "DISPERSE", "ch28_00044": "DISPERSE",
    "ch30_3_x0110": "GO BACK TO JERICHO", "ch32_5_00076": "REFUSE DEAL",
    "ch32_5_00090": "REFUSE", "ch32_5_00093": "REFUSE", "ch32_5_00045": "SING",
}
# The rooftop deaths: a choice's option, or a Quick-Time Event's failure branch.
ROOFTOP_DEATHS = [
    ("ch32_3_00013", "DON'T DODGE"), ("ch32_3_00019", "LET HANK WIN"), ("ch32_3_00050", "LET THEM WIN"),
]
# Daniel jumps with Emma and Connor does not leap after them.
STAY_BACK = {"ch1_00005": "STAY BACK"}
# After a spilled drink Hank refuses Connor more time and the deviant is never found.
FOUND = {"ch6_00145": "BUY HIM ANOTHER DRINK"}


def death_ladder_at(graph: dict, nid: str) -> bool:
    """``nid`` adds one to Connor's Deaths, whatever the count was."""
    node = graph["nodes"][nid]
    for deaths in range(7):
        idx, _, _ = pick_branch(node, {"connor_deaths": deaths})
        if idx is None:
            return False
        if node["branches"][idx]["effects"]["flags"]["connor_deaths"] != deaths + 1:
            return False
    return True


# The Hostage


def test_moving_closer_after_daniels_warning_he_jumps_with_emma(tmp_path):
    run = play_story(
        tmp_path,
        {BLUFF_NODE: "BLUFF", MOVE_CLOSER_OR_GIVE_UP: "MOVE CLOSER", **STAY_BACK},
    )
    assert DANIEL_JUMPS_WITH_EMMA in run.nodes
    assert FINAL_PLEA not in run.nodes
    assert run.flags["emma_saved"] is False


def test_refusing_daniels_demand_he_jumps_with_emma(tmp_path):
    run = play_story(tmp_path, {FINAL_DEMAND: "REFUSE", **STAY_BACK})
    assert DANIEL_JUMPS_WITH_EMMA in run.nodes
    assert FINAL_PLEA not in run.nodes
    assert run.flags["emma_saved"] is False
    assert EMMA_DIED_LINE in run.nodes and EMMA_SAVED_LINE not in run.nodes


def test_a_saved_emma_is_remembered_in_the_nest(tmp_path):
    run = play_story(tmp_path, {})
    assert run.flags["emma_saved"] is True
    assert EMMA_SAVED_LINE in run.nodes and EMMA_DIED_LINE not in run.nodes


def test_shooting_daniel_with_the_hidden_gun_makes_the_news():
    plea = load_dataset()["nodes"][FINAL_PLEA]
    use_gun = next(o for o in plea["options"] if o["label"] == "USE GUN")
    assert use_gun["effects"]["news"]


@pytest.mark.parametrize("pick, saved", [("IGNORE", True), ("OBEY", False)])
def test_the_cop_connor_saved_thanks_him_in_public_enemy(tmp_path, pick, saved):
    run = play_story(tmp_path, {WOUNDED_COP: pick})
    assert (COP_FROM_THE_HOSTAGE in run.nodes) is saved


def test_daniel_who_shot_connor_remembers_it_in_last_chance():
    node = load_dataset()["nodes"][REACTIVATE_DANIEL]
    idx, _, _ = pick_branch(node, {"connor_daniel_final_plea": "convince"})
    assert node["branches"][idx]["condition_text"].startswith("Daniel killed Connor")


# The Interrogation


def test_giving_up_on_the_interrogation_gets_no_confession(tmp_path):
    run = play_story(tmp_path, {**FOUND, APPROACH: "GIVE UP"})
    assert CONFESSION not in run.nodes
    assert BACK_TO_THE_CELL in run.nodes
    assert NO_CONFESSION_GAVIN in run.nodes


# Cole's photo


def test_without_seeing_coles_photo_connor_cannot_name_him(tmp_path):
    run = play_story(tmp_path, RUSHED_RUSSIAN_ROULETTE)
    assert "PHOTO" not in run.offered(BRIDGE_TOPICS)
    assert "COLE" not in run.offered(PASSWORD)


def test_having_seen_coles_photo_connor_can_name_him(tmp_path):
    run = play_story(tmp_path, {})
    assert "PHOTO" in run.offered(BRIDGE_TOPICS)
    assert "COLE" in run.offered(PASSWORD)


# Meet Kamski


@pytest.mark.parametrize("deaths, line", [(1, "first time"), (2, "multiple"), (3, "multiple")])
def test_hank_greets_connor_by_how_often_he_died(deaths, line):
    node = load_dataset()["nodes"][HANK_GREETS_A_RETURNING_CONNOR]
    idx, _, _ = pick_branch(node, {"connor_deaths": deaths})
    assert line in node["branches"][idx]["condition_text"]


# Hank quitting the force


def test_a_hostile_hank_does_not_quit_when_kamski_gave_up_jericho(tmp_path):
    run = play_story(tmp_path, {**MACHINE, **HOSTILE_HANK, **KAMSKI_GAVE_JERICHO})
    assert run.flags["hank_quit_force"] is False
    assert HANKS_HOUSE_SUICIDE not in run.nodes
    assert HANK_ON_THE_ROOF in run.nodes


def test_a_hostile_hank_who_quit_is_replaced_by_allen_on_the_roof(tmp_path):
    run = play_story(tmp_path, {**MACHINE, **HOSTILE_HANK})
    assert run.flags["hank_quit_force"] is True
    assert HANK_ON_THE_ROOF not in run.nodes
    assert ALLEN_FIGHT_OR_FLEE in run.nodes


def test_allen_intervening_reads_as_a_sentence():
    node = load_dataset()["nodes"][ALLEN_OR_HANK]
    assert not any("{{" in b["condition_text"] for b in node["branches"])


# Connor's Last Mission: the rooftop


def test_connor_can_leave_the_rooftop_only_after_insisting_about_cole(tmp_path):
    plain = play_story(tmp_path / "a", MACHINE)
    insist = play_story(tmp_path / "b", {**MACHINE, ROOFTOP_TALK: "HANK'S SON (INSIST)"})
    assert "LEAVE" not in plain.offered(LEAVE_OR_ATTACK)
    assert "LEAVE" in insist.offered(LEAVE_OR_ATTACK)


def test_a_hostile_hank_cannot_talk_connor_off_the_rooftop(tmp_path):
    run = play_story(
        tmp_path,
        {**MACHINE, **HOSTILE_HANK, **KAMSKI_GAVE_JERICHO, ROOFTOP_TALK: "HANK'S SON (INSIST)"},
    )
    assert "LEAVE" not in run.offered(LEAVE_OR_ATTACK)


@pytest.mark.parametrize(
    "pick, dodge, hank_lives",
    [("KILL HANK", "DODGE", False), ("SAVE HANK", "DODGE", False),
     ("SAVE HANK", "DON'T DODGE", True)],
)
def test_hank_lives_on_the_rooftop_only_if_connor_spares_him_and_takes_the_fall(
    tmp_path, pick, dodge, hank_lives
):
    # Wiki: saved, Hank rushes Connor; dodging, Hank falls to his death.
    picks = {**MACHINE, LEAVE_OR_ATTACK: "ATTACK", SPARE_OR_KILL: pick, DODGE: dodge}
    run = play_story(tmp_path, picks)
    assert run.flags["hank_alive"] is hank_lives


def test_jumping_off_the_roof_from_allen_adds_a_death(tmp_path):
    fight = play_story(tmp_path / "a", {**MACHINE, **HOSTILE_HANK})
    flee = play_story(tmp_path / "b", {**MACHINE, **HOSTILE_HANK, ALLEN_FIGHT_OR_FLEE: "FLEE"})
    assert flee.flags["connor_deaths"] == fight.flags["connor_deaths"] + 1


@pytest.mark.parametrize("nid, outcome", ROOFTOP_DEATHS)
def test_every_rooftop_death_adds_one(nid, outcome):
    graph = load_dataset()
    node = graph["nodes"][nid]
    if node["type"] == "choice":
        nxt = next(o["next"] for o in node["options"] if o["label"] == outcome)
    else:
        nxt = node["branches"][outcome]["next"]
    assert death_ladder_at(graph, nxt)


# Connor's Last Mission: the crowd


def test_shooting_markus_in_the_crowd_ends_his_story(tmp_path):
    run = play_story(tmp_path, {**MACHINE, **MARKUS_SPEAKS, CROWD: "SHOOT"})
    assert run.flags["markus_alive"] is False
    assert "32.5" in run.chapters and run.chapters[-1] == "32.8"


def test_refusing_to_shoot_connor_can_escape_amanda_and_markus_lives(tmp_path):
    run = play_story(
        tmp_path,
        {**MACHINE, **MARKUS_SPEAKS, CROWD: "DON'T SHOOT",
         ZEN_GARDEN: "FIND THE EMERGENCY EXIT"},
    )
    assert run.flags["markus_alive"] is True


def test_without_a_chase_connor_never_asks_about_the_highway(tmp_path):
    run = play_story(tmp_path, KARA_UNSEEN)
    assert run.flags["kara_chased_by_connor"] is False
    assert "HIGHWAY" not in run.offered(HIGHWAY_TOPIC)


def test_stopped_at_the_highway_connor_can_ask_hank_why(tmp_path):
    run = play_story(tmp_path, CHASE_THEN_STOPPED)
    assert "HIGHWAY" in run.offered(HIGHWAY_TOPIC)


def test_giving_up_in_the_zen_garden_amanda_shoots_markus(tmp_path):
    run = play_story(
        tmp_path, {**MACHINE, **MARKUS_SPEAKS, CROWD: "DON'T SHOOT", ZEN_GARDEN: "GIVE UP"}
    )
    assert run.flags["markus_alive"] is False


# Public News: the Jericho raid is news once the army storms the freighter (30), not
# when Connor gives its location to Amanda in private (29).
RAID_NEWS = "Army and police storm deviant hideout aboard freighter in Detroit harbour"


def test_the_jericho_raid_is_news_only_once_it_happens(tmp_path):
    run = play_story(tmp_path, {**KAMSKI_GAVE_JERICHO, "ch29_00270": "JERICHO"})
    assert run.labels["ch29_00270"] == "JERICHO"
    first = next(
        e for e in run.events
        if e["type"] == "decision" and RAID_NEWS in e["input"].get("news", [])
    )
    assert str(first["chapter"]).startswith("30.")
