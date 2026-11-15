"""Running Scores and Joint Decisions.

Running Scores: The Hostage's Probability of Success and the deviant's stress in The
Interrogation are real numbers moved by the wiki's modifiers (effects.add) and compared
by rules (gte/lte/gt/lt), and the Gauge Feedback the model reads comes from the same
moves. Joint Decisions: the gun in Jericho's hold and the final fight in 32.6 are decided
with both Markus's and Connor's memories (ADR 0005). Relationship arrows are shown.
"""

from copy import deepcopy

import pytest

from detroit_benchmark.engine import Runner, pick_branch, validate_graph
from detroit_benchmark.visitor_estimate import _extreme_route
from tests.dataset import load_dataset, play_story, read_events, story_moments
from tests.test_crossroads import MACHINE_WITH_MARKUS
from tests.test_markus_wiki_audit import REVOLUTION
from tests.test_night_of_the_soul import MACHINE

STRESS = "connor_deviant_stress"
SCORES = {
    STRESS: {
        "gauge": "deviant_stress", "min": 0, "max": 100, "shown": "percent",
        "bands": [
            {"name": "too low", "max": 49},
            {"name": "optimal", "max": 70},
            {"name": "too high", "max": 100},
        ],
    },
    "odds": {"gauge": "probability_of_success", "min": 0, "max": 99},
}


def _scored_graph(first_add: dict, second_add: dict | None = None) -> dict:
    """A choice that moves scores, a rule comparing the stress, an ending each way."""
    return {
        "metadata": {"fidelity": "verified_game_rules"},
        "start": "first",
        "initial_flags": {STRESS: 35, "odds": 95},
        "scores": deepcopy(SCORES),
        "nodes": {
            "first": {
                "id": "first", "type": "choice", "chapter": "9", "character": "Connor",
                "heading": "Interrogate", "description": "The deviant waits.",
                "options": [{"id": "a", "label": "THREATEN", "next": "second",
                             "effects": {"flags": {}, "add": first_add}}],
            },
            "second": {
                "id": "second", "type": "choice", "chapter": "9", "character": "Connor",
                "heading": "Convince", "description": "Now?",
                "options": [{"id": "b", "label": "GO", "next": "rule",
                             "effects": {"flags": {}, "add": second_add or {}}}],
            },
            "rule": {
                "id": "rule", "type": "condition", "chapter": "9", "character": "Connor",
                "heading": "Convince", "resolution": "rule",
                "source": "https://detroit-become-human.fandom.com/wiki/The_Interrogation",
                "branches": [
                    {"when": {"flag": STRESS, "gte": 50, "lte": 70}, "next": "confess"},
                    {"when": {"any": [{"flag": STRESS, "lt": 50}, {"flag": STRESS, "gt": 70}]},
                     "next": "silent"},
                ],
            },
            "confess": {"id": "confess", "type": "ending", "chapter": "9", "description": "It talks."},
            "silent": {"id": "silent", "type": "ending", "chapter": "9", "description": "Silence."},
        },
    }


def _decisions(run_dir):
    return [e for e in read_events(run_dir) if e["type"] == "decision"]


def test_an_add_moves_the_score_and_the_model_reads_the_move(tmp_path):
    Runner(_scored_graph({STRESS: 27, "odds": 10}), "mock", None, tmp_path / "r").run()
    first, second = _decisions(tmp_path / "r")
    assert first["flags_after"][STRESS] == 62
    assert first["flags_after"]["odds"] == 99  # Capped at the score's max.
    assert second["input"]["chapter_segment_so_far"][-1]["on_screen"] == [
        "The deviant's stress: up sharply to 62% (optimal)",
        "Probability of success: up",  # The real change (+4), and no number.
    ]
    assert read_events(tmp_path / "r")[-1]["node_id"] == "confess"


@pytest.mark.parametrize("add, ending", [({STRESS: 4}, "silent"), ({STRESS: 40}, "silent"),
                                          ({STRESS: 15}, "confess")])
def test_a_rule_compares_the_score(tmp_path, add, ending):
    Runner(_scored_graph(add), "mock", None, tmp_path / "r").run()
    assert read_events(tmp_path / "r")[-1]["node_id"] == ending


def test_a_score_at_its_cap_is_worded_from_the_real_change(tmp_path):
    Runner(_scored_graph({STRESS: 65, "odds": 4}, {STRESS: 5, "odds": 10}), "mock", None,
           tmp_path / "r").run()
    first, second = _decisions(tmp_path / "r")
    assert second["flags_after"][STRESS] == 100 and second["flags_after"]["odds"] == 99
    # The hidden score didn't move, so nothing is said about it.
    assert [f["text"] for f in second["feedback"]] == [
        "The deviant's stress: stays at 100% (too high)"
    ]


def test_a_small_move_is_not_sharp_and_a_score_never_drops_below_its_min(tmp_path):
    Runner(_scored_graph({STRESS: -4}, {STRESS: -60}), "mock", None, tmp_path / "r").run()
    first, second = _decisions(tmp_path / "r")
    assert first["feedback"][0]["text"] == "The deviant's stress: down to 31% (too low)"
    assert second["flags_after"][STRESS] == 0


@pytest.mark.parametrize(
    "change, problem",
    [
        (lambda g: g["nodes"]["first"]["options"][0]["effects"]["add"].update(hank=1), "not a score"),
        (lambda g: g["nodes"]["first"]["options"][0]["effects"]["add"].update({STRESS: "4"}), "number"),
        (lambda g: g["initial_flags"].pop(STRESS), "starting value"),
        (lambda g: g["scores"][STRESS].update(gauge="mood"), "unknown gauge"),
        (lambda g: g["scores"][STRESS]["bands"].pop(), "bands"),
        (lambda g: g["nodes"]["rule"]["branches"][0]["when"].update(flag="hank"), "not a number"),
        (lambda g: g["nodes"]["rule"]["branches"][0]["when"].update(gte="50"), "needs a number"),
        (lambda g: g["nodes"]["first"]["options"][0]["effects"].update(
            feedback=[{"gauge": "deviant_stress", "direction": "up"}]), "comes from its add"),
        (lambda g: g["nodes"]["first"]["options"][0]["effects"].update(show=["odds"]),
         "shown as a percentage"),
    ],
)
def test_the_validator_checks_scores_adds_and_comparisons(change, problem):
    graph = _scored_graph({STRESS: 4})
    assert validate_graph(graph)["valid"]
    change(graph)
    report = validate_graph(graph)
    assert not report["valid"]
    assert any(problem in e for e in report["errors"]), report["errors"]


# --- The Hostage: https://detroit-become-human.fandom.com/wiki/The_Hostage#Probability_Of_Success
HOSTAGE_ADDS = {
    ("ch1_x0001", "INVESTIGATE THOROUGHLY"): 32,  # Every clue: 3+3+7+3+3+3+3+7.
    ("ch1_x0001", "CHECK KEY AREAS"): 17,  # The father, his tablet, Daniel's name.
    ("ch1_x0003", "TAKE GUN"): 7,
    ("ch1_00078", "CALM"): 3, ("ch1_00078", "RELEASE HOSTAGE"): -2,
    ("ch1_00078", "REASSURE DANIEL"): 3, ("ch1_00078", "EMPATHIZE"): -2,
    ("ch1_00063", "IGNORE"): -5, ("ch1_00063", "OBEY"): 6,
    ("ch1_00058", "TRUTH"): 6,
    ("ch1_00050", "POSSIBLE CAUSE"): 10, ("ch1_00050", "EMMA AND YOU"): 10,
    ("ch1_00050", "REALISTIC"): -2, ("ch1_00050", "BLAMING"): -5,
    ("ch1_00050", "SYMPATHETIC"): 6, ("ch1_00050", "DEFECTIVE"): -5,
    ("ch1_00032", "ACCEPT"): 10,
    ("ch1_00028", "LAST CHANCE"): -8, ("ch1_00028", "TRUST"): 6, ("ch1_00028", "RATIONAL"): -8,
    ("ch1_00019", "COMPROMISE"): 6, ("ch1_00019", "REFUSE"): -20,
    ("ch1_00009", "REASSURE"): 6, ("ch1_00009", "TRUTH"): -20,
}


def _adds(score: str, chapter: str) -> dict:
    found = {}
    for nid, node in load_dataset()["nodes"].items():
        if node["chapter"] != chapter:
            continue
        for option in node.get("options", []):
            delta = (option.get("effects") or {}).get("add", {}).get(score)
            if delta:
                found[(nid, option["label"])] = delta
    return found


def test_the_hostage_counts_every_wiki_modifier():
    graph = load_dataset()
    assert graph["initial_flags"]["connor_hostage_probability"] == 48
    assert graph["scores"]["connor_hostage_probability"]["max"] == 99
    assert _adds("connor_hostage_probability", "1") == HOSTAGE_ADDS
    helicopter = graph["nodes"]["ch1_x0107"]["branches"][0]
    assert helicopter["effects"]["add"] == {"connor_hostage_probability": -15}


EXPLORE, FINAL, TRUSTED = "ch1_x0001", "ch1_00009", "ch1_00003"


@pytest.mark.parametrize(
    "picks, odds, trusted",
    [
        # 48+32+7+3-5+0+10-15+10-8+6+6 = 94.
        ({"ch1_00019": "COMPROMISE"}, 94, True),
        # 48+17+3+6+10-15+10+6+6+6 = 97 (no gun: COMPROMISE comes first).
        ({EXPLORE: "CHECK KEY AREAS", "ch1_00063": "OBEY", "ch1_00028": "TRUST"}, 97, True),
        # 48+3-5+6-15+0-8+6+6 = 41: rushing, REASSURE falls short.
        ({EXPLORE: "RUSH TO THE BALCONY", "ch1_00050": "SYMPATHETIC",
          "ch1_00032": "REFUSE", "ch1_00028": "LAST CHANCE"}, 41, False),
        # 48+32+0+3-5-2-15+10-8+6+6 = 75.
        ({"ch1_x0003": "LEAVE GUN", "ch1_00050": "REALISTIC", "ch1_00028": "LAST CHANCE"}, 75, False),
    ],
    ids=["thorough", "key-areas", "rushed", "cold"],
)
def test_reassure_succeeds_at_80_percent(tmp_path, picks, odds, trusted):
    run = play_story(tmp_path, {**picks, FINAL: "REASSURE"})
    assert run.flags["connor_hostage_probability"] == odds
    assert (TRUSTED in run.nodes) is trusted
    assert run.flags["connor_daniel_probability_high"] is trusted


def test_the_hostage_shows_directions_never_numbers(tmp_path):
    run = play_story(tmp_path, {})
    lines = [
        line
        for e in run.events
        if e["type"] == "decision" and e["chapter"] == "1"
        for moment in e["input"]["chapter_segment_so_far"]
        for line in moment.get("on_screen", [])
        if line.startswith("Probability")
    ]
    assert "Probability of success: down sharply" in lines  # The helicopter.
    assert not any(ch.isdigit() for line in lines for ch in line)


def test_failing_to_negotiate_at_10_percent_needs_the_timer():
    """The wiki's other threshold (10% or less: Daniel jumps) can't be reached without the
    game's timer before a choice that already makes him jump (REFUSE, TRUTH, MOVE CLOSER):
    the worst start and every worst move before the car demand leave 13%."""
    worst = 48 + 0 - 2 - 5 - 5 - 15 - 8
    assert worst == 13 > 10


# --- The Interrogation:
# https://detroit-become-human.fandom.com/wiki/The_Interrogation#Influencing_Carlos'_android's_stress
STRESS_ADDS = {
    ("ch9_00123", "SHOW PHOTOS"): 4, ("ch9_00123", "WOUNDS"): 4, ("ch9_00123", "NAME"): -4,
    ("ch9_00118", "COMFORT"): -4, ("ch9_00118", "REASSURE"): -4,
    ("ch9_00118", "THREATEN"): 4, ("ch9_00118", "BLAME"): 4,
    ("ch9_00113", "SYMPATHIZE"): -4, ("ch9_00113", "THREATEN"): 4,
    ("ch9_00113", "TRUST"): -4, ("ch9_00113", "PROBE MEMORY"): 8,
    ("ch9_00106", "LIE"): -4, ("ch9_00106", "TRUTH"): 4,
    ("ch9_00102", "LIE"): -4, ("ch9_00102", "TRUTH"): 4,
    ("ch9_00095", "PRESSURE IT"): 10, ("ch9_x0107", "PRESSURE IT"): 10,
    ("ch9_00061", "GIVE UP"): -20, ("ch9_00061", "MAINTAIN PRESSURE"): 40,
    ("ch9_00093", "UNDERSTANDING"): -7, ("ch9_00093", "THREATEN"): 7, ("ch9_00093", "ORDER"): 7,
    ("ch9_00089", "SYMPATHIZE"): -7, ("ch9_00089", "INDIFFERENT"): 7, ("ch9_00089", "COMFORT"): -7,
    ("ch9_00085", "PROTECT"): -7, ("ch9_00085", "TERRIFY"): 7, ("ch9_00085", "WARN"): 7,
}


def _second_convince(table: dict) -> dict:
    """Convincing as the second approach, after pressure, has its own copy of the sets."""
    copies = {"ch9_00093": "ch9_x0111", "ch9_00089": "ch9_x0115", "ch9_00085": "ch9_x0119"}
    return {(copies[nid], label): v for (nid, label), v in table.items() if nid in copies}


def test_the_interrogation_counts_every_wiki_modifier():
    graph = load_dataset()
    assert graph["initial_flags"][STRESS] == 35
    assert _adds(STRESS, "9") == {**STRESS_ADDS, **_second_convince(STRESS_ADDS)}
    assert "connor_deviant_stress_high" not in graph["initial_flags"]
    probe = graph["nodes"]["ch9_00079"]["branches"][0]
    assert probe["effects"]["add"] == {STRESS: 100}


HARSH = {"ch9_00123": "SHOW PHOTOS", "ch9_00118": "THREATEN", "ch9_00113": "THREATEN",
         "ch9_00106": "TRUTH", "ch9_00102": "TRUTH"}  # 35+4+4+4+4+4 = 55.
CONVINCE = {"ch9_00095": "CONVINCE IT", "ch9_00089": "INDIFFERENT", "ch9_00085": "TERRIFY"}
CONFESSION, CHRIS, SELF_DESTRUCT = "ch9_00058", "ch9_00040", "ch9_00012"
SECOND_APPROACH, CELL = "ch9_x0107", "ch9_x0103"


def test_convincing_in_the_optimal_band_gets_a_confession(tmp_path):
    run = play_story(tmp_path, {**HARSH, **CONVINCE})  # 55-7+7+7 = 62.
    assert run.flags[STRESS] == 62
    assert CONFESSION in run.nodes and CHRIS in run.nodes
    assert SECOND_APPROACH not in run.nodes
    assert run.flags["connor_interrogation_approach"] == "convince"


def test_a_kind_interrogation_leaves_the_stress_too_low_to_convince(tmp_path):
    # 35-4-4-4-4 = 19, then -7 three times: 0%.
    run = play_story(tmp_path, {"ch9_00095": "CONVINCE IT", SECOND_APPROACH: "GIVE UP"})
    assert run.flags[STRESS] == 0
    assert CONFESSION not in run.nodes and CELL in run.nodes
    assert run.offered(SECOND_APPROACH) == ["PRESSURE IT", "PROBE ITS MEMORY", "GIVE UP"]


def test_the_model_reads_the_stress_with_its_band(tmp_path):
    run = play_story(tmp_path, {**HARSH, **CONVINCE})
    last = [e for e in run.events if e["type"] == "decision" and e["chapter"] == "9"][-1]
    lines = [
        line
        for moment in last["input"]["chapter_segment_so_far"]
        for line in moment.get("on_screen", [])
    ]
    assert lines[:2] == ["The deviant's stress: 35% (too low)",
                         "The deviant's stress: up to 39% (too low)"]
    assert "The deviant's stress: up sharply to 62% (optimal)" in lines


@pytest.mark.parametrize(
    "picks, ending, stress",
    [
        ({"ch9_00095": "PRESSURE IT", "ch9_00061": "MAINTAIN PRESSURE"}, SELF_DESTRUCT, 69),
        # 55+10-20 = 45, then the second approach: -7+7+7 = 52%, optimal.
        ({**HARSH, "ch9_00095": "PRESSURE IT", "ch9_00061": "GIVE UP",
          "ch9_x0109": "CONVINCE IT", "ch9_x0115": "INDIFFERENT", "ch9_x0119": "TERRIFY"},
         CHRIS, 52),
        ({"ch9_00095": "PROBE ITS MEMORY"}, SELF_DESTRUCT, 100),
    ],
    ids=["pressed-to-the-end", "pressure-then-back-off", "probed"],
)
def test_the_stress_decides_between_chris_and_self_destruction(tmp_path, picks, ending, stress):
    run = play_story(tmp_path, picks)
    assert run.flags[STRESS] == stress
    other = CHRIS if ending == SELF_DESTRUCT else SELF_DESTRUCT
    assert ending in run.nodes and other not in run.nodes


# --- Joint Decisions (ADR 0005) -----------------------------------------------------
def _joint_graph() -> dict:
    """Markus's segment, then Connor's with a Joint Decision, then Markus's again."""
    def scene(nid, character, chapter, nxt):
        return {"id": nid, "type": "scene", "chapter": chapter, "character": character,
                "heading": f"{character} {chapter}", "description": "", "next": nxt}

    def exit_(nid, character, chapter, nxt):
        return {"id": nid, "type": "chapter_exit", "chapter": chapter,
                "character": character, "next": nxt}

    return {
        "metadata": {"fidelity": "verified_game_rules"},
        "start": "m1",
        "nodes": {
            "m1": scene("m1", "Markus", "1", "m1x"),
            "m1x": exit_("m1x", "Markus", "1", "c2"),
            "c2": scene("c2", "Connor", "2", "gun"),
            "gun": {
                "id": "gun", "type": "choice", "chapter": "2", "character": "Connor",
                "heading": "In the hold", "description": "Both lunge for the gun.",
                "deciders": ["Markus", "Connor"],
                "decider_context": {"Markus": "Connor draws on Markus in the hold."},
                "options": [{"id": "reach", "label": "REACH THE GUN FIRST", "next": "c2x",
                             "effects": {"flags": {}}}],
            },
            "c2x": exit_("c2x", "Connor", "2", "m3"),
            "m3": {
                "id": "m3", "type": "choice", "chapter": "3", "character": "Markus",
                "heading": "After", "description": "Now what?",
                "options": [{"id": "go", "label": "GO", "next": "m3x", "effects": {"flags": {}}}],
            },
            "m3x": exit_("m3x", "Markus", "3", "end"),
            "end": {"id": "end", "type": "ending", "chapter": "3", "description": "Done."},
        },
    }


def _play_joint(tmp_path):
    Runner(_joint_graph(), "mock", None, tmp_path / "r").run()
    return read_events(tmp_path / "r")


def test_a_joint_decision_carries_both_memories_and_both_views(tmp_path):
    events = _play_joint(tmp_path)
    gun = next(e for e in events if e["node_id"] == "gun")
    payload = gun["input"]
    assert "character_memory" not in payload and "chapter_segment_so_far" not in payload
    assert "Markus and Connor" in payload["joint_decision"]
    views = payload["points_of_view"]
    assert views["Markus"]["character_memory"].startswith("Chapter 1")
    assert views["Markus"]["this_moment"] == "Connor draws on Markus in the hold."
    assert views["Connor"]["character_memory"] == ""
    assert views["Connor"]["chapter_segment_so_far"][0]["scene_id"] == "c2"
    assert gun["deciders"] == ["Markus", "Connor"]


def test_the_other_decider_learns_the_outcome(tmp_path):
    events = _play_joint(tmp_path)
    after = next(e for e in events if e["node_id"] == "m3")
    learned = after["input"]["chapter_segment_so_far"][0]
    assert learned["decided"] == "Decided with Markus's and Connor's memories"
    assert learned["your_choice"] == "REACH THE GUN FIRST" and learned["chapter"] == "2"
    updates = [e for e in events if e["type"] == "memory_update"]
    markus_after = updates[-1]
    assert markus_after["character"] == "Markus"
    assert markus_after["input"]["chapter_segment"][0] == learned
    assert "REACH THE GUN FIRST" in markus_after["memory"]
    # Connor remembers it as his own segment's choice, once.
    connor = updates[1]
    assert [m.get("your_choice") for m in connor["input"]["chapter_segment"]
            if "your_choice" in m] == ["REACH THE GUN FIRST"]


@pytest.mark.parametrize(
    "change, problem",
    [
        (lambda n: n.update(deciders=["Connor"]), "one other Character"),
        (lambda n: n.update(deciders=[]), "one other Character"),
        (lambda n: n.update(deciders=["Markus", "Kara"]), "including its own"),
        (lambda n: n.update(deciders=["Markus", "Connor", "Hank"]), "including its own"),
        (lambda n: n.update(decider_context={}), "no decider_context"),
        (lambda n: n.update(deciders=["Markus"], decider_context={}), "no decider_context"),
    ],
)
def test_the_validator_checks_deciders(change, problem):
    graph = _joint_graph()
    assert validate_graph(graph)["valid"]
    change(graph["nodes"]["gun"])
    report = validate_graph(graph)
    assert any(problem in e for e in report["errors"]), report["errors"]


def test_the_story_says_whose_memories_decided(tmp_path):
    Runner(_joint_graph(), "mock", None, tmp_path / "runs" / "r").run()
    (gun,) = [m for m in story_moments(tmp_path / "runs", "2") if m["type"] == "decision"]
    assert gun["decided"] == "Decided with Markus's and Connor's memories"
    assert gun["deciders"] == ["Markus", "Connor"]
    (alone,) = [m for m in story_moments(tmp_path / "runs", "3") if m["type"] == "decision"]
    assert "decided" not in alone and "deciders" not in alone


def _markus_alone_graph() -> dict:
    """The gun in Connor's segment is Markus's decision alone."""
    graph = _joint_graph()
    graph["nodes"]["gun"]["deciders"] = ["Markus"]
    return graph


def test_a_cross_segment_decision_carries_only_the_deciders_memory(tmp_path):
    Runner(_markus_alone_graph(), "mock", None, tmp_path / "r").run()
    events = read_events(tmp_path / "r")
    gun = next(e for e in events if e["node_id"] == "gun")
    payload = gun["input"]
    assert payload["current_scene"]["character"] == "Markus"
    assert payload["character_memory"].startswith("Chapter 1")  # Markus's, from chapter 1.
    assert payload["this_moment"] == "Connor draws on Markus in the hold."
    assert not {"chapter_segment_so_far", "points_of_view", "joint_decision"} & set(payload)
    assert gun["deciders"] == ["Markus"]


def test_the_segments_character_learns_what_the_other_decided(tmp_path):
    Runner(_markus_alone_graph(), "mock", None, tmp_path / "r").run()
    events = read_events(tmp_path / "r")
    connor, markus = [e for e in events if e["type"] == "memory_update"][1:]
    # Connor's Memory Update gets the outcome, not a choice of his own.
    assert connor["input"]["chapter_segment"][-1] == {
        "at": "In the hold", "decided_by": "Markus", "outcome": "REACH THE GUN FIRST"}
    # Markus remembers his choice, in his next segment and Memory Update.
    learned = next(e for e in events if e["node_id"] == "m3")["input"]["chapter_segment_so_far"][0]
    assert learned["decided"] == "Decided as Markus"
    assert learned["your_choice"] == "REACH THE GUN FIRST"
    assert markus["input"]["chapter_segment"][0] == learned


def test_the_story_says_who_decided_alone(tmp_path):
    Runner(_markus_alone_graph(), "mock", None, tmp_path / "runs" / "r").run()
    (gun,) = [m for m in story_moments(tmp_path / "runs", "2") if m["type"] == "decision"]
    assert gun["decided"] == "Decided as Markus" and gun["character"] == "Markus"


GUN, FIGHT, AS_MARKUS, AS_CONNOR = "ch30_2_00010", "ch32_6_00046", "ch32_6_x0127", "ch32_6_x0119"


def test_who_decides_the_gun_and_the_final_fight():
    nodes = load_dataset()["nodes"]
    assert nodes[GUN]["type"] == "choice" and nodes[GUN]["chapter"] == "30.2"
    assert nodes[GUN]["deciders"] == ["Markus"]  # In Connor's segment, Markus's alone.
    assert nodes[FIGHT]["deciders"] == ["Markus", "Connor"]  # Who to control: joint.
    assert nodes[AS_CONNOR]["deciders"] == ["Connor"]
    assert "deciders" not in nodes[AS_MARKUS]  # Markus's own, in his own segment.
    labels = [o["label"] for o in nodes[GUN]["options"]]
    assert labels == ["REACH THE GUN FIRST", "LET CONNOR REACH IT"]


def _memory_before(events: list, event: dict, character: str) -> str:
    updates = [e for e in events[: events.index(event)]
               if e["type"] == "memory_update" and e["character"] == character]
    return updates[-1]["memory"]


@pytest.mark.parametrize("pick", ["REACH THE GUN FIRST", "LET CONNOR REACH IT"])
def test_the_gun_in_the_hold_is_markus_decision(tmp_path, pick):
    run = play_story(tmp_path, {**MACHINE_WITH_MARKUS, GUN: pick})
    reached = pick == "REACH THE GUN FIRST"
    # Markus shoots Connor (one of Connor's Deaths), or Connor shoots Markus (his Fate).
    assert ("ch30_2_x0101" in run.nodes, "ch30_2_00009" in run.nodes) == (reached, not reached)
    assert run.flags["connor_died_in_crossroads"] is reached
    if not reached:
        assert run.flags["markus_alive"] is False
    gun = next(e for e in run.events if e["node_id"] == GUN)
    payload = gun["input"]
    assert payload["current_scene"]["character"] == "Markus"
    assert payload["character_memory"] == _memory_before(run.events, gun, "Markus")
    assert "chapter_segment_so_far" not in payload and "points_of_view" not in payload
    connor = next(e for e in run.events[run.events.index(gun):] if e["type"] == "memory_update")
    assert connor["character"] == "Connor"
    assert {"at": "In the hold", "decided_by": "Markus", "outcome": pick} in connor["input"]["chapter_segment"]
    if reached:
        # Markus's next segment knows what he decided in Connor's.
        markus = next(e for e in run.events[run.events.index(gun) + 1:]
                      if e["type"] == "decision" and e["input"]["current_scene"]["character"] == "Markus")
        assert markus["input"]["chapter_segment_so_far"][0]["your_choice"] == pick


def test_only_who_to_control_is_decided_together(tmp_path):
    run = play_story(tmp_path, {**REVOLUTION, **MACHINE, FIGHT: "CONTROL CONNOR"})
    fight = next(e for e in run.events if e["node_id"] == FIGHT)
    assert fight["deciders"] == ["Markus", "Connor"]
    assert set(fight["input"]["points_of_view"]) == {"Markus", "Connor"}
    as_connor = next(e for e in run.events if e["node_id"] == AS_CONNOR)
    payload = as_connor["input"]
    assert as_connor["deciders"] == ["Connor"]
    assert payload["current_scene"]["character"] == "Connor"
    assert payload["character_memory"] == _memory_before(run.events, as_connor, "Connor")
    assert payload["since_last_memory"][0]["decided"] == "Decided with Markus's and Connor's memories"
    assert "chapter_segment_so_far" not in payload


def test_controlling_markus_he_fights_with_his_own_memory(tmp_path):
    run = play_story(tmp_path, {**REVOLUTION, **MACHINE, FIGHT: "CONTROL MARKUS"})
    as_markus = next(e for e in run.events if e["node_id"] == AS_MARKUS)
    assert "deciders" not in as_markus
    assert as_markus["input"]["character_memory"] == _memory_before(run.events, as_markus, "Markus")
    assert "chapter_segment_so_far" in as_markus["input"]


# --- Relationships ------------------------------------------------------------------
def test_relationships_are_shown_by_default(tmp_path):
    run = play_story(tmp_path, {})
    lines = {
        line
        for e in run.events
        if e["type"] == "decision"
        for moment in e["input"].get("chapter_segment_so_far", [])
        for line in moment.get("on_screen", [])
    }
    assert any(line.startswith("Relationship with Hank: ") for line in lines)


# --- Review fixes -------------------------------------------------------------------
@pytest.mark.parametrize("stress, outcome", [(70, CHRIS), (71, SELF_DESTRUCT), (50, CHRIS)])
def test_seventy_percent_is_optimal_and_chris_steps_in(stress, outcome):
    graph = load_dataset()
    rule = graph["nodes"]["ch9_00041"]
    idx, _, _ = pick_branch(rule, {STRESS: stress, "connor_pressured_four_times": False})
    assert rule["branches"][idx]["next"] == outcome
    band = "optimal" if stress <= 70 else "too high"
    assert next(b["name"] for b in graph["scores"][STRESS]["bands"] if stress <= b["max"]) == band


def test_the_stress_is_shown_from_the_start_and_after_fear(tmp_path):
    run = play_story(tmp_path, {})
    first = next(e for e in run.events if e["node_id"] == "ch9_00123")
    assert first["input"]["chapter_segment_so_far"][-1]["on_screen"] == [
        "The deviant's stress: 35% (too low)"
    ]
    assert run.labels["ch9_00123"] == "FEAR"
    after = next(e for e in run.events if e["node_id"] == "ch9_00118")
    fear = next(m for m in after["input"]["chapter_segment_so_far"] if m.get("your_choice") == "FEAR")
    assert fear["on_screen"] == ["The deviant's stress: 35% (too low)"]


def test_giving_up_the_pressure_leads_back_to_the_approaches(tmp_path):
    run = play_story(tmp_path, {"ch9_00095": "PRESSURE IT", "ch9_00061": "GIVE UP",
                                "ch9_x0109": "GIVE UP"})
    assert run.offered("ch9_x0109") == ["PROBE ITS MEMORY", "CONVINCE IT", "GIVE UP"]
    assert CONFESSION not in run.nodes and CELL in run.nodes


def test_after_a_failed_convince_and_pressure_connor_gives_up(tmp_path):
    # Both approaches used: no third one.
    run = play_story(tmp_path, {"ch9_00095": "CONVINCE IT", SECOND_APPROACH: "PRESSURE IT",
                                "ch9_00061": "GIVE UP"})
    assert "ch9_x0109" not in run.nodes
    assert CONFESSION not in run.nodes and CELL in run.nodes


def _two_joint_graph() -> dict:
    """Connor's segment makes two Joint Decisions before Markus plays again."""
    graph = _joint_graph()
    nodes = graph["nodes"]
    nodes["c2x"]["next"] = "c4"
    nodes["c4"] = {"id": "c4", "type": "scene", "chapter": "4", "character": "Connor",
                   "heading": "Connor 4", "description": "", "next": "fight"}
    nodes["fight"] = {**nodes["gun"], "id": "fight", "chapter": "4", "heading": "The fight",
                      "options": [{"id": "win", "label": "WIN THE FIGHT", "next": "c4x",
                                   "effects": {"flags": {}}}]}
    nodes["c4x"] = {"id": "c4x", "type": "chapter_exit", "chapter": "4",
                    "character": "Connor", "next": "m3"}
    return graph


def test_the_other_deciders_view_carries_its_earlier_joint_decisions(tmp_path):
    Runner(_two_joint_graph(), "mock", None, tmp_path / "r").run()
    events = read_events(tmp_path / "r")
    gun = next(e for e in events if e["node_id"] == "gun")
    assert "since_last_memory" not in gun["input"]["points_of_view"]["Markus"]
    fight = next(e for e in events if e["node_id"] == "fight")
    markus = fight["input"]["points_of_view"]["Markus"]
    assert [m["your_choice"] for m in markus["since_last_memory"]] == ["REACH THE GUN FIRST"]
    assert markus["this_moment"]
    after = next(e for e in events if e["node_id"] == "m3")
    assert [m["your_choice"] for m in after["input"]["chapter_segment_so_far"][:2]] == [
        "REACH THE GUN FIRST", "WIN THE FIGHT"]


def _estimate(graph: dict) -> int:
    return _extreme_route(graph, max, memory=0, rationale=10, news=0).prompt_chars


def test_the_estimate_counts_relationship_and_branch_feedback():
    plain = _estimate(_scored_graph({STRESS: 4}))
    hinted = _scored_graph({STRESS: 4})
    hinted["nodes"]["first"]["options"][0]["relation_hints"] = [
        {"name": "RelationName.Hank", "direction": "RelationType.LargeUp"}]
    assert _estimate(hinted) > plain
    shown = _scored_graph({STRESS: 4})
    shown["nodes"]["second"]["options"][0]["next"] = "look"
    shown["nodes"]["look"] = {
        "id": "look", "type": "condition", "chapter": "9", "character": "Connor",
        "heading": "Look", "resolution": "rule", "source": "https://detroit-become-human.fandom.com/wiki/x",
        "branches": [{"when": {"all": []}, "next": "third",
                      "effects": {"flags": {}, "show": [STRESS]}}], "next": "third"}
    shown["nodes"]["third"] = {**shown["nodes"]["second"], "id": "third",
                               "options": [{**shown["nodes"]["second"]["options"][0], "next": "rule"}]}
    unshown = deepcopy(shown)
    del unshown["nodes"]["look"]["branches"][0]["effects"]["show"]
    assert _estimate(shown) > _estimate(unshown)
