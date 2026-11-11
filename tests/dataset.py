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
