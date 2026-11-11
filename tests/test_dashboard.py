"""Contract tests for dashboard's existing run-log format."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from detroit_benchmark.dashboard import (
    STALE_RUN_SECONDS,
    _flowchart_projection,
    create_app,
)

PROJECT = Path(__file__).resolve().parents[1]


def client():
    return TestClient(create_app(PROJECT / "demo_runs"))


def test_lists_demo_runs():
    response = client().get("/api/runs")
    assert response.status_code == 200
    runs = response.json()["runs"]
    assert len(runs) == 10
    assert {run["status"] for run in runs} == {"complete"}
    assert {run["choices"] for run in runs} == {6}
    assert {run["provider"] for run in runs} == {"mock"}
    assert all(run["synthetic"] for run in runs)
    assert {"openai", "anthropic", "xai", "google", "deepseek", "mistral"} <= {
        r["display_provider"] for r in runs
    }


def test_detail_reflects_saved_decisions():
    c = client()
    runs = c.get("/api/runs").json()["runs"]
    first = next(r for r in runs if "first" in r["name"])
    d = c.get(f"/api/runs/{first['id']}").json()
    assert len(d["decisions"]) == 6
    assert d["decisions"][0]["choice_id"] == "scan"
    assert d["decisions"][0]["flags_before"] == {}
    assert d["decisions"][0]["flags_after"]["scan_performed"] is True
    assert d["decisions"][1]["prompt_history_count"] == 1
    assert d["decisions"][5]["prompt_history_count"] == 5
    event = c.get(f"/api/runs/{first['id']}/events/{d['decisions'][5]['index']}").json()
    assert len(event["input"]["entire_decision_history"]) == 5
    assert all(x.get("rationale") for x in event["input"]["entire_decision_history"])
    assert "Select exactly ONE" in event["system_prompt"]
    assert event["input"]["world_state"] != event["flags_after"]


def test_compare_identifies_same_node_differences_not_path_absences():
    c = client()
    runs = c.get("/api/runs").json()["runs"]
    first = next(r for r in runs if r["name"] == "demo-first-option")
    last = next(r for r in runs if r["name"] == "demo-last-option")
    result = c.get(
        "/api/compare", params=[("run_ids", first["id"]), ("run_ids", last["id"])]
    )
    assert result.status_code == 200
    payload = result.json()
    assert payload["shared"] == 6
    assert payload["different"] == 6
    assert payload["unshared"] == 0
    assert payload["identical"] == 0
    assert (
        payload["rows"][0]["left"]["node_id"] == payload["rows"][0]["right"]["node_id"]
    )


def test_csv_export_and_missing_event():
    c = client()
    run = c.get("/api/runs").json()["runs"][0]
    response = c.get(f"/api/runs/{run['id']}/decisions.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "rationale" in response.text
    assert len(response.text.splitlines()) == 7
    assert c.get(f"/api/runs/{run['id']}/events/9999").status_code == 404


def test_path_traversal_rejected():
    import base64

    bad = base64.urlsafe_b64encode(b"../../etc").decode().rstrip("=")
    assert client().get(f"/api/runs/{bad}").status_code == 404


def test_in_progress_and_partially_written_jsonl(tmp_path):
    source = PROJECT / "demo_runs" / "demo-first-option"
    target = tmp_path / "live"
    shutil.copytree(source, target)
    (target / "summary.json").unlink()
    checkpoint = json.loads((target / "checkpoint.json").read_text())
    checkpoint["state"]["status"] = "running"
    (target / "checkpoint.json").write_text(json.dumps(checkpoint))
    with (target / "events.jsonl").open("a") as f:
        f.write('{"index":')  # concurrent writer: incomplete final record
    c = TestClient(create_app(tmp_path))
    run = c.get("/api/runs").json()["runs"][0]
    assert run["status"] == "running"
    detail = c.get(f"/api/runs/{run['id']}").json()
    assert len(detail["decisions"]) == 6


def test_serves_frontend_and_assets():
    c = client()
    assert c.get("/").status_code == 200
    assert "renderDecisionInspector" in c.get("/assets/app.js").text
    assert c.get("/assets/styles.css").status_code == 200


def test_frontend_is_named_llm_become_human():
    c = client()
    assert "<title>LLM: Become Human</title>" in c.get("/").text
    for path in ("/", "/assets/app.js", "/assets/story.js", "/assets/styles.css"):
        assert "decision atlas" not in c.get(path).text.lower(), path


def test_legacy_view_is_gone():
    c = client()
    assert c.get("/legacy").status_code == 404
    for asset in ("legacy.html", "legacy-app.js", "legacy-styles.css"):
        assert c.get(f"/assets/{asset}").status_code == 404, asset
    assert "/legacy" not in c.get("/").text


def test_frontend_has_no_internal_detail_copy():
    c = client()
    page = "\n".join(
        c.get(path).text
        for path in ("/", "/assets/app.js", "/assets/story.js")
    ).lower()
    for phrase in (
        "all script paths",
        "always on",
        "private · local",
        "synchronizing",
        "script steps",
        "graph nodes",
        "drag to pan",
        "esc · close",
        "every script branch",
        "refreshbtn",
    ):
        assert phrase not in page, phrase


def test_compare_requires_two_runs():
    c = client()
    first = c.get("/api/runs").json()["runs"][0]
    assert c.get("/api/compare", params={"run_ids": first["id"]}).status_code == 422


def test_flowchart_includes_unvisited_options_and_all_chapters():
    c = client()
    run = c.get("/api/runs").json()["runs"][0]
    chart = c.get(f"/api/runs/{run['id']}/flowchart").json()
    assert chart["complete"] is True
    assert chart["source"] == "matched_local_graph"
    assert chart["node_count"] == 22
    assert len(chart["chapters"]) == 3
    assert {"scan", "rush"} == {
        o["id"] for o in chart["nodes"]["arrival_decision"]["options"]
    }
    assert chart["nodes"]["arrival_decision"]["options"][0]["next"] == "scan_result"
    assert "source_keys" not in json.dumps(chart)


def test_new_runner_stores_full_graph_snapshot(tmp_path):
    from detroit_benchmark.engine import Runner, canonical_hash

    graph = json.loads((PROJECT / "examples" / "showcase_game.json").read_text())
    folder = tmp_path / "fresh"
    Runner(graph, "mock", None, folder).run()
    saved = json.loads((folder / "story-graph.json").read_text())
    assert canonical_hash(saved) == canonical_hash(graph)
    c = TestClient(create_app(tmp_path))
    run = c.get("/api/runs").json()["runs"][0]
    assert c.get(f"/api/runs/{run['id']}/flowchart").json()["source"] == "run_snapshot"


def test_old_runs_without_graph_return_partial_not_invented_paths(tmp_path):
    shutil.copytree(PROJECT / "demo_runs" / "demo-first-option", tmp_path / "old")
    c = TestClient(create_app(tmp_path))
    run = c.get("/api/runs").json()["runs"][0]
    # The demo can be matched from the shipped example graph, so modify the hash
    # to simulate a legacy story file that is no longer on disk.
    exp = json.loads((tmp_path / "old" / "experiment.json").read_text())
    exp["graph_sha256"] = "unavailable-story-graph"
    (tmp_path / "old" / "experiment.json").write_text(json.dumps(exp))
    result = c.get(f"/api/runs/{run['id']}/flowchart").json()
    assert result["complete"] is False
    assert result["source"] == "event_log_only"
    assert len(result["nodes"]["arrival_decision"]["options"]) == 2
    assert (
        next(
            o
            for o in result["nodes"]["arrival_decision"]["options"]
            if o["id"] == "rush"
        )["next"]
        is None
    )


def test_demo_family_is_only_cosmetic_and_never_claims_real_model_usage(tmp_path):
    source = PROJECT / "demo_runs" / "preview-grok-a"
    target = tmp_path / "preview"
    shutil.copytree(source, target)
    c = TestClient(create_app(tmp_path))
    item = c.get("/api/runs").json()["runs"][0]
    assert item["provider"] == "mock"
    assert item["display_provider"] == "xai"
    assert item["synthetic"] is True
    exp = json.loads((target / "experiment.json").read_text())
    exp["synthetic"] = False
    (target / "experiment.json").write_text(json.dumps(exp))
    item = c.get("/api/runs").json()["runs"][0]
    assert item["display_provider"] is None


def test_story_endpoint_returns_readable_chapter_in_order():
    c = client()
    run = c.get("/api/runs").json()["runs"][0]
    chapter = c.get(f"/api/runs/{run['id']}/flowchart").json()["chapters"][0]
    beats = c.get(f"/api/runs/{run['id']}/story", params={"chapter": chapter}).json()[
        "beats"
    ]
    assert beats
    assert [b["index"] for b in beats] == sorted(b["index"] for b in beats)
    decision = next(b for b in beats if b["type"] == "decision")
    assert (
        decision["available_choices"]
        and decision["choice_id"]
        and decision["rationale"]
    )
    assert "system_prompt" not in decision and "input" not in decision


def test_story_endpoint_exposes_dialogue_and_clues(tmp_path):
    target = tmp_path / "run"
    shutil.copytree(PROJECT / "demo_runs" / "demo-first-option", target)
    with (target / "events.jsonl").open("a") as f:
        f.write(
            json.dumps(
                {
                    "index": 9000,
                    "type": "scene",
                    "node_id": "n",
                    "chapter": "Extra",
                    "visible_to_agent": {
                        "heading": "Roof",
                        "description": "Inspect: Gun",
                        "observations": ["Loaded"],
                        "dialogue": [
                            {"speaker": "Allen", "text": "Hold.", "source_keys": ["K"]}
                        ],
                    },
                }
            )
            + "\n"
        )
    c = TestClient(create_app(tmp_path))
    run = c.get("/api/runs").json()["runs"][0]
    [beat] = c.get(f"/api/runs/{run['id']}/story", params={"chapter": "Extra"}).json()[
        "beats"
    ]
    assert beat["dialogue"] == [{"speaker": "Allen", "text": "Hold."}]
    assert beat["observations"] == ["Loaded"]


def test_story_for_unvisited_chapter_is_empty_not_an_error():
    c = client()
    run = c.get("/api/runs").json()["runs"][0]
    response = c.get(
        f"/api/runs/{run['id']}/story", params={"chapter": "Never visited"}
    )
    assert response.status_code == 200
    assert response.json()["beats"] == []


def test_story_sees_new_events_written_to_a_live_run(tmp_path):
    target = tmp_path / "run"
    shutil.copytree(PROJECT / "demo_runs" / "demo-first-option", target)
    c = TestClient(create_app(tmp_path))
    run = c.get("/api/runs").json()["runs"][0]
    assert (
        c.get(f"/api/runs/{run['id']}/story", params={"chapter": "Live"}).json()[
            "beats"
        ]
        == []
    )
    with (target / "events.jsonl").open("a") as f:
        f.write(
            json.dumps(
                {
                    "index": 9001,
                    "type": "scene",
                    "node_id": "n",
                    "chapter": "Live",
                    "visible_to_agent": {"heading": "New"},
                }
            )
            + "\n"
        )
    assert (
        len(
            c.get(f"/api/runs/{run['id']}/story", params={"chapter": "Live"}).json()[
                "beats"
            ]
        )
        == 1
    )


def test_run_without_recent_events_is_reported_as_stopped(tmp_path):
    target = tmp_path / "dead"
    shutil.copytree(PROJECT / "demo_runs" / "demo-first-option", target)
    (target / "summary.json").unlink()
    checkpoint = json.loads((target / "checkpoint.json").read_text())
    checkpoint["state"]["status"] = "running"
    (target / "checkpoint.json").write_text(json.dumps(checkpoint))
    long_ago = time.time() - 2 * STALE_RUN_SECONDS
    os.utime(target / "events.jsonl", (long_ago, long_ago))
    run = TestClient(create_app(tmp_path)).get("/api/runs").json()["runs"][0]
    assert run["status"] == "stopped"


def test_detroit_graph_gets_chapter_titles_and_others_keep_their_names():
    detroit = {
        "metadata": {
            "source": "https://github.com/detroitbecometext/detroitbecometext.github.io"
        },
        "nodes": {
            "a": {"id": "a", "type": "scene", "chapter": "1", "character": "Connor"}
        },
    }
    assert _flowchart_projection(detroit, complete=True, source="t")["chapter_info"][
        "1"
    ] == {"title": "The Hostage", "character": "Connor"}
    other = {
        "metadata": {},
        "nodes": {"a": {"id": "a", "type": "scene", "chapter": "1"}},
    }
    assert _flowchart_projection(other, complete=True, source="t")["chapter_info"][
        "1"
    ] == {"title": None, "character": None}


def test_browsers_must_revalidate_the_frontend():
    c = client()
    for path in (
        "/",
        "/assets/app.js",
        "/assets/story.js",
        "/assets/styles.css",
    ):
        assert c.get(path).headers["cache-control"] == "no-cache", path


def test_flowchart_includes_scene_script_without_source_keys():
    graph = {
        "metadata": {},
        "nodes": {
            "a": {
                "id": "a",
                "type": "scene",
                "chapter": "1",
                "observations": ["Loaded"],
                "dialogue": [
                    {"speaker": "Allen", "text": "Hold.", "source_keys": ["K"]}
                ],
            }
        },
    }
    node = _flowchart_projection(graph, complete=True, source="t")["nodes"]["a"]
    assert node["dialogue"] == [{"speaker": "Allen", "text": "Hold."}]
    assert node["observations"] == ["Loaded"]


@pytest.mark.skipif(
    not (PROJECT / "docker-compose.yml").exists(),
    reason="compose file is not in the image",
)
def test_dashboard_mounts_are_not_nested_inside_a_read_only_mount():
    compose = (PROJECT / "docker-compose.yml").read_text()
    dashboard = compose.split("dashboard:", 1)[1].split("runner:", 1)[0]
    mounts = re.findall(r"^\s*- \./[^:\s]+:(/app/\S+?)(:ro)?$", dashboard, re.M)
    assert len(mounts) >= 2
    for target, read_only in mounts:
        if read_only:
            assert not any(
                other != target and other.startswith(target + "/")
                for other, _ in mounts
            ), target
