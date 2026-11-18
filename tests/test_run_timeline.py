"""A Run's timeline: the Moments the Story and the Flowchart draw, worked out from its
events once, so the browser only draws them."""

import json

from detroit_benchmark.run_timeline import timeline


def _decision(index, node, choice, character="Connor", **extra):
    return {
        "index": index,
        "type": "decision",
        "chapter": "1",
        "node_id": node,
        "input": {
            "current_scene": {"heading": "Roof", "character": character},
            "available_choices": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
        },
        "output": {"choice_id": choice, "rationale": "Because."},
        **extra,
    }


def _logged(tmp_path, *events):
    (tmp_path / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )
    return timeline(tmp_path)


def test_each_pass_through_a_decision_has_its_own_key_in_both_views(tmp_path):
    run = _logged(
        tmp_path,
        _decision(0, "roof", "a"),
        _decision(1, "deck", "a"),
        _decision(2, "roof", "b"),
    )
    assert [d["key"] for d in run.decisions] == ["roof#1", "deck#1", "roof#2"]
    assert [m["key"] for m in run.chapter("1", {})] == ["roof#1", "deck#1", "roof#2"]


def test_every_event_names_where_the_run_went_next(tmp_path):
    scene = {"index": 1, "type": "scene", "chapter": "2", "node_id": "hall"}
    run = _logged(tmp_path, _decision(0, "roof", "a"), scene)
    first, last = run.events
    assert (first["next"], first["next_chapter"]) == ("hall", "2")
    assert "next" not in last


def test_the_story_asks_who_decides(tmp_path):
    run = _logged(
        tmp_path,
        _decision(0, "roof", "a"),
        _decision(1, "hold", "a", deciders=["Markus", "Connor"]),
        # A Cross-Segment Decision's scene is the decider's.
        _decision(2, "gun", "a", character="Markus", deciders=["Markus"]),
    )
    moments = run.chapter("1", {})
    assert [m["question"] for m in moments] == [
        "What does Connor do?",
        "What do Markus and Connor do?",
        "What does Markus do?",
    ]
    assert [m.get("decided") for m in moments] == [
        None,
        "Decided with Markus's and Connor's memories",
        "Decided as Markus",
    ]


def test_a_condition_the_story_could_not_decide_says_what_the_run_assumed(tmp_path):
    rule = {
        "index": 0,
        "type": "condition",
        "chapter": "1",
        "node_id": "rule",
        "branch_index": 1,
        "used_unverified_default": True,
    }
    graph = {
        "nodes": {
            "rule": {
                "branches": [
                    {"condition_text": "Hank trusts Connor"},
                    {"condition_text": "Hank does not trust Connor"},
                ]
            }
        }
    }
    (moment,) = _logged(tmp_path, rule).chapter("1", graph)
    assert moment["text"] == "Assumed: Hank does not trust Connor"
