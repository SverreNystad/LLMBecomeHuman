"""Dataset checks for Chapter Briefings and Public News."""

import json
import re
from pathlib import Path

import pytest

from detroit_benchmark.engine import validate_graph

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "detroit-unverified.json"
WIKI = "https://detroit-become-human.fandom.com"
SNAKE_CASE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")


@pytest.fixture(scope="module")
def graph():
    return json.loads(DATASET.read_text(encoding="utf-8"))


def choice_effects(graph):
    for nid, node in graph["nodes"].items():
        for option in node.get("options", []):
            yield f"{nid}/{option['id']}", option.get("effects") or {}


def test_every_chapter_segment_has_a_short_briefing(graph):
    briefings = graph["chapter_briefings"]
    assert set(briefings) == set(graph["chapter_entries"])
    for segment, text in briefings.items():
        assert text.strip(), segment
        assert len(text) <= 600, (segment, len(text))


def test_every_headline_is_short_and_has_a_wiki_source(graph):
    items = [
        (where, item)
        for where, effects in choice_effects(graph)
        for item in effects.get("news", [])
    ]
    assert items, "dataset should contain Public News"
    for where, item in items:
        assert item["headline"].strip(), where
        assert len(item["headline"]) <= 120, where
        assert item["source"].startswith(WIKI), where


def test_flags_are_snake_case(graph):
    for where, effects in choice_effects(graph):
        for flag in effects.get("flags", {}):
            assert SNAKE_CASE.fullmatch(flag), (where, flag)


def test_news_options_also_set_a_flag(graph):
    for where, effects in choice_effects(graph):
        if effects.get("news"):
            assert effects.get("flags"), where


def test_enrichment_sources_are_credited(graph):
    sources = graph["metadata"]["enrichment_sources"]
    assert any(s.startswith(WIKI) for s in sources)


def test_validate_graph_accepts_enriched_dataset(graph):
    report = validate_graph(graph)
    assert report["valid"], report["errors"][:5]


def test_validate_graph_rejects_bad_enrichment():
    graph = {
        "start": "a",
        "chapter_entries": {"1": "a", "2": "a"},
        "chapter_briefings": {"1": "x" * 601},
        "nodes": {
            "a": {
                "id": "a",
                "type": "choice",
                "options": [
                    {
                        "id": "o",
                        "next": "end",
                        "effects": {
                            "flags": {"BadFlag": True},
                            "news": [{"headline": "", "source": "https://example.com"}],
                        },
                    }
                ],
            },
            "end": {"id": "end", "type": "ending"},
        },
    }
    errors = validate_graph(graph)["errors"]
    assert any("briefing exceeds" in e for e in errors)
    assert any("missing chapter briefing" in e for e in errors)
    assert any("snake_case" in e for e in errors)
    assert any("without headline" in e for e in errors)
    assert any("without wiki source" in e for e in errors)


@pytest.mark.parametrize("path", sorted((ROOT / "examples").glob("*_game.json")))
def test_examples_without_enrichment_still_validate(path):
    graph = json.loads(path.read_text(encoding="utf-8"))
    assert validate_graph(graph)["valid"]
