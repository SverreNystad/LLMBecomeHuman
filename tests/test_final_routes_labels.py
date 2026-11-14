"""Readable Final Routes labels in the Flowchart (#83): route nodes carry the question their
route flag answers, from the Ending Summary's mapping table, instead of the flag's name."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from detroit_benchmark.dashboard import create_app

PROJECT = Path(__file__).resolve().parents[1]
DEMO = PROJECT / "demo_runs" / "detroit"
SNAKE_CASE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")


def _flowchart() -> dict:
    client = TestClient(create_app(DEMO))
    run_id = client.get("/api/runs").json()["runs"][0]["id"]
    response = client.get(f"/api/runs/{run_id}/flowchart")
    assert response.status_code == 200
    return response.json()


def test_final_routes_route_nodes_are_headed_by_their_question():
    nodes = _flowchart()["nodes"]
    assert nodes["route_kara_final"]["heading"] == "Was Kara captured?"
    assert nodes["route_connor_final"]["heading"] == "Did Connor become deviant?"
    assert nodes["route_markus_final"]["heading"] == "Was Markus's revolution peaceful?"
    routes = [n for n in nodes.values() if n.get("type") == "route"]
    assert all(n["heading"].endswith("?") for n in routes)


def test_no_final_routes_heading_or_branch_text_is_snake_case():
    nodes = _flowchart()["nodes"]
    final = [node for node in nodes.values() if node.get("chapter") == "final"]
    assert final
    texts = [node.get("heading", "") for node in final]
    texts += [
        branch.get("condition_text", "")
        for node in final
        for branch in node.get("branches", [])
    ]
    for text in texts:
        assert not SNAKE_CASE.search(text), text
