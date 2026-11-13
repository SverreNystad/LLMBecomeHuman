"""The real story dataset, loaded once per test session; each call returns a fresh copy."""

import json
from functools import lru_cache

from detroit_benchmark.engine import effect_flags
from pathlib import Path

DATASET = Path(__file__).resolve().parents[1] / "data" / "detroit-unverified.json"


@lru_cache(maxsize=1)
def _text() -> str:
    return DATASET.read_text(encoding="utf-8")


def load_dataset() -> dict:
    return json.loads(_text())


def flag_values(graph: dict) -> dict[str, set]:
    """Every value each flag can take: set by a choice, by a condition branch (a fate
    decided there), or at the start of the story."""
    values: dict[str, set] = {}
    for name, value in (graph.get("initial_flags") or {}).items():
        values.setdefault(name, set()).add(value)
    for n in graph["nodes"].values():
        for o in n.get("options", []) + n.get("branches", []):
            for name, value in effect_flags(o).items():
                values.setdefault(name, set()).add(value)
    return values


def flags_in(expr: dict) -> set[str]:
    """Every flag name a rule's ``when`` expression reads."""
    if "flag" in expr:
        return {expr["flag"]}
    inner = expr.get("all") or expr.get("any") or [expr["not"]]
    return set().union(*(flags_in(x) for x in inner))


def read_events(run_dir: Path) -> list[dict]:
    """A finished Run's events, strictly: a malformed line fails the test."""
    return [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text().splitlines()
        if line
    ]


class Playthrough:
    """A whole-story Run of the real dataset by a scripted mock player."""

    def __init__(self, events: list[dict], flags: dict):
        self.events = events
        self.flags = flags
        self.nodes = [e.get("node_id") for e in events]
        self.chapters = [str(e.get("chapter")) for e in events if e["type"] == "scene"]
        self.headings: dict[str, set] = {}
        for e in events:
            if e["type"] == "scene":
                self.headings.setdefault(str(e.get("chapter")), set()).add(
                    e["visible_to_agent"]["heading"]
                )
        self.labels = {
            e["node_id"]: e["label"] for e in events if e["type"] == "decision"
        }

    def offered(self, nid: str) -> list[str]:
        """The option labels the model was offered at a choice node."""
        event = next(e for e in self.events if e.get("node_id") == nid)
        return [o["label"] for o in event["input"]["available_choices"]]


def play_story(run_dir: Path, picks: dict[str, str]) -> Playthrough:
    """Play the whole real story, picking the option labelled ``picks[node]`` at
    each listed choice node and the first option elsewhere."""
    from detroit_benchmark.engine import ModelDecision, Runner

    class Scripted(Runner):
        def _model_response(self, payload, options):
            wanted = picks.get(self.state["node"])
            pick = next((o for o in options if o["label"] == wanted), options[0])
            return ModelDecision(choice_id=pick["id"], rationale="Scripted."), {}

    run = Scripted(load_dataset(), "mock", None, run_dir, allow_unverified=True)
    run.run()
    assert run.state["status"] == "complete"
    return Playthrough(read_events(run_dir), run.state["flags"])
