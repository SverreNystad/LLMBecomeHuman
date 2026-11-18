"""Taking an option or a condition branch: the Outcome it has on a Run, worked out
without touching the Run (its flags, what changed, its Gauge Feedback, its news)."""

from detroit_benchmark.engine import Runner, take
from tests.dataset import read_events

STRESS = {
    "gauge": "deviant_stress",
    "shown": "percent",
    "min": 0,
    "max": 100,
    "bands": [{"name": "too low", "max": 49}, {"name": "optimal", "max": 100}],
}
GRAPH = {"scores": {"stress": STRESS}}
WIKI = "https://detroit-become-human.fandom.com/wiki/Crossroads"


def test_taking_an_option_leaves_the_runs_flags_as_they_were():
    flags = {"stress": 40, "met": False}
    item = {"effects": {"flags": {"met": True}, "add": {"stress": 15}}}
    outcome = take(GRAPH, item, flags)
    assert flags == {"stress": 40, "met": False}
    assert outcome.flags == {"stress": 55, "met": True}
    assert outcome.changed == {"met": True, "stress": 55}


def test_the_gauge_feedback_is_the_authored_lines_then_the_real_moves():
    item = {
        "effects": {
            "add": {"stress": 80},
            "feedback": [{"gauge": "probability_of_success", "direction": "up"}],
        }
    }
    outcome = take(GRAPH, item, {"stress": 40})
    assert outcome.flags["stress"] == 100
    assert [f["text"] for f in outcome.feedback] == [
        "Probability of success: up",
        # The move is worded from the real change, capped at the score's max.
        "The deviant's stress: up sharply to 100% (optimal)",
    ]


def test_an_option_and_a_branch_both_make_their_news_public():
    news = [{"headline": "Riot downtown", "source": "https://x"}]
    assert take(GRAPH, {"effects": {"news": news}}, {}).news == ["Riot downtown"]


def test_nothing_taken_changes_nothing():
    outcome = take(GRAPH, None, {"stress": 1})
    assert (outcome.flags, outcome.changed, outcome.feedback, outcome.news) == (
        {"stress": 1},
        {},
        [],
        [],
    )


def test_a_branch_that_makes_news_reaches_the_next_prompt(tmp_path):
    graph = {
        "metadata": {"fidelity": "verified_game_rules"},
        "start": "rule",
        "nodes": {
            "rule": {
                "id": "rule", "type": "condition", "chapter": "1", "character": "Kara",
                "heading": "On the bus", "resolution": "rule", "source": WIKI,
                "branches": [
                    {
                        "when": {"flag": "always", "equals": True},
                        "next": "pick",
                        "effects": {
                            "news": [{"headline": "Android escapes", "source": WIKI}]
                        },
                    }
                ],
                "next": "pick",
            },
            "pick": {
                "id": "pick", "type": "choice", "chapter": "1", "character": "Kara",
                "heading": "Border", "description": "Cross?",
                "options": [{"id": "go", "label": "GO", "next": "end"}],
            },
            "end": {"id": "end", "type": "ending", "chapter": "1", "description": "."},
        },
        "initial_flags": {"always": True},
    }
    Runner(graph, "mock", None, tmp_path / "run").run()
    decision = next(e for e in read_events(tmp_path / "run") if e["type"] == "decision")
    assert decision["input"]["news"] == ["Android escapes"]
