"""Gauge Feedback: the on-screen gauges a player sees move after a choice (The Hostage's
Probability of Success, the deviant's stress in The Interrogation) are shown to the model
right after the choice that moved them, each line once. Also: Partners without the
timer approximation, and the CyberLife Tower elevator going the wrong way."""

import pytest

from detroit_benchmark.engine import Runner, effect_adds, score_move, validate_graph
from tests.dataset import load_dataset, play_story, read_events, story_moments

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
                "id": "first",
                "type": "choice",
                "chapter": "1",
                "character": "Connor",
                "heading": "On the terrace",
                "description": "Daniel waits.",
                "options": [
                    {
                        "id": "calm",
                        "label": "CALM",
                        "next": "rule",
                        "effects": first,
                        "relation_hints": hints or [],
                    },
                ],
            },
            "rule": {
                "id": "rule",
                "type": "condition",
                "chapter": "1",
                "character": "Connor",
                "heading": "The deviant listens",
                "resolution": "rule",
                "source": "https://detroit-become-human.fandom.com/wiki/The_Hostage",
                "branches": [branch],
                "next": "second",
            },
            "second": {
                "id": "second",
                "type": "choice",
                "chapter": "1",
                "character": "Connor",
                "heading": "Final plea",
                "description": "What now?",
                "options": [
                    {"id": "go", "label": "GO", "next": "end", "effects": {"flags": {}}}
                ],
            },
            "end": {
                "id": "end",
                "type": "ending",
                "chapter": "1",
                "description": "Done.",
            },
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


def test_relationship_hints_can_be_hidden(tmp_path):
    Runner(
        _graph(hints=HANK_UP), "mock", None, tmp_path / "run", show_relationships=False
    ).run()
    second = _decisions(tmp_path / "run")[1]
    assert "on_screen" not in second["input"]["chapter_segment_so_far"][-1]


def test_relationship_hints_can_be_shown_through_the_same_feedback(tmp_path):
    Runner(
        _graph(option_feedback=[UP], hints=HANK_UP),
        "mock",
        None,
        tmp_path / "run",
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


def test_the_dashboard_story_carries_the_feedback_text(tmp_path):
    Runner(_graph(option_feedback=[UP]), "mock", None, tmp_path / "runs" / "r").run()
    first, second = [
        m for m in story_moments(tmp_path / "runs", "1") if m["type"] == "decision"
    ]
    assert first["feedback"] == ["Probability of success: up"]
    assert "feedback" not in second


SOFTWARE_UP = {
    "name": "RelationName.SoftwareInstability",
    "direction": "RelationType.SmallUp",
}


def test_a_repeated_hint_flashes_once(tmp_path):
    hints = [SOFTWARE_UP, SOFTWARE_UP, *HANK_UP, SOFTWARE_UP]
    Runner(
        _graph(option_feedback=[UP, UP], hints=hints), "mock", None, tmp_path / "r"
    ).run()
    first = _decisions(tmp_path / "r")[0]
    assert [f["text"] for f in first["feedback"]] == [
        "Probability of success: up",
        "Software instability: up",
        "Relationship with Hank: up sharply",
    ]


@pytest.mark.slow
def test_use_gun_shows_software_instability_once(tmp_path):
    # USE GUN carries three identical arrows in the transcript data.
    run = play_story(
        tmp_path, {"ch1_x0003": "TAKE GUN", "ch1_00058": "LIE", "ch1_00019": "USE GUN"}
    )
    used = next(e for e in run.events if e.get("decision_key") == "ch1_00019:option_0")
    texts = [f["text"] for f in used["feedback"]]
    assert texts.count("Software instability: up") == 1


# The Hostage: the wiki's Probability of Success modifiers, shown as directions
# (6 points or more is "large").
# https://detroit-become-human.fandom.com/wiki/The_Hostage#Probability_Of_Success
HOSTAGE_GAUGE = {
    ("ch1_x0001", "INVESTIGATE THOROUGHLY"): "large_up",
    ("ch1_x0001", "CHECK KEY AREAS"): "large_up",  # +17: three clues.
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
    (
        "ch9_x0107",
        "PRESSURE IT",
    ): "large_up",  # The second approach, after convincing fails.
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
    """Every option's move of a gauge: authored, or from a Running Score's add."""
    graph = load_dataset()
    moves = {}
    for nid, node in graph["nodes"].items():
        if node["chapter"] != chapter:
            continue
        for option in node.get("options", []):
            for item in (option.get("effects") or {}).get("feedback") or []:
                if item["gauge"] == gauge:
                    moves[(nid, option["label"])] = item["direction"]
            for name, delta in effect_adds(option).items():
                score = graph["scores"][name]
                if score["gauge"] == gauge:
                    moves[(nid, option["label"])] = score_move(score, delta, 0)[
                        "direction"
                    ]
    return moves


def test_the_hostage_shows_the_wikis_probability_of_success_moves():
    assert _gauge_moves("probability_of_success", "1") == HOSTAGE_GAUGE


def test_the_interrogation_shows_the_wikis_stress_moves():
    copies = {
        "ch9_00093": "ch9_x0111",
        "ch9_00089": "ch9_x0115",
        "ch9_00085": "ch9_x0119",
    }
    second_convince = {
        (copies[nid], label): move
        for (nid, label), move in STRESS_GAUGE.items()
        if nid in copies
    }
    assert _gauge_moves("deviant_stress", "9") == {**STRESS_GAUGE, **second_convince}


@pytest.mark.slow
def test_a_played_hostage_prompt_shows_the_probability_moving(tmp_path):
    run = play_story(tmp_path, {"ch1_00078": "CALM"})
    decisions = [e for e in run.events if e["type"] == "decision"]
    calm_at = next(i for i, e in enumerate(decisions) if e["node_id"] == "ch1_00078")
    after = decisions[calm_at + 1]
    calm = [
        e
        for e in after["input"]["chapter_segment_so_far"]
        if e.get("your_choice") == "CALM"
    ]
    assert calm[-1]["on_screen"] == ["Probability of success: up"]


# Partners: whether Hank ends the search depends on how Connor treated him at the bar
# (tests/test_connor_wiki_audit.py covers the search itself).
BAR, LAST_NIGHT_TOPICS = "ch6_00145", "ch12_00066"
WRONG_ANSWER = {"ch6_00025": "…WITH THE BAT."}


@pytest.mark.slow
@pytest.mark.parametrize("bar", ["BUY HIM ANOTHER DRINK", "WAIT OUTSIDE"])
def test_without_a_spilled_drink_hank_goes_to_the_house(tmp_path, bar):
    run = play_story(tmp_path, {BAR: bar})
    assert run.flags["connor_partners_found_deviant"] is True
    assert "9" in run.chapters
    assert "LAST NIGHT" not in run.offered(LAST_NIGHT_TOPICS)


@pytest.mark.slow
def test_the_default_run_spills_the_drink_and_leaves_the_crime_unsolved(tmp_path):
    run = play_story(tmp_path, {})
    assert run.labels[BAR] == "SPILL HIS DRINK"
    assert run.flags["connor_partners_found_deviant"] is False
    assert "ch9_00095" not in run.nodes


@pytest.mark.slow
def test_last_night_needs_a_spilled_drink_and_an_unsolved_case(tmp_path):
    spilled = play_story(tmp_path / "a", {BAR: "SPILL HIS DRINK", **WRONG_ANSWER})
    bought = play_story(tmp_path / "b", {BAR: "BUY HIM ANOTHER DRINK", **WRONG_ANSWER})
    assert spilled.flags["connor_partners_found_deviant"] is False
    assert "LAST NIGHT" in spilled.offered(LAST_NIGHT_TOPICS)
    assert "LAST NIGHT" not in bought.offered(LAST_NIGHT_TOPICS)


def test_the_drink_keeps_its_effect_on_hank():
    options = {o["label"]: o for o in load_dataset()["nodes"][BAR]["options"]}
    assert options["SPILL HIS DRINK"]["relation_hints"][0]["direction"].endswith(
        "LargeDown"
    )
    assert options["BUY HIM ANOTHER DRINK"]["relation_hints"][0]["direction"].endswith(
        "LargeUp"
    )


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
