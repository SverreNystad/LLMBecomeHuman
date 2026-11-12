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
