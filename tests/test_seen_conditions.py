"""Seen Conditions (GLOSSARY.md): an Unlock Requirement or rule can ask whether the Run
has already passed a story node, e.g. "Chose OPEN THE REGISTER" or "Saw the body in
the bathroom", without a flag of its own."""

import pytest

from detroit_benchmark.engine import Runner, validate_graph
from tests.dataset import read_events


def _graph() -> dict:
    """Two ways past the register, then a choice and a rule that remember which."""

    def choice(nid, options):
        return {
            "id": nid,
            "type": "choice",
            "chapter": "10",
            "character": "Kara",
            "heading": "The store",
            "description": "The clerk watches.",
            "options": [
                {
                    "id": f"o{i}",
                    "label": label,
                    "next": nxt,
                    "effects": {"flags": {}},
                    **({"requires": requires} if requires else {}),
                }
                for i, (label, nxt, requires) in enumerate(options)
            ],
        }

    def scene(nid, nxt):
        return {
            "id": nid,
            "type": "scene",
            "chapter": "10",
            "character": "Kara",
            "heading": "The store",
            "description": nid,
            "next": nxt,
        }

    return {
        "metadata": {"fidelity": "verified_game_rules"},
        "start": "threaten",
        "initial_flags": {},
        "nodes": {
            "threaten": choice(
                "threaten",
                [
                    ("BACK OFF!", "backed_off", None),
                    ("OPEN THE REGISTER!", "register", None),
                ],
            ),
            "backed_off": scene("backed_off", "demand"),
            "register": scene("register", "demand"),
            "demand": choice(
                "demand",
                [("LEAVE", "rule", None), ("BILLS!", "rule", [{"seen": "register"}])],
            ),
            "rule": {
                "id": "rule",
                "type": "condition",
                "chapter": "10",
                "character": "Kara",
                "heading": "The store",
                "resolution": "rule",
                "source": "https://detroit-become-human.fandom.com/wiki/Fugitives",
                "branches": [
                    {"when": {"seen": "register"}, "next": "money"},
                    {"when": {"not": {"seen": "register"}}, "next": "no_money"},
                ],
            },
            "money": {
                "id": "money",
                "type": "ending",
                "chapter": "10",
                "description": "Money.",
            },
            "no_money": {
                "id": "no_money",
                "type": "ending",
                "chapter": "10",
                "description": "Nothing.",
            },
        },
    }


class _Picks(Runner):
    def __init__(self, *args, picks, **kwargs):
        self.picks = picks
        super().__init__(*args, **kwargs)

    def _model_response(self, payload, options):
        from detroit_benchmark.engine import ModelDecision

        wanted = self.picks.get(self.state["node"])
        pick = next((o for o in options if o["label"] == wanted), options[0])
        return ModelDecision(choice_id=pick["id"], rationale="Scripted."), {}


def _play(tmp_path, picks):
    _Picks(_graph(), "mock", None, tmp_path / "r", picks=picks).run()
    return read_events(tmp_path / "r")


@pytest.mark.parametrize("opened", [True, False])
def test_an_option_and_a_rule_remember_a_node_the_run_passed(tmp_path, opened):
    events = _play(
        tmp_path, {"threaten": "OPEN THE REGISTER!" if opened else "BACK OFF!"}
    )
    demand = next(e for e in events if e.get("node_id") == "demand")
    offered = [o["label"] for o in demand["input"]["available_choices"]]
    assert ("BILLS!" in offered) is opened
    assert events[-1]["node_id"] == ("money" if opened else "no_money")


def test_a_seen_condition_is_never_unknown(tmp_path):
    # Unlike an unset flag, a node the Run never passed is simply not seen.
    events = _play(tmp_path, {})
    assert not any(e.get("used_unverified_default") for e in events)


def test_the_validator_checks_the_node_a_seen_condition_names():
    graph = _graph()
    assert validate_graph(graph)["errors"] == []
    graph["nodes"]["rule"]["branches"][0]["when"] = {"seen": "regster"}
    assert validate_graph(graph)["errors"] == [
        "rule: branch 0: seen names unknown node 'regster'"
    ]
