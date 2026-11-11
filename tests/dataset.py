"""The real story dataset, loaded once per test session; each call returns a fresh copy."""

import json
from functools import lru_cache
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
            for name, value in (o.get("effects") or {}).get("flags", {}).items():
                values.setdefault(name, set()).add(value)
    return values
