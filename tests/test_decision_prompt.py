"""The Decision Prompt: everything a model sees at a choice (ADR 0001, ADR 0005)."""

from detroit_benchmark.decision_prompt import (
    PromptContext,
    choice_moments,
    decision_prompt,
)

GRAPH = {"chapter_briefings": {"2": "The hold of the freighter."}, "nodes": {}}


def choice(**extra) -> dict:
    return {
        "id": "gun",
        "type": "choice",
        "chapter": "2",
        "character": "Connor",
        "heading": "In the hold",
        "description": "Both lunge for the gun.",
        "options": [
            {"id": "reach", "label": "REACH THE GUN", "next": "x"},
            {"id": "wait", "label": "WAIT", "next": "x"},
        ],
        **extra,
    }


def context(**extra) -> PromptContext:
    return PromptContext(
        **{
            "memories": {"Connor": "Connor remembers.", "Markus": "Markus remembers."},
            "pending": {},
            "segment": [{"at": "Earlier", "your_choice": "LOOK"}],
            "news": None,
            "goal": "Play as yourself.",
            **extra,
        }
    )


def test_a_choice_shows_the_scene_its_characters_memory_and_segment_and_the_offered_options():
    node = choice()
    prompt = decision_prompt(GRAPH, node, node["options"][:1], context())
    assert prompt == {
        "current_scene": {
            "chapter": "2",
            "character": "Connor",
            "heading": "In the hold",
            "description": "Both lunge for the gun.",
        },
        "chapter_briefing": "The hold of the freighter.",
        "character_memory": "Connor remembers.",
        "chapter_segment_so_far": [{"at": "Earlier", "your_choice": "LOOK"}],
        "goal": "Play as yourself.",
        "available_choices": [{"id": "reach", "label": "REACH THE GUN"}],
    }


def test_public_news_is_shown_when_there_is_some():
    node = choice()
    prompt = decision_prompt(GRAPH, node, node["options"], context(news=["Riot."]))
    assert prompt["news"] == ["Riot."]


JOINT = {
    "deciders": ["Markus", "Connor"],
    "decider_context": {"Markus": "Connor draws on Markus in the hold."},
}


def test_a_joint_decision_shows_each_deciders_memory_and_own_view_of_the_moment():
    node = choice(**JOINT)
    pending = {"Markus": [{"at": "Before", "your_choice": "RUN"}]}
    prompt = decision_prompt(GRAPH, node, node["options"], context(pending=pending))
    assert prompt["current_scene"]["deciders"] == ["Markus", "Connor"]
    assert prompt["joint_decision"].startswith(
        "This is a Joint Decision: it belongs to both Markus and Connor."
    )
    assert prompt["points_of_view"] == {
        "Markus": {
            "character_memory": "Markus remembers.",
            "since_last_memory": [{"at": "Before", "your_choice": "RUN"}],
            "this_moment": "Connor draws on Markus in the hold.",
        },
        "Connor": {
            "character_memory": "Connor remembers.",
            "chapter_segment_so_far": [{"at": "Earlier", "your_choice": "LOOK"}],
        },
    }
    assert "character_memory" not in prompt and "chapter_segment_so_far" not in prompt


def test_a_cross_segment_decision_shows_only_the_deciders_memory_and_view():
    node = choice(
        deciders=["Markus"],
        decider_context={"Markus": "Connor draws on Markus in the hold."},
    )
    prompt = decision_prompt(GRAPH, node, node["options"], context())
    assert prompt == {
        "current_scene": {
            "chapter": "2",
            "character": "Markus",
            "heading": "In the hold",
            "description": "Both lunge for the gun.",
        },
        "character_memory": "Markus remembers.",
        "this_moment": "Connor draws on Markus in the hold.",
        "goal": "Play as yourself.",
        "available_choices": [
            {"id": "reach", "label": "REACH THE GUN"},
            {"id": "wait", "label": "WAIT"},
        ],
    }


REACH = {"id": "reach", "label": "REACH THE GUN", "next": "x"}


def test_the_segments_character_remembers_its_own_choice_and_what_flashed_on_screen():
    segment, others = choice_moments(choice(), REACH, "Because.", ["Hank: up"])
    assert segment == {
        "at": "In the hold",
        "your_choice": "REACH THE GUN",
        "rationale": "Because.",
        "on_screen": ["Hank: up"],
    }
    assert others == {}


def test_after_a_joint_decision_the_other_decider_remembers_it_at_its_next_memory_update():
    segment, others = choice_moments(choice(**JOINT), REACH, "Because.", [])
    assert segment == {
        "at": "In the hold",
        "your_choice": "REACH THE GUN",
        "rationale": "Because.",
    }
    assert others == {
        "Markus": {
            "chapter": "2",
            "at": "In the hold",
            "decided": "Decided with Markus's and Connor's memories",
            "your_choice": "REACH THE GUN",
            "rationale": "Because.",
        }
    }


def test_after_a_cross_segment_decision_the_segments_character_learns_only_the_outcome():
    node = choice(deciders=["Markus"], decider_context={"Markus": "..."})
    segment, others = choice_moments(node, REACH, "Because.", [])
    assert segment == {
        "at": "In the hold",
        "decided_by": "Markus",
        "outcome": "REACH THE GUN",
    }
    assert others["Markus"]["decided"] == "Decided as Markus"
    assert others["Markus"]["your_choice"] == "REACH THE GUN"
