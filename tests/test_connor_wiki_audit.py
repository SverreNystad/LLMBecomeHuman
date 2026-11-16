"""Connor's chapters checked against the wiki's flowcharts (second audit): Quick-Time
Events that are really decisions are choices, the crowd at Markus's speech plays after
his demonstration (docs/adr/0004), and hidden scores are flag rules."""

import pytest

from detroit_benchmark.dashboard import DETROIT_CHAPTER_TITLES, _flowchart_projection
from detroit_benchmark.engine import pick_branch
from tests.dataset import load_dataset, play_story_with_hank_given_time as play_story


MACHINE = {"ch30_2_00097": "REMAIN A MACHINE", "ch30_2_00124": "REMAIN A MACHINE"}
HOSTILE_HANK = {"ch6_00134": "FIRM", "ch15_00018": "Chase Deviant"}
# Markus survives a successful demonstration and gives his speech: no Molotov in Capitol
# Park and no violence in the Freedom March keep public opinion positive.
MARKUS_SPEAKS = {
    "ch26_00070": "REFUSE",
    "ch28_00014": "DISPERSE",
    "ch28_00018": "ABANDON",
    "ch28_00030": "RUN AWAY",
    "ch28_00035": "DISPERSE",
    "ch28_00040": "RUN AWAY",
    "ch28_00041": "DISPERSE",
    "ch28_00044": "DISPERSE",
    "ch30_3_x0110": "GO BACK TO JERICHO",
    "ch32_5_00076": "REFUSE DEAL",
    "ch32_5_00090": "REFUSE",
    "ch32_5_00093": "REFUSE",
    "ch32_5_00045": "SING",
}
MARKUS_TAKES_THE_DEAL = {"ch32_5_00076": "ACCEPT DEAL"}

# Connor's Last Mission (32.3): the rooftop
LEAVE_OR_ATTACK, FIGHT, SPARE_OR_KILL, DODGE = (
    "ch32_3_00020", "ch32_3_00019", "ch32_3_00015", "ch32_3_00013",
)
HANK_PUSHED_CONNOR, HANK_FELL = "ch32_3_00012", "ch32_3_x0108"
ALLEN_FIGHT = "ch32_3_00050"
ATTACK = {**MACHINE, LEAVE_OR_ATTACK: "ATTACK"}
# The crowd at Markus's speech (32.8)
CROWD_SEGMENT = "32.8"
CROWD, ZEN_GARDEN = "ch32_3_00008", "ch32_3_x0101"


def _index(chapters, chapter):
    return [i for i, c in enumerate(chapters) if c == chapter]


# The rooftop fight and the dodge are two separate choices.


def test_the_rooftop_fight_and_the_dodge_are_choices():
    nodes = load_dataset()["nodes"]
    assert [o["label"] for o in nodes[FIGHT]["options"]] == ["WIN THE FIGHT", "LET HANK WIN"]
    assert [o["label"] for o in nodes[DODGE]["options"]] == ["DODGE", "DON'T DODGE"]
    for nid in (FIGHT, DODGE):
        assert nodes[nid]["type"] == "choice"
        assert "resolution" not in nodes[nid]


def test_letting_hank_win_he_kills_connor_and_lives(tmp_path):
    base = play_story(tmp_path / "a", ATTACK)
    run = play_story(tmp_path / "b", {**ATTACK, FIGHT: "LET HANK WIN"})
    assert SPARE_OR_KILL not in run.nodes
    assert run.flags["hank_alive"] is True
    assert run.flags["connor_deaths"] == base.flags["connor_deaths"] + 1


def test_letting_hank_go_after_winning_kills_him(tmp_path):
    run = play_story(tmp_path, {**ATTACK, SPARE_OR_KILL: "KILL HANK"})
    assert run.flags["hank_alive"] is False


def test_saving_hank_then_dodging_his_rush_he_falls_to_his_death(tmp_path):
    base = play_story(tmp_path / "a", ATTACK)
    run = play_story(tmp_path / "b", {**ATTACK, SPARE_OR_KILL: "SAVE HANK", DODGE: "DODGE"})
    assert HANK_FELL in run.nodes
    assert run.flags["hank_alive"] is False
    assert run.flags["connor_deaths"] == base.flags["connor_deaths"]


def test_saving_hank_and_not_dodging_hank_pushes_connor_off(tmp_path):
    base = play_story(tmp_path / "a", ATTACK)
    run = play_story(
        tmp_path / "b", {**ATTACK, SPARE_OR_KILL: "SAVE HANK", DODGE: "DON'T DODGE"}
    )
    assert HANK_PUSHED_CONNOR in run.nodes
    assert run.flags["hank_alive"] is True
    assert run.flags["connor_deaths"] == base.flags["connor_deaths"] + 1


def test_connor_can_let_allen_s_men_win():
    node = load_dataset()["nodes"][ALLEN_FIGHT]
    assert node["type"] == "choice"
    assert {o["label"] for o in node["options"]} == {"WIN THE FIGHT", "LET THEM WIN"}


# The crowd at Markus's speech is its own segment, after Markus's demonstration.


def test_the_crowd_plays_after_markus_speaks(tmp_path):
    run = play_story(tmp_path, {**MACHINE, **MARKUS_SPEAKS})
    crowd, rooftop, markus = (
        _index(run.chapters, c) for c in (CROWD_SEGMENT, "32.3", "32.5")
    )
    assert crowd and rooftop and markus
    assert max(rooftop) < min(markus) < max(markus) < min(crowd)
    assert CROWD in run.nodes


def test_shooting_markus_in_the_crowd_ends_his_fate_after_his_speech(tmp_path):
    run = play_story(tmp_path, {**MACHINE, **MARKUS_SPEAKS, CROWD: "SHOOT"})
    assert "32.5" in run.chapters and "32.6" not in run.chapters
    assert run.flags["markus_alive"] is False
    assert run.chapters[-1] == CROWD_SEGMENT


@pytest.mark.parametrize(
    "exit_pick, markus_alive", [("FIND THE EMERGENCY EXIT", True), ("GIVE UP", False)]
)
def test_refusing_to_shoot_amanda_takes_over_unless_connor_escapes(
    tmp_path, exit_pick, markus_alive
):
    picks = {**MACHINE, **MARKUS_SPEAKS, CROWD: "DON'T SHOOT", ZEN_GARDEN: exit_pick}
    run = play_story(tmp_path, picks)
    assert run.flags["markus_alive"] is markus_alive


@pytest.mark.parametrize(
    "picks",
    [
        {**MACHINE, **MARKUS_TAKES_THE_DEAL},  # Perkins shoots Markus
        MARKUS_SPEAKS,  # a deviant Connor is at CyberLife Tower
        {**MACHINE, "ch31_1_00006": "REVOLUTION"},  # no demonstration
    ],
    ids=["markus-dead", "deviant-connor", "revolution"],
)
def test_no_crowd_without_markus_speaking_to_a_machine_connor(tmp_path, picks):
    run = play_story(tmp_path, picks)
    assert CROWD_SEGMENT not in run.chapters
    assert CROWD not in run.nodes


def test_the_rooftop_segment_no_longer_holds_the_crowd():
    graph = load_dataset()
    nodes = graph["nodes"]
    assert nodes[CROWD]["chapter"] == CROWD_SEGMENT
    assert nodes[ZEN_GARDEN]["chapter"] == CROWD_SEGMENT
    assert "ch32_3_00009" not in nodes
    assert graph["chapter_entries"][CROWD_SEGMENT] in nodes
    assert graph["chapter_briefings"][CROWD_SEGMENT]
    assert CROWD_SEGMENT in DETROIT_CHAPTER_TITLES
    for option in nodes[CROWD]["options"]:
        for item in option["effects"].get("news", []):
            assert "sniper" not in item["headline"]


def test_the_flowchart_lists_segments_in_story_order():
    chapters = _flowchart_projection(load_dataset(), complete=True, source="t")["chapters"]
    assert chapters.index("32.6") < chapters.index("32.7") < chapters.index("32.8")
    assert chapters[-1] == "final"


# The Interrogation: Chris intervenes when the deviant's stress stays below 70%.
APPROACH, PRESSED, CHRIS = "ch9_00095", "ch9_00061", "ch9_00040"
SELF_DESTRUCTS, SHOOTS_CONNOR = "ch9_00012", "ch9_x0101"


def test_maintaining_pressure_the_deviant_confesses_then_destroys_itself(tmp_path):
    run = play_story(
        tmp_path, {APPROACH: "PRESSURE IT", PRESSED: "MAINTAIN PRESSURE"}
    )
    assert "MAINTAIN PRESSURE" in run.offered(PRESSED)
    assert "ch9_00057" in run.nodes  # the confession
    assert SELF_DESTRUCTS in run.nodes and CHRIS not in run.nodes


def test_backing_off_after_pressure_chris_steps_in_and_it_shoots_connor(tmp_path):
    # Giving up the pressure leads back to the approaches (wiki flowchart): convincing
    # it then, with the stress at 52%, gets the confession, and Chris steps in.
    harsh = {"ch9_00123": "SHOW PHOTOS", "ch9_00118": "THREATEN", "ch9_00113": "THREATEN",
             "ch9_00106": "TRUTH", "ch9_00102": "TRUTH"}
    convince = {"ch9_x0109": "CONVINCE IT", "ch9_x0115": "INDIFFERENT", "ch9_x0119": "TERRIFY"}
    run = play_story(
        tmp_path,
        {**harsh, APPROACH: "PRESSURE IT", PRESSED: "GIVE UP", **convince, CHRIS: "GIVE UP"},
    )
    assert CHRIS in run.nodes
    assert SHOOTS_CONNOR in run.nodes
    assert run.flags["connor_died_in_interrogation"] is True


def test_probing_its_memory_the_deviant_destroys_itself(tmp_path):
    run = play_story(tmp_path, {APPROACH: "PROBE ITS MEMORY"})
    assert SELF_DESTRUCTS in run.nodes and CHRIS not in run.nodes


# Partners: whether Hank ends the search depends on how Connor treated him at the bar,
# not on how long Connor searches. After a spilled drink he refuses Connor more time.
BAR, SEARCH, LAST_NIGHT_TOPICS = "ch6_00145", "ch6_x0001", "ch12_00066"
HANK_REFUSES, UNSOLVED = "ch6_x0105", "ch6_x0101"


@pytest.mark.parametrize(
    "bar, search, unsolved",
    [
        ("SPILL HIS DRINK", "INVESTIGATE THOROUGHLY", True),
        ("SPILL HIS DRINK", "CHECK KEY EVIDENCE", True),
        ("BUY HIM ANOTHER DRINK", "INVESTIGATE THOROUGHLY", False),
        ("WAIT OUTSIDE", "INVESTIGATE THOROUGHLY", False),
    ],
)
def test_hank_refuses_more_time_after_a_spilled_drink(tmp_path, bar, search, unsolved):
    run = play_story(tmp_path, {BAR: bar, SEARCH: search})
    assert (HANK_REFUSES in run.nodes) is unsolved
    assert (UNSOLVED in run.nodes) is unsolved
    assert run.flags["connor_partners_found_deviant"] is not unsolved
    # Waiting for Hank: Connor can bring up last night only if the case went unsolved.
    assert ("LAST NIGHT" in run.offered(LAST_NIGHT_TOPICS)) is unsolved


# Connor at the CyberLife Tower: the elevator.
ELEVATOR, HACKED_ELEVATOR = "ch32_4_00122", "ch32_4_x0101"
GUARDS_AT_49, VOICE = "ch32_4_00112", "ch32_4_00120"


def test_hacking_the_elevator_camera_no_guards_wait_on_floor_49(tmp_path):
    run = play_story(tmp_path, {ELEVATOR: "HACK CAMERA", HACKED_ELEVATOR: "ATTACK GUARDS"})
    assert run.flags["connor_hacked_elevator_camera"] is True
    assert GUARDS_AT_49 not in run.nodes


def test_without_hacking_the_camera_guards_wait_on_floor_49(tmp_path):
    run = play_story(tmp_path, {ELEVATOR: "ATTACK GUARDS"})
    assert GUARDS_AT_49 in run.nodes


def test_reaching_level_31_connor_is_ambushed_and_the_androids_stay_dormant(tmp_path):
    run = play_story(tmp_path, {ELEVATOR: "DO NOTHING"})
    assert "ch32_4_x0102" in run.nodes
    assert VOICE not in run.nodes and "ch32_4_00108" not in run.nodes
    assert run.flags["connor_story_ended"] is True
    assert run.flags["connor_androids_woke"] is False


def test_connors_own_voice_fails_so_he_uses_the_guards(tmp_path):
    run = play_story(tmp_path, {ELEVATOR: "ATTACK GUARDS", VOICE: "CONNOR'S VOICE"})
    assert "ch32_4_00118" in run.nodes and "ch32_4_00117" in run.nodes
    assert "ch32_4_00108" in run.nodes


# The Hostage: REASSURE builds trust only with the Probability of Success at 80% or more.
EXPLORE, GUN, TERRACE, COP, TOPIC, HELICOPTER, PLEA, DEMAND, FINAL = (
    "ch1_x0001", "ch1_x0003", "ch1_00078", "ch1_00063", "ch1_00050",
    "ch1_00032", "ch1_00028", "ch1_00019", "ch1_00009",
)
LEAP = "ch1_00005"
TRUSTS, LEAPT, EMMA_FELL = "ch1_00003", "ch1_x0105", "ch1_x0104"
TO_REASSURE = {DEMAND: "COMPROMISE", FINAL: "REASSURE", GUN: "LEAVE GUN"}
WARM = {TOPIC: "SYMPATHETIC", HELICOPTER: "ACCEPT"}
COLD = {TOPIC: "REALISTIC", HELICOPTER: "REFUSE", PLEA: "LAST CHANCE", COP: "IGNORE"}


@pytest.mark.parametrize(
    "picks, trusted",
    [
        ({EXPLORE: "INVESTIGATE THOROUGHLY", **COLD, **WARM}, True),
        ({EXPLORE: "INVESTIGATE THOROUGHLY", **COLD, HELICOPTER: "ACCEPT"}, False),
        ({EXPLORE: "CHECK KEY AREAS", **COLD, **WARM}, False),
        # Probability of Success: 48+17+3+6+6-15+10+6+6+6 = 93 (LAST CHANCE instead of
        # TRUST would leave 79%, short of the 80% REASSURE needs).
        ({EXPLORE: "CHECK KEY AREAS", **COLD, **WARM, COP: "OBEY", PLEA: "TRUST"}, True),
        ({EXPLORE: "RUSH TO THE BALCONY", **WARM, COP: "OBEY", PLEA: "TRUST"}, False),
    ],
    ids=["thorough-two", "thorough-one", "key-two", "key-three", "rush"],
)
def test_reassuring_daniel_works_only_with_enough_trust(tmp_path, picks, trusted):
    run = play_story(tmp_path, {**TO_REASSURE, **picks})
    assert run.labels[FINAL] == "REASSURE"
    assert (TRUSTS in run.nodes) is trusted
    assert (LEAP in run.nodes) is not trusted


@pytest.mark.parametrize(
    "pick, emma_saved, deaths, scene",
    [("LEAP FOR EMMA", True, 1, LEAPT), ("STAY BACK", False, 0, EMMA_FELL)],
)
def test_when_daniel_jumps_connor_chooses_whether_to_leap_for_emma(
    tmp_path, pick, emma_saved, deaths, scene
):
    run = play_story(tmp_path, {DEMAND: "REFUSE", LEAP: pick})
    assert run.labels[LEAP] == pick
    assert scene in run.nodes
    assert run.flags["emma_saved"] is emma_saved
    assert run.flags["connor_died_in_hostage"] is (deaths == 1)


# Connor's Last Mission opens in the Zen Garden when Markus killed the deviant Connor
# (connor_killed_by_markus is set in Night of the Soul by the Markus agent's change).


@pytest.mark.parametrize("killed, opening", [(True, "ch32_3_x0109"), (False, "ch32_3_00066")])
def test_a_connor_markus_killed_is_replaced_in_the_zen_garden(killed, opening):
    node = load_dataset()["nodes"]["ch32_3_x0110"]
    idx, _, unknown = pick_branch(node, {"connor_killed_by_markus": killed})
    assert not unknown
    assert (node["branches"][idx]["next"] if idx is not None else node["next"]) == opening
