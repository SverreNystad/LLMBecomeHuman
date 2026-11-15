"""Gauge Feedback: the on-screen gauges a player sees move after a choice (The Hostage's
Probability of Success, the deviant's stress in The Interrogation) are shown to the model,
as a direction only, right after the choice that moved them. Also: Partners without the
timer approximation, and the CyberLife Tower elevator going the wrong way."""

import pytest

from detroit_benchmark.dashboard import _story_beat
from detroit_benchmark.engine import Runner, pick_branch, validate_graph
from tests.dataset import load_dataset, play_story, read_events

UP = {"gauge": "probability_of_success", "direction": "up"}
STRESS_DOWN_SHARPLY = {"gauge": "deviant_stress", "direction": "large_down"}


def _graph(option_feedback=None, branch_feedback=None, hints=None) -> dict:
    """Choice -> condition -> choice -> ending, all in one Chapter Segment."""
    first = {"flags": {"went": True}}
    if option_feedback is not None:
        first["feedback"] = option_feedback
    branch = {"when": {"flag": "went", "equals": True}, "next": "second"}
    if branch_feedback is not None:
        branch["effects"] = {"flags": {}, "feedback": branch_feedback}
    return {
        "metadata": {"fidelity": "verified_game_rules"},
        "start": "first",
        "nodes": {
            "first": {
                "id": "first", "type": "choice", "chapter": "1", "character": "Connor",
                "heading": "On the terrace", "description": "Daniel waits.",
                "options": [
                    {"id": "calm", "label": "CALM", "next": "rule", "effects": first,
                     "relation_hints": hints or []},
                ],
            },
            "rule": {
                "id": "rule", "type": "condition", "chapter": "1", "character": "Connor",
                "heading": "The deviant listens", "resolution": "rule",
                "source": "https://detroit-become-human.fandom.com/wiki/The_Hostage",
                "branches": [branch], "next": "second",
            },
            "second": {
                "id": "second", "type": "choice", "chapter": "1", "character": "Connor",
                "heading": "Final plea", "description": "What now?",
                "options": [{"id": "go", "label": "GO", "next": "end",
                             "effects": {"flags": {}}}],
            },
            "end": {"id": "end", "type": "ending", "chapter": "1", "description": "Done."},
        },
    }


def _decisions(run_dir):
    return [e for e in read_events(run_dir) if e["type"] == "decision"]


def test_the_next_prompt_shows_the_gauge_move_right_after_the_choice(tmp_path):
    Runner(_graph(option_feedback=[UP]), "mock", None, tmp_path / "run").run()
    first, second = _decisions(tmp_path / "run")
    segment = second["input"]["chapter_segment_so_far"]
    assert segment[-1]["your_choice"] == "CALM"
    assert segment[-1]["on_screen"] == ["Probability of success: up"]
    # The decision event records it for the dashboard, with its wording.
    assert first["feedback"] == [{**UP, "text": "Probability of success: up"}]


def test_a_condition_branch_can_move_a_gauge_too(tmp_path):
    Runner(
        _graph(branch_feedback=[STRESS_DOWN_SHARPLY]), "mock", None, tmp_path / "run"
    ).run()
    events = read_events(tmp_path / "run")
    condition = next(e for e in events if e["type"] == "condition")
    assert condition["feedback"][0]["text"] == "The deviant's stress: down sharply"
    segment = _decisions(tmp_path / "run")[1]["input"]["chapter_segment_so_far"]
    assert segment[-1] == {
        "at": "The deviant listens",
        "on_screen": ["The deviant's stress: down sharply"],
    }


def test_a_choice_without_feedback_adds_nothing_to_the_prompt(tmp_path):
    Runner(_graph(), "mock", None, tmp_path / "run").run()
    first, second = _decisions(tmp_path / "run")
    assert "on_screen" not in second["input"]["chapter_segment_so_far"][-1]
    assert "feedback" not in first


HANK_UP = [{"name": "RelationName.Hank", "direction": "RelationType.LargeUp"}]


def test_relationship_hints_stay_hidden_by_default(tmp_path):
    Runner(_graph(hints=HANK_UP), "mock", None, tmp_path / "run").run()
    second = _decisions(tmp_path / "run")[1]
    assert "on_screen" not in second["input"]["chapter_segment_so_far"][-1]


def test_relationship_hints_can_be_shown_through_the_same_feedback(tmp_path):
    Runner(
        _graph(option_feedback=[UP], hints=HANK_UP), "mock", None, tmp_path / "run",
        show_relationships=True,
    ).run()
    second = _decisions(tmp_path / "run")[1]
    assert second["input"]["chapter_segment_so_far"][-1]["on_screen"] == [
        "Probability of success: up",
        "Relationship with Hank: up sharply",
    ]


@pytest.mark.parametrize(
    "feedback, problem",
    [
        ([{"gauge": "hank_mood", "direction": "up"}], "unknown gauge"),
        ([{"gauge": "probability_of_success", "direction": "sideways"}], "direction"),
        ({"gauge": "probability_of_success", "direction": "up"}, "list"),
    ],
)
def test_the_validator_checks_feedback(feedback, problem):
    for graph in (_graph(option_feedback=feedback), _graph(branch_feedback=feedback)):
        report = validate_graph(graph)
        assert not report["valid"]
        assert any("feedback" in e and problem in e for e in report["errors"])


def test_well_formed_feedback_validates():
    assert validate_graph(_graph(option_feedback=[UP], branch_feedback=[UP]))["valid"]


def test_the_dashboard_story_carries_the_feedback_text():
    beat = _story_beat(
        {"type": "decision", "index": 3, "node_id": "n",
         "feedback": [{**UP, "text": "Probability of success: up"}]}
    )
    assert beat["feedback"] == ["Probability of success: up"]
    assert "feedback" not in _story_beat({"type": "decision", "index": 3, "node_id": "n"})


# The Hostage: the wiki's Probability of Success modifiers, shown as directions
# (6 points or more is "large").
# https://detroit-become-human.fandom.com/wiki/The_Hostage#Probability_Of_Success
HOSTAGE_GAUGE = {
    ("ch1_x0001", "INVESTIGATE THOROUGHLY"): "large_up",
    ("ch1_x0001", "CHECK KEY AREAS"): "up",
    ("ch1_x0003", "TAKE GUN"): "large_up",
    ("ch1_00078", "CALM"): "up",
    ("ch1_00078", "RELEASE HOSTAGE"): "down",
    ("ch1_00078", "REASSURE DANIEL"): "up",
    ("ch1_00078", "EMPATHIZE"): "down",
    ("ch1_00063", "IGNORE"): "down",
    ("ch1_00063", "OBEY"): "large_up",
    ("ch1_00058", "TRUTH"): "large_up",
    ("ch1_00050", "POSSIBLE CAUSE"): "large_up",
    ("ch1_00050", "EMMA AND YOU"): "large_up",
    ("ch1_00050", "REALISTIC"): "down",
    ("ch1_00050", "BLAMING"): "down",
    ("ch1_00050", "SYMPATHETIC"): "large_up",
    ("ch1_00050", "DEFECTIVE"): "down",
    ("ch1_00032", "ACCEPT"): "large_up",
    ("ch1_00028", "LAST CHANCE"): "large_down",
    ("ch1_00028", "TRUST"): "large_up",
    ("ch1_00028", "RATIONAL"): "large_down",
    ("ch1_00019", "COMPROMISE"): "large_up",
    ("ch1_00019", "REFUSE"): "large_down",
    ("ch1_00009", "REASSURE"): "large_up",
    ("ch1_00009", "TRUTH"): "large_down",
}
# The Interrogation: the wiki's stress modifiers (6 points or more is "large").
# https://detroit-become-human.fandom.com/wiki/The_Interrogation#Influencing_Carlos'_android's_stress
STRESS_GAUGE = {
    ("ch9_00123", "SHOW PHOTOS"): "up",
    ("ch9_00123", "WOUNDS"): "up",
    ("ch9_00123", "NAME"): "down",
    ("ch9_00118", "COMFORT"): "down",
    ("ch9_00118", "REASSURE"): "down",
    ("ch9_00118", "THREATEN"): "up",
    ("ch9_00118", "BLAME"): "up",
    ("ch9_00113", "SYMPATHIZE"): "down",
    ("ch9_00113", "THREATEN"): "up",
    ("ch9_00113", "TRUST"): "down",
    ("ch9_00113", "PROBE MEMORY"): "large_up",
    ("ch9_00106", "LIE"): "down",
    ("ch9_00106", "TRUTH"): "up",
    ("ch9_00102", "LIE"): "down",
    ("ch9_00102", "TRUTH"): "up",
    ("ch9_00095", "PRESSURE IT"): "large_up",
    ("ch9_00095", "PROBE ITS MEMORY"): "large_up",
    ("ch9_00061", "MAINTAIN PRESSURE"): "large_up",
    ("ch9_00061", "GIVE UP"): "large_down",
    ("ch9_00093", "UNDERSTANDING"): "large_down",
    ("ch9_00093", "THREATEN"): "large_up",
    ("ch9_00093", "ORDER"): "large_up",
    ("ch9_00089", "SYMPATHIZE"): "large_down",
    ("ch9_00089", "INDIFFERENT"): "large_up",
    ("ch9_00089", "COMFORT"): "large_down",
    ("ch9_00085", "PROTECT"): "large_down",
    ("ch9_00085", "TERRIFY"): "large_up",
    ("ch9_00085", "WARN"): "large_up",
}


def _gauge_moves(gauge: str, chapter: str) -> dict:
    moves = {}
    for nid, node in load_dataset()["nodes"].items():
        if node["chapter"] != chapter:
            continue
        for option in node.get("options", []):
            for item in (option.get("effects") or {}).get("feedback") or []:
                if item["gauge"] == gauge:
                    moves[(nid, option["label"])] = item["direction"]
    return moves


def test_the_hostage_shows_the_wikis_probability_of_success_moves():
    assert _gauge_moves("probability_of_success", "1") == HOSTAGE_GAUGE


def test_the_interrogation_shows_the_wikis_stress_moves():
    assert _gauge_moves("deviant_stress", "9") == STRESS_GAUGE


def _rising_settings(gauge: str, chapter: str) -> set:
    """Every (flag, value) set by an option the model sees raise the gauge."""
    graph = load_dataset()
    settings = set()
    for (nid, label), direction in _gauge_moves(gauge, chapter).items():
        if direction not in ("up", "large_up"):
            continue
        option = next(o for o in graph["nodes"][nid]["options"] if o["label"] == label)
        settings |= set(option["effects"]["flags"].items())
    return settings


def _required_settings(expr) -> set:
    if "flag" in expr:
        return {(expr["flag"], expr.get("equals", True))}
    if "not" in expr:
        return set()
    return set().union(*(_required_settings(x) for x in expr.get("all") or expr["any"]))


def test_every_factor_the_hostage_rule_counts_is_a_rise_the_model_saw():
    rule = load_dataset()["nodes"]["ch1_x0106"]
    counted = _required_settings(rule["branches"][0]["when"])
    rising = _rising_settings("probability_of_success", "1")
    assert counted - rising == set()


def test_the_stress_rule_follows_the_stress_the_model_saw():
    nodes = load_dataset()["nodes"]
    for nid, label in [("ch9_00095", "PROBE ITS MEMORY"), ("ch9_00061", "MAINTAIN PRESSURE")]:
        option = next(o for o in nodes[nid]["options"] if o["label"] == label)
        assert option["effects"]["flags"]["connor_deviant_stress_high"] is True
        assert STRESS_GAUGE[(nid, label)] == "large_up"
    backing_off = next(o for o in nodes["ch9_00061"]["options"] if o["label"] == "GIVE UP")
    assert backing_off["effects"]["flags"]["connor_deviant_stress_high"] is False
    # Only a rising stress pushes the deviant to self-destruct.
    idx, _, _ = pick_branch(nodes["ch9_00041"], {"connor_deviant_stress_high": True})
    assert nodes["ch9_00041"]["branches"][idx]["next"] == "ch9_00012"


EXPLORE, GUN, GUN_TALK, HELICOPTER, DEMAND, FINAL = (
    "ch1_x0001", "ch1_x0003", "ch1_00058", "ch1_00032", "ch1_00019", "ch1_00009",
)
COLD = {"ch1_00050": "REALISTIC", "ch1_00028": "LAST CHANCE", "ch1_00063": "IGNORE"}
TO_REASSURE = {EXPLORE: "INVESTIGATE THOROUGHLY", DEMAND: "COMPROMISE", FINAL: "REASSURE"}


@pytest.mark.parametrize(
    "picks, trusted",
    [
        # Taking the cop's gun raises the probability whether or not Connor lies about it.
        ({GUN: "TAKE GUN", GUN_TALK: "LIE", HELICOPTER: "ACCEPT"}, True),
        ({GUN: "TAKE GUN", GUN_TALK: "TRUTH", HELICOPTER: "REFUSE"}, True),
        ({GUN: "TAKE GUN", GUN_TALK: "LIE", HELICOPTER: "REFUSE"}, False),
        ({GUN: "LEAVE GUN", HELICOPTER: "ACCEPT"}, False),
    ],
    ids=["took-lied-dismissed", "took-honest", "took-lied", "left-dismissed"],
)
def test_the_cops_gun_counts_as_the_rise_the_model_saw(tmp_path, picks, trusted):
    run = play_story(tmp_path, {**TO_REASSURE, **COLD, **picks})
    assert run.labels[FINAL] == "REASSURE"
    assert ("ch1_00003" in run.nodes) is trusted


def test_a_played_hostage_prompt_shows_the_probability_moving(tmp_path):
    run = play_story(tmp_path, {"ch1_00078": "CALM"})
    decisions = [e for e in run.events if e["type"] == "decision"]
    calm_at = next(i for i, e in enumerate(decisions) if e["node_id"] == "ch1_00078")
    after = decisions[calm_at + 1]
    calm = [e for e in after["input"]["chapter_segment_so_far"] if e.get("your_choice") == "CALM"]
    assert calm[-1]["on_screen"] == ["Probability of success: up"]


# Partners: the text version has no timer, so Hank never runs out of patience; the drink
# only changes how friendly he is (wiki Partners#Notes: "If you run out of time").
BAR, LAST_NIGHT_TOPICS = "ch6_00145", "ch12_00066"
WRONG_ANSWER = {"ch6_00025": "…WITH THE BAT."}


def test_the_timer_approximation_is_gone():
    nodes = load_dataset()["nodes"]
    assert not {"ch6_x0103", "ch6_x0104", "ch6_x0105"} & set(nodes)
    assert nodes["ch6_00054"]["next"] == "ch6_00053"


@pytest.mark.parametrize("bar", ["SPILL HIS DRINK", "BUY HIM ANOTHER DRINK", "WAIT OUTSIDE"])
def test_hank_goes_to_the_house_whatever_happens_to_his_drink(tmp_path, bar):
    run = play_story(tmp_path, {BAR: bar})
    assert run.flags["connor_partners_found_deviant"] is True
    assert "9" in run.chapters
    assert "LAST NIGHT" not in run.offered(LAST_NIGHT_TOPICS)


def test_the_default_run_reaches_the_interrogation(tmp_path):
    run = play_story(tmp_path, {})
    assert run.labels[BAR] == "SPILL HIS DRINK"
    assert "ch9_00095" in run.nodes


def test_last_night_needs_a_spilled_drink_and_an_unsolved_case(tmp_path):
    spilled = play_story(tmp_path / "a", {BAR: "SPILL HIS DRINK", **WRONG_ANSWER})
    bought = play_story(tmp_path / "b", {BAR: "BUY HIM ANOTHER DRINK", **WRONG_ANSWER})
    assert spilled.flags["connor_partners_found_deviant"] is False
    assert "LAST NIGHT" in spilled.offered(LAST_NIGHT_TOPICS)
    assert "LAST NIGHT" not in bought.offered(LAST_NIGHT_TOPICS)


def test_the_drink_keeps_its_effect_on_hank():
    options = {o["label"]: o for o in load_dataset()["nodes"][BAR]["options"]}
    assert options["SPILL HIS DRINK"]["relation_hints"][0]["direction"].endswith("LargeDown")
    assert options["BUY HIM ANOTHER DRINK"]["relation_hints"][0]["direction"].endswith("LargeUp")


# Connor at the CyberLife Tower: the elevator climbs to level 31; the androids are on -49.
@pytest.mark.parametrize("where", ["ch32_4_00122", "ch32_4_x0101", "briefing"])
def test_the_elevator_is_going_the_wrong_way(where):
    graph = load_dataset()
    text = (
        graph["chapter_briefings"]["32.4"]
        if where == "briefing"
        else graph["nodes"][where]["description"]
    )
    assert "level 31" in text and "Floor -49" in text
    assert "up" in text and "top" in text
