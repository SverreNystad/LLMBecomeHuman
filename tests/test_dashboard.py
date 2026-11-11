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
from detroit_benchmark.engine import Runner
from tests.test_benchmark import three_segment_graph

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
        c.get(path).text for path in ("/", "/assets/app.js", "/assets/story.js")
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
    moments = c.get(f"/api/runs/{run['id']}/story", params={"chapter": chapter}).json()[
        "moments"
    ]
    assert moments
    assert [b["index"] for b in moments] == sorted(b["index"] for b in moments)
    decision = next(b for b in moments if b["type"] == "decision")
    assert (
        decision["available_choices"]
        and decision["choice_id"]
        and decision["rationale"]
    )
    assert "system_prompt" not in decision and "input" not in decision


def test_story_and_flowchart_share_moment_ids():
    c = client()
    run = next(
        r for r in c.get("/api/runs").json()["runs"] if r["name"] == "demo-first-option"
    )
    chart = c.get(f"/api/runs/{run['id']}/flowchart").json()
    flowchart_moments = {
        node["moment"]: node for node in chart["nodes"].values() if "moment" in node
    }
    assert len(flowchart_moments) == chart["node_count"]
    for chapter in chart["chapters"]:
        moments = c.get(
            f"/api/runs/{run['id']}/story", params={"chapter": chapter}
        ).json()["moments"]
        assert moments
        for moment in moments:
            node = flowchart_moments[moment["moment"]]
            assert node["chapter"] == chapter
    # The first decision of the run is the arrival choice in both views.
    first = c.get(
        f"/api/runs/{run['id']}/story", params={"chapter": chart["chapters"][0]}
    ).json()["moments"]
    decision = next(b for b in first if b["type"] == "decision")
    assert flowchart_moments[decision["moment"]]["id"] == "arrival_decision"


def test_story_moments_stay_distinct_when_a_scene_is_revisited(tmp_path):
    target = tmp_path / "run"
    shutil.copytree(PROJECT / "demo_runs" / "demo-first-option", target)
    with (target / "events.jsonl").open("a") as f:
        for index in (9000, 9001):
            f.write(
                json.dumps(
                    {
                        "index": index,
                        "type": "scene",
                        "node_id": "loop",
                        "chapter": "Again",
                        "visible_to_agent": {"heading": "Loop"},
                    }
                )
                + "\n"
            )
    c = TestClient(create_app(tmp_path))
    run = c.get("/api/runs").json()["runs"][0]
    moments = c.get(f"/api/runs/{run['id']}/story", params={"chapter": "Again"}).json()[
        "moments"
    ]
    assert [b["moment"] for b in moments] == ["loop", "loop"]
    assert [b["visit"] for b in moments] == [1, 2]


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
    [moment] = c.get(f"/api/runs/{run['id']}/story", params={"chapter": "Extra"}).json()[
        "moments"
    ]
    assert moment["dialogue"] == [{"speaker": "Allen", "text": "Hold."}]
    assert moment["observations"] == ["Loaded"]


def test_story_for_unvisited_chapter_is_empty_not_an_error():
    c = client()
    run = c.get("/api/runs").json()["runs"][0]
    response = c.get(
        f"/api/runs/{run['id']}/story", params={"chapter": "Never visited"}
    )
    assert response.status_code == 200
    assert response.json()["moments"] == []


def test_story_sees_new_events_written_to_a_live_run(tmp_path):
    target = tmp_path / "run"
    shutil.copytree(PROJECT / "demo_runs" / "demo-first-option", target)
    c = TestClient(create_app(tmp_path))
    run = c.get("/api/runs").json()["runs"][0]
    assert (
        c.get(f"/api/runs/{run['id']}/story", params={"chapter": "Live"}).json()[
            "moments"
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
                "moments"
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


def test_flowchart_marks_exploration_choices_and_key_inspect_scenes():
    graph = {
        "metadata": {},
        "nodes": {
            "how": {
                "id": "how",
                "type": "choice",
                "chapter": "1",
                "exploration": True,
                "options": [],
            },
            "gun": {"id": "gun", "type": "scene", "chapter": "1", "key": True},
            "plain": {"id": "plain", "type": "scene", "chapter": "1"},
        },
    }
    nodes = _flowchart_projection(graph, complete=True, source="t")["nodes"]
    assert nodes["how"]["exploration"] is True
    assert nodes["gun"]["key"] is True
    assert "key" not in nodes["plain"]


def played_run(tmp_path, **graph_extra):
    """A real mock Run of three Chapter Segments (Connor, Kara, Connor)."""
    graph = {**three_segment_graph(), **graph_extra}
    Runner(graph, "mock", None, tmp_path / "run").run()
    c = TestClient(create_app(tmp_path))
    return c, c.get("/api/runs").json()["runs"][0]


def story(c, run, chapter):
    response = c.get(f"/api/runs/{run['id']}/story", params={"chapter": chapter})
    assert response.status_code == 200
    return response.json()


def test_story_opens_each_chapter_with_its_briefing(tmp_path):
    c, run = played_run(
        tmp_path, chapter_briefings={"1": "A rooftop at dusk.", "2": "A kitchen."}
    )
    assert story(c, run, "1")["briefing"] == "A rooftop at dusk."
    assert story(c, run, "2")["briefing"] == "A kitchen."
    assert story(c, run, "3")["briefing"] is None


def test_story_ends_each_chapter_segment_with_a_memory_snapshot(tmp_path):
    c, run = played_run(tmp_path)
    first = story(c, run, "1")["moments"][-1]
    assert first["type"] == "memory"
    assert first["character"] == "Connor"
    assert "Rooftop" in first["memory"]
    assert first["previous"] == ""
    assert first["truncated"] is False

    kara = story(c, run, "2")["moments"][-1]
    assert kara["character"] == "Kara"
    assert kara["previous"] == ""  # Kara's own first memory, not Connor's

    later = story(c, run, "3")["moments"]
    memory = next(b for b in later if b["type"] == "memory")
    assert memory["previous"] == first["memory"]
    assert "Interrogation" in memory["memory"]


def test_old_runs_have_no_briefing_and_no_memory():
    c = client()
    run = c.get("/api/runs").json()["runs"][0]
    chapter = c.get(f"/api/runs/{run['id']}").json()["decisions"][0]["chapter"]
    body = story(c, run, chapter)
    assert body["moments"]
    assert body["briefing"] is None
    assert not [b for b in body["moments"] if b["type"] == "memory"]


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


def test_title_art_served_when_installed(tmp_path):
    (tmp_path / "ui").mkdir()
    (tmp_path / "ui" / "title.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
    c = TestClient(create_app(PROJECT / "demo_runs", images_dir=tmp_path))
    response = c.get("/api/art/title")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.content.startswith(b"RIFF")


def test_title_art_missing_is_404(tmp_path):
    c = TestClient(create_app(PROJECT / "demo_runs", images_dir=tmp_path))
    assert c.get("/api/art/title").status_code == 404


def _scene_art_app(tmp_path, installed=("ch01_installed",), runs=None):
    """A tmp images folder and manifest: one scene installed, one listed but missing."""
    images = tmp_path / "images"
    (images / "scenes").mkdir(parents=True)
    (tmp_path / "secret.txt").write_text("not art", encoding="utf-8")
    scenes = []
    for key in ("ch01_installed", "ch01_missing"):
        scenes.append(
            {
                "key": key,
                "file": f"scenes/{key}.webp",
                "chapter": "1",
                "character": "Connor",
                "headings": ["Coming into the living room"],
                "chapter_main": key == "ch01_installed",
                "caption": key,
            }
        )
        if key in installed:
            (images / "scenes" / f"{key}.webp").write_bytes(b"RIFF\x00\x00\x00\x00WEBP")
    # A manifest entry pointing outside the images folder is never served.
    scenes.append({"key": "escape", "file": "../secret.txt", "chapter": "1"})
    manifest = tmp_path / "scene-art.json"
    manifest.write_text(json.dumps({"title": "ui/title.webp", "scenes": scenes}))
    return TestClient(
        create_app(
            runs or PROJECT / "demo_runs", images_dir=images, art_manifest=manifest
        )
    )


def test_scene_art_manifest_lists_only_installed_images(tmp_path):
    scenes = _scene_art_app(tmp_path).get("/api/art/manifest").json()["scenes"]
    assert [s["key"] for s in scenes] == ["ch01_installed"]
    assert scenes[0]["url"] == "/api/art/scene/ch01_installed"
    assert scenes[0]["headings"] == ["Coming into the living room"]
    assert scenes[0]["chapter_main"] is True
    assert "file" not in scenes[0]


def test_scene_art_is_served_if_installed_else_404(tmp_path):
    c = _scene_art_app(tmp_path)
    found = c.get("/api/art/scene/ch01_installed")
    assert found.status_code == 200
    assert found.headers["content-type"] == "image/webp"
    assert found.content.startswith(b"RIFF")
    assert c.get("/api/art/scene/ch01_missing").status_code == 404
    assert c.get("/api/art/scene/not_in_manifest").status_code == 404


def test_scene_art_rejects_path_traversal(tmp_path):
    c = _scene_art_app(tmp_path)
    assert c.get("/api/art/scene/escape").status_code == 404
    for key in ("..%2Fsecret.txt", "..%2F..%2Fsecret.txt", "%2Fetc%2Fpasswd"):
        response = c.get(f"/api/art/scene/{key}")
        assert response.status_code == 404, key
        assert b"not art" not in response.content


def test_scene_art_without_images_or_manifest(tmp_path):
    c = TestClient(
        create_app(
            PROJECT / "demo_runs",
            images_dir=tmp_path / "none",
            art_manifest=tmp_path / "none.json",
        )
    )
    assert c.get("/api/art/manifest").json() == {"scenes": []}
    assert c.get("/api/art/scene/ch01_penthouse").status_code == 404


def test_committed_scene_art_manifest_is_well_formed():
    manifest = json.loads((PROJECT / "data" / "scene-art.json").read_text())
    keys = [scene["key"] for scene in manifest["scenes"]]
    assert len(keys) == len(set(keys))
    for scene in manifest["scenes"]:
        assert scene["file"] == f"scenes/{scene['key']}.webp"
        assert isinstance(scene["headings"], list)


def test_story_scenes_carry_their_installed_scene_image_key(tmp_path):
    Runner(three_segment_graph(), "mock", None, tmp_path / "runs" / "r1").run()
    c = _scene_art_app(tmp_path, runs=tmp_path / "runs")
    run = c.get("/api/runs").json()["runs"][0]
    moments = c.get(f"/api/runs/{run['id']}/story", params={"chapter": "1"}).json()[
        "moments"
    ]
    scenes = [m for m in moments if m["type"] == "scene"]
    assert scenes
    # Only installed images are named; the chapter's main image is the fallback.
    assert {m["art"] for m in scenes} == {"ch01_installed"}
    assert all("art" not in m for m in moments if m["type"] != "scene")
