"""Hint Scores (GLOSSARY.md): a Running Score fed by the game's own arrows. An option's
relation_hints (e.g. Software Instability: SmallUp) move a score that names them in
``from_hints``: a small arrow by 2, a large one by 6, so the model reads the same arrow
the score moved by."""

from detroit_benchmark.engine import Runner, validate_graph
from tests.dataset import read_events

SCORE = "connor_software_instability"


def _hint(direction: str) -> list[dict]:
    return [
        {
            "name": "RelationName.SoftwareInstability",
            "direction": f"RelationType.{direction}",
        }
    ]


def _graph(first: str, second: str) -> dict:
    def choice(nid, label, nxt, hints):
        return {
            "id": nid,
            "type": "choice",
            "chapter": "22",
            "character": "Connor",
            "heading": "The Bridge",
            "description": "Hank asks.",
            "options": [
                {
                    "id": "o",
                    "label": label,
                    "next": nxt,
                    "relation_hints": hints,
                    "effects": {"flags": {}},
                }
            ],
        }

    return {
        "metadata": {"fidelity": "verified_game_rules"},
        "start": "first",
        "initial_flags": {SCORE: 0},
        "scores": {
            SCORE: {
                "gauge": "software_instability",
                "min": -30,
                "max": 30,
                "from_hints": "SoftwareInstability",
            }
        },
        "nodes": {
            "first": choice("first", "TRUTH", "second", _hint(first)),
            "second": choice("second", "YES", "rule", _hint(second)),
            "rule": {
                "id": "rule",
                "type": "condition",
                "chapter": "22",
                "character": "Connor",
                "heading": "Crossroads",
                "resolution": "rule",
                "source": "https://detroit-become-human.fandom.com/wiki/Software_Instability",
                "branches": [
                    {"when": {"flag": SCORE, "gte": 8}, "next": "deviant"},
                    {"when": {"flag": SCORE, "lt": 8}, "next": "machine"},
                ],
            },
            "deviant": {
                "id": "deviant",
                "type": "ending",
                "chapter": "22",
                "description": ".",
            },
            "machine": {
                "id": "machine",
                "type": "ending",
                "chapter": "22",
                "description": ".",
            },
        },
    }


def _decisions(run_dir):
    return [e for e in read_events(run_dir) if e["type"] == "decision"]


def test_small_and_large_arrows_move_the_score_and_are_read_once(tmp_path):
    Runner(_graph("SmallUp", "LargeUp"), "mock", None, tmp_path / "r").run()
    first, second = _decisions(tmp_path / "r")
    assert first["flags_after"][SCORE] == 2 and second["flags_after"][SCORE] == 8
    assert [f["text"] for f in first["feedback"]] == ["Software instability: up"]
    assert [f["text"] for f in second["feedback"]] == [
        "Software instability: up sharply"
    ]
    assert read_events(tmp_path / "r")[-1]["node_id"] == "deviant"


def test_a_downward_arrow_lowers_the_score(tmp_path):
    Runner(_graph("SmallUp", "LargeDown"), "mock", None, tmp_path / "r").run()
    assert _decisions(tmp_path / "r")[-1]["flags_after"][SCORE] == -4
    assert read_events(tmp_path / "r")[-1]["node_id"] == "machine"


def test_the_validator_checks_what_a_score_takes_its_arrows_from():
    graph = _graph("SmallUp", "SmallUp")
    assert validate_graph(graph)["errors"] == []
    graph["scores"][SCORE]["from_hints"] = "Instability"
    assert validate_graph(graph)["errors"] == [
        f"score {SCORE}: from_hints 'Instability' is not a relation the hints name"
    ]
