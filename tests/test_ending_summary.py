"""The Ending Summary on a Run's detail (#82): how each Character, the side characters and
the world ended, in plain sentences built on the server."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from detroit_benchmark.dashboard import create_app
from tests.conftest import DETROIT_RUNS

PROJECT = Path(__file__).resolve().parents[1]
SIDE_CHARACTERS = ["Hank", "Alice", "Luther", "Simon", "North", "Josh", "Carl"]
SNAKE_CASE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")


def _summary(root: Path, name: str) -> dict:
    client = TestClient(create_app(root))
    runs = {run["name"]: run["id"] for run in client.get("/api/runs").json()["runs"]}
    response = client.get(f"/api/runs/{runs[name]}")
    assert response.status_code == 200
    return response.json()["ending_summary"]


def _sentences(summary: dict) -> list[str]:
    texts = [entry["sentence"] for entry in summary["characters"]]
    texts.append(summary["world"]["sentence"])
    texts.extend(summary["world"]["headlines"])
    texts.extend(fate["text"] for fate in summary["fates"])
    return texts


def _character(summary: dict, name: str) -> dict:
    return next(entry for entry in summary["characters"] if entry["name"] == name)


def _fate(summary: dict, name: str) -> str:
    return next(fate["fate"] for fate in summary["fates"] if fate["name"] == name)


@pytest.fixture
def craft(tmp_path):
    """Copies a demo Run into a temporary runs folder, letting the test edit its record:
    `craft(final_flags=..., news=..., routes=..., finished=...)` returns the runs folder."""

    def make(*, flags=None, news=None, routes=None, finished=True):
        run = tmp_path / "runs" / "crafted"
        shutil.copytree(DETROIT_RUNS / "synthetic-anthropic", run)
        summary_path, checkpoint_path = run / "summary.json", run / "checkpoint.json"
        summary = json.loads(summary_path.read_text())
        checkpoint = json.loads(checkpoint_path.read_text())
        if flags is not None:
            summary["final_flags"] = checkpoint["state"]["flags"] = flags
        if news is not None:
            checkpoint["state"]["news"] = news
        if routes is not None:
            events = [json.loads(line) for line in (run / "events.jsonl").open()]
            kept = [e for e in events if e["type"] != "route"]
            ending = next(i for i, e in enumerate(kept) if e["type"] == "ending")
            crafted = [
                {
                    "index": 0,
                    "type": "route",
                    "chapter": "final",
                    "node_id": node,
                    "flag": flag,
                    "value": value,
                    "assumed": assumed,
                }
                for node, flag, value, assumed in routes
            ]
            events = kept[:ending] + crafted + kept[ending:]
            for i, event in enumerate(events):
                event["index"] = i
            (run / "events.jsonl").write_text(
                "".join(json.dumps(e) + "\n" for e in events)
            )
        if not finished:
            summary_path.unlink()
            checkpoint["state"]["status"] = "running"
        else:
            summary_path.write_text(json.dumps(summary))
        checkpoint_path.write_text(json.dumps(checkpoint))
        return tmp_path / "runs"

    return make


def test_a_finished_demo_run_has_three_characters_seven_fates_and_the_world():
    summary = _summary(DETROIT_RUNS, "synthetic-anthropic")
    assert summary["finished"] is True
    assert [entry["name"] for entry in summary["characters"]] == [
        "Connor",
        "Kara",
        "Markus",
    ]
    assert [fate["name"] for fate in summary["fates"]] == SIDE_CHARACTERS
    assert all(entry["sentence"] for entry in summary["characters"])
    assert summary["world"]["sentence"]
    # The last three Public News headlines, newest last.
    assert summary["world"]["headlines"] == [
        "Androids free CyberLife store stock in Capitol Park and leave without setting fires",
        "Androids release two captured police officers unharmed in Capitol Park",
        "Android marchers flee downtown plaza under police fire",
    ]


@pytest.mark.parametrize(
    "name", ["synthetic-anthropic", "synthetic-xai", "synthetic-google"]
)
def test_no_sentence_names_a_flag(name):
    for text in _sentences(_summary(DETROIT_RUNS, name)):
        assert text and not SNAKE_CASE.search(text), text


def test_a_demo_run_reads_as_its_recorded_route():
    peaceful = _summary(DETROIT_RUNS, "synthetic-google")
    assert _character(peaceful, "Markus")["sentence"] == (
        "Markus led a peaceful demonstration and died with his people."
    )
    assert _character(peaceful, "Kara")["sentence"] == (
        "Kara and Alice escaped the camp on a truck."
    )
    assert peaceful["world"]["sentence"] == "The revolution stayed peaceful."
    violent = _summary(DETROIT_RUNS, "synthetic-xai")
    assert _character(violent, "Connor")["sentence"].startswith(
        "Connor stayed a machine. He died 3 times"
    )
    assert violent["world"]["sentence"] == "The revolution turned violent."
    without = _summary(DETROIT_RUNS, "synthetic-anthropic")
    assert _character(without, "Markus")["sentence"] == (
        "Markus walked away from Jericho and left his people to North."
    )
    assert without["world"]["sentence"] == "The revolution went on without Markus."


def test_an_outcome_missing_from_the_flags_is_unknown_not_defaulted(craft):
    # A Run from before the Fate flags, whose Kara route was assumed.
    root = craft(
        flags={"connor_deviant": True},
        routes=[
            ("route_kara_final", "kara_captured", False, True),
            ("route_connor_final", "connor_deviant", True, False),
            ("route_markus_final", "markus_peaceful", True, False),
        ],
    )
    summary = _summary(root, "crafted")
    assert {fate["fate"] for fate in summary["fates"]} == {"unknown"}
    assert all(fate["text"] == "Unknown" for fate in summary["fates"])
    kara = _character(summary, "Kara")
    assert kara["outcome"] == "unknown"
    assert "unknown" in kara["sentence"]
    connor = _character(summary, "Connor")
    assert connor["deaths"] is None
    assert connor["sentence"] == (
        "Connor became deviant. It is unknown how often he died or whether his story ended."
    )


def test_a_crafted_ending_says_who_lived_and_how(craft):
    flags = {
        "connor_deviant": True,
        "connor_deaths": 2,
        "connor_story_ended": False,
        "connor_androids_woke": True,
        "kara_alive": True,
        "kara_captured": False,
        "kara_story_ended": False,
        "alice_alive": True,
        "markus_alive": False,
        "markus_peaceful": False,
        "hank_alive": True,
        "luther_alive": False,
        "simon_alive": True,
        "north_alive": False,
        "josh_alive": True,
    }
    root = craft(
        flags=flags,
        news=["One", "Two", "Three", "Four"],
        routes=[
            ("route_kara_final", "kara_captured", False, False),
            ("route_connor_final", "connor_deviant", True, False),
            ("route_markus_final", "markus_peaceful", False, False),
        ],
    )
    summary = _summary(root, "crafted")
    assert _character(summary, "Connor")["sentence"] == (
        "Connor became deviant. He died twice, and CyberLife sent a new body each time."
        " His story went on to the end. Connor woke the androids at CyberLife Tower."
    )
    kara = _character(summary, "Kara")
    assert kara["sentence"] == "Kara reached freedom. Alice is with her."
    assert kara["alice_with_her"] is True
    assert _character(summary, "Markus")["sentence"] == (
        "Markus led a violent revolution. He died before it was over."
    )
    assert [fate["fate"] for fate in summary["fates"]] == [
        "alive",
        "alive",
        "dead",
        "alive",
        "dead",
        "alive",
        "unknown",  # Carl: this crafted Run never decided him
    ]
    assert summary["world"] == {
        "sentence": "The revolution turned violent.",
        "headlines": ["Two", "Three", "Four"],
    }


@pytest.mark.parametrize(
    ("kara_flags", "sentence"),
    [
        ({"kara_captured": True}, "Kara was captured. Alice is alive."),
        ({"kara_alive": False}, "Kara died. Alice is alive."),
    ],
)
def test_alice_is_with_kara_only_if_kara_is_free(craft, kara_flags, sentence):
    flags = {"kara_alive": True, "kara_captured": False, "alice_alive": True}
    kara_flags = {**flags, **kara_flags}
    route = ("route_kara_final", "kara_captured", kara_flags["kara_captured"], False)
    root = craft(flags=kara_flags, routes=[route])
    kara = _character(_summary(root, "crafted"), "Kara")
    assert kara["sentence"] == sentence
    assert kara["alice_with_her"] is False


@pytest.mark.parametrize(
    ("alice", "sentence", "with_her"),
    [
        (True, "Kara was captured but escaped the camp. Alice is with her.", True),
        (False, "Kara was captured but escaped the camp. Alice died.", False),
    ],
)
def test_kara_who_escaped_the_camp_is_not_described_as_captured(
    craft, alice, sentence, with_her
):
    flags = {
        "kara_alive": True,
        "kara_captured": True,
        "kara_escaped_camp": True,
        "kara_story_ended": False,
        "alice_alive": alice,
    }
    root = craft(flags=flags, routes=[("route_kara_final", "kara_captured", True, False)])
    kara = _character(_summary(root, "crafted"), "Kara")
    assert kara["outcome"] == "escaped"
    assert kara["sentence"] == sentence
    assert kara["alice_with_her"] is with_her


def test_markus_whose_story_ended_early_has_no_revolution_outcome(craft):
    # The story's starting facts say "not peaceful"; that is a default, not an outcome.
    root = craft(
        flags={"markus_alive": False, "markus_peaceful": False},
        routes=[("route_connor_final", "connor_deviant", False, False)],
    )
    summary = _summary(root, "crafted")
    markus = _character(summary, "Markus")
    assert markus["outcome"] == "unknown"
    assert markus["sentence"] == "Markus died before the final battle."
    assert summary["world"]["sentence"] == "The revolution went on without Markus."


def test_an_unfinished_run_is_marked_not_finished(craft):
    flags = {"kara_alive": True, "kara_captured": False, "alice_alive": True}
    summary = _summary(craft(flags=flags, finished=False), "crafted")
    assert summary["finished"] is False
    # Kara has got away so far, but a Run still playing has not set her free.
    assert _character(summary, "Kara")["outcome"] == "unknown"
    assert summary["fates"][1] == {"name": "Alice", "fate": "alive", "text": "Alive"}


def test_a_run_that_recorded_no_outcomes_says_so(craft):
    """Runs played before the story tracked Fates finish with every outcome unknown; the
    summary says no outcome was recorded instead of listing unknowns."""
    summary = _summary(craft(flags={}, news=[], routes=[]), "crafted")
    assert summary["finished"] is True
    assert summary["recorded"] is False
