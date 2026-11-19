"""Visitor Runs becoming public over HTTP (#76): the first complete Run of a model is listed
for everyone; every other Visitor Run stays private.

The model factory is built on the engine's `mock` provider, so a whole Run plays in seconds.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from detroit_benchmark import visitor_runs
from detroit_benchmark.dashboard import create_app
from tests.test_visitor_runs import (
    listing,
    mock_factory,
    start,
    visitor_client,
    wait_until_finished,
)
from tests.conftest import DETROIT_RUNS



def public_ids(client):
    return [run["id"] for run in listing(client)]


def public_run_exists(client, provider, model):
    response = client.get(
        "/api/visitor-runs/public", params={"provider": provider, "model": model}
    )
    assert response.status_code == 200
    return response.json()["public_run_exists"]


def start_when_free(client, provider="openai", model="gpt-test-1"):
    """Starts a Run once this visitor's last one has freed its slot (just after it ends)."""
    deadline = time.time() + 10
    while (response := start(client, provider=provider, model=model)).status_code == 409:
        assert time.time() < deadline, "the last Run never freed its slot"
        time.sleep(0.05)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def play(client, provider="openai", model="gpt-test-1"):
    return wait_until_finished(client, start_when_free(client, provider, model))


def bake_in(root: Path, provider: str, model: str, status: str = "complete"):
    """A maintainers' Run of this model under the runs root (not a Visitor Run)."""
    directory = root / "runs" / f"{provider}-{model}"
    shutil.copytree(DETROIT_RUNS / "synthetic-anthropic", directory)
    experiment = json.loads((directory / "experiment.json").read_text())
    experiment.update(provider=provider, model_id=model, synthetic=False)
    (directory / "experiment.json").write_text(json.dumps(experiment))
    summary = json.loads((directory / "summary.json").read_text())
    summary.update(status=status, provider=provider, model=model)
    (directory / "summary.json").write_text(json.dumps(summary))
    return directory


def test_the_first_complete_visitor_run_of_a_model_is_listed_for_everyone(tmp_path):
    client = visitor_client(tmp_path)
    assert public_run_exists(client, "openai", "gpt-test-1") is False

    run = play(client)

    assert run["status"] == "complete"
    assert public_ids(client) == [run["id"]]
    assert public_run_exists(client, "openai", "gpt-test-1") is True


def test_a_second_complete_run_of_the_same_model_stays_private(tmp_path):
    client = visitor_client(tmp_path)
    first = play(client)
    second = play(client)

    assert second["status"] == "complete"
    assert public_ids(client) == [first["id"]]
    assert second["id"] in [run["id"] for run in listing(client, second["id"])]


def test_models_are_told_apart_by_exact_provider_and_model_id(tmp_path):
    client = visitor_client(tmp_path)
    first = play(client, "openai", "gpt-test-1")
    dated = play(client, "openai", "gpt-test-1-2026-01-01")
    routed = play(client, "openrouter", "gpt-test-1")

    assert set(public_ids(client)) == {first["id"], dated["id"], routed["id"]}
    assert public_run_exists(client, "openrouter", "gpt-test-1-2026-01-01") is False


def test_a_model_with_a_baked_in_run_is_never_made_public(tmp_path):
    baked = bake_in(tmp_path, "anthropic", "claude-test-9")
    client = visitor_client(tmp_path)
    assert public_run_exists(client, "anthropic", "claude-test-9") is True

    run = play(client, "anthropic", "claude-test-9")

    assert run["status"] == "complete"
    assert [r["name"] for r in listing(client)] == [
        baked.relative_to(tmp_path).as_posix()
    ]


def test_a_partial_baked_in_run_does_not_count(tmp_path):
    bake_in(tmp_path, "anthropic", "claude-test-9", status="partial")
    client = visitor_client(tmp_path)
    assert public_run_exists(client, "anthropic", "claude-test-9") is False

    run = play(client, "anthropic", "claude-test-9")
    assert run["id"] in public_ids(client)


def test_a_partial_visitor_run_stays_private_and_does_not_count(tmp_path):
    def failing(provider, model_id, temperature=0, max_tokens=400, api_key=None):
        raise RuntimeError("the provider is down")

    client = visitor_client(tmp_path, model_factory=failing)
    run = play(client)

    assert run["status"] == "partial"
    assert public_ids(client) == []
    assert public_run_exists(client, "openai", "gpt-test-1") is False


def test_a_stopped_visitor_run_stays_private_and_does_not_count(tmp_path):
    gate = threading.Event()

    def held(provider, model_id, temperature=0, max_tokens=400, api_key=None):
        gate.wait(timeout=30)
        return mock_factory(provider, model_id, temperature, max_tokens)

    client = visitor_client(tmp_path, model_factory=held)
    run_id = start_when_free(client)
    assert client.post(f"/api/visitor-runs/{run_id}/stop").status_code == 202
    gate.set()

    assert wait_until_finished(client, run_id)["status"] == "partial"
    assert public_ids(client) == []
    assert public_run_exists(client, "openai", "gpt-test-1") is False


def test_a_playing_visitor_run_is_not_public(tmp_path):
    gate = threading.Event()

    def held(provider, model_id, temperature=0, max_tokens=400, api_key=None):
        gate.wait(timeout=30)
        return mock_factory(provider, model_id, temperature, max_tokens)

    client = visitor_client(tmp_path, model_factory=held)
    run_id = start(client).json()["id"]
    try:
        assert listing(client, run_id)[0]["status"] == "running"
        assert public_ids(client) == []
        assert public_run_exists(client, "openai", "gpt-test-1") is False
    finally:
        gate.set()
    wait_until_finished(client, run_id)
    assert public_ids(client) == [run_id]


def test_concurrent_completions_of_the_same_model_give_exactly_one_public_run(
    tmp_path,
):
    # Both Runs wait until both have built their backend, so they play side by side. Two
    # visitors (client IPs), since the site plays at most two at once and one per visitor.
    runs = 2
    barrier = threading.Barrier(runs, timeout=30)

    def together(provider, model_id, temperature=0, max_tokens=400, api_key=None):
        barrier.wait()
        return mock_factory(provider, model_id, temperature, max_tokens)

    client = visitor_client(tmp_path, model_factory=together)
    ids = [
        client.post(
            "/api/visitor-runs",
            json={"provider": "openai", "model": "gpt-test-1", "key": "sk-x"},
            headers={"CF-Connecting-IP": f"203.0.113.{n}"},
        ).json()["id"]
        for n in range(runs)
    ]
    finished = [wait_until_finished(client, run_id) for run_id in ids]

    assert [run["status"] for run in finished] == ["complete"] * runs
    public = public_ids(client)
    assert len(public) == 1 and public[0] in ids


def test_the_public_run_stays_public_and_the_rest_private_after_a_restart(tmp_path):
    client = visitor_client(tmp_path)
    first = play(client)
    second = play(client)

    restarted = visitor_client(tmp_path)
    assert public_ids(restarted) == [first["id"]]
    play(restarted)
    assert public_ids(restarted) == [first["id"]]
    assert second["id"] not in public_ids(restarted)


def test_without_the_flag_public_visitor_runs_are_still_listed_but_the_check_is_absent(
    tmp_path,
):
    run = play(visitor_client(tmp_path))
    client = TestClient(create_app(tmp_path))
    assert public_ids(client) == [run["id"]]
    assert (
        client.get(
            "/api/visitor-runs/public", params={"provider": "openai", "model": "x"}
        ).status_code
        == 404
    )


def test_publication_is_settled_at_start_up_and_when_a_run_ends_not_per_request(
    tmp_path, monkeypatch
):
    scans = []
    real = visitor_runs._public_models
    monkeypatch.setattr(
        visitor_runs, "_public_models", lambda root: scans.append(root) or real(root)
    )
    client = visitor_client(tmp_path)
    assert len(scans) == 1  # At start-up.

    for _ in range(5):
        listing(client)
        public_run_exists(client, "openai", "gpt-test-1")
        client.get(
            "/api/visitor-runs/estimate",
            params={"provider": "openai", "model": "gpt-test-1"},
        )
    assert len(scans) == 1

    run = play(client)
    # The Run reads as finished a moment before its worker settles publication, and is
    # listed (its decision written) a moment before the cached answer is refreshed: wait
    # for the cached answer, the last thing settling does.
    deadline = time.time() + 30
    while (
        not public_run_exists(client, "openai", "gpt-test-1") and time.time() < deadline
    ):
        time.sleep(0.02)
    assert len(scans) == 2  # When the Run ended.
    # The cached answer was refreshed then.
    assert public_run_exists(client, "openai", "gpt-test-1") is True
    assert public_ids(client) == [run["id"]]
    assert len(scans) == 2
