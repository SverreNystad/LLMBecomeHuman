"""Visitor Runs over HTTP (#71): a visitor starts a Run with their own key and watches it play.

The model factory is built on the engine's `mock` provider, so a whole Run plays in seconds.
"""

from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from detroit_benchmark.dashboard import create_app
from detroit_benchmark.engine import create_model
from detroit_benchmark.visitor_runs import scrub
from tests.test_benchmark import fake_chat_module

KEY = "sk-sentinel-0f3c9a7d1e5b4f2a"


def mock_factory(provider, model_id, temperature=0, max_tokens=400, api_key=None):
    """Plays every Visitor Run with the mock provider's policy, whatever provider was chosen."""
    return create_model("mock", model_id, temperature, max_tokens)


def visitor_client(tmp_path, **options):
    options.setdefault("allow_own_runs", True)
    options.setdefault("model_factory", mock_factory)
    return TestClient(create_app(tmp_path, **options))


def start(client, provider="openai", model="gpt-test-1", key=KEY):
    return client.post(
        "/api/visitor-runs", json={"provider": provider, "model": model, "key": key}
    )


def listing(client, *ids):
    return client.get("/api/runs", params={"visitor_runs": list(ids)}).json()["runs"]


def wait_until_finished(client, run_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = next((r for r in listing(client, run_id) if r["id"] == run_id), None)
        if run and run["status"] != "running":
            return run
        time.sleep(0.1)
    raise AssertionError("the Visitor Run did not finish")


def test_with_the_flag_off_every_visitor_run_endpoint_is_absent(tmp_path):
    client = TestClient(create_app(tmp_path, model_factory=mock_factory))
    assert client.get("/api/visitor-runs/config").status_code == 404
    assert start(client).status_code == 404
    assert list(tmp_path.iterdir()) == []


def test_a_started_visitor_run_plays_to_completion_and_is_listed(
    tmp_path,
):
    client = visitor_client(tmp_path)
    response = start(client, provider="anthropic", model="claude-test-9")
    assert response.status_code == 200
    run_id = response.json()["id"]

    run = wait_until_finished(client, run_id)
    assert run["status"] == "complete"
    assert (run["provider"], run["model"]) == ("anthropic", "claude-test-9")
    assert run["choices"] > 0
    # The same fidelity mode as the maintainers' recent real Runs.
    assert run["fidelity"] == "unverified_transcript_approximation"
    assert run["unverified"] is True

    # The first complete Run of its model is public (#76; tests/test_visitor_publication.py).
    assert [r["id"] for r in listing(client)] == [run_id]
    assert client.get(f"/api/runs/{run_id}").json()["run"]["status"] == "complete"


@pytest.mark.parametrize(
    "provider,module,cls,key_option",
    [
        ("openai", "langchain_openai", "ChatOpenAI", "api_key"),
        ("anthropic", "langchain_anthropic", "ChatAnthropic", "api_key"),
        (
            "google",
            "langchain_google_genai",
            "ChatGoogleGenerativeAI",
            "google_api_key",
        ),
        ("xai", "langchain_openai", "ChatOpenAI", "api_key"),
        ("deepseek", "langchain_openai", "ChatOpenAI", "api_key"),
        ("mistral", "langchain_openai", "ChatOpenAI", "api_key"),
        ("openrouter", "langchain_openai", "ChatOpenAI", "api_key"),
    ],
)
def test_a_backend_takes_a_key_passed_in_without_touching_the_environment(
    monkeypatch, provider, module, cls, key_option
):
    for name in list(os.environ):
        if name.endswith("_API_KEY"):
            monkeypatch.delenv(name)
    captured = fake_chat_module(monkeypatch, module, cls)
    before = dict(os.environ)
    create_model(provider, "some-model", 0, api_key=KEY)
    assert captured[key_option] == KEY
    assert dict(os.environ) == before


def test_the_key_never_reaches_the_runs_folder_or_the_logs_even_on_errors(
    tmp_path, caplog
):
    keys_used = []

    def factory(provider, model_id, temperature=0, max_tokens=400, api_key=None):
        keys_used.append(api_key)
        if model_id == "broken-model":
            raise RuntimeError(f"Incorrect API key provided: {api_key}")
        return mock_factory(provider, model_id, temperature, max_tokens)

    caplog.set_level("DEBUG")
    client = visitor_client(tmp_path, model_factory=factory, max_playing_per_visitor=2)
    played = start(client, model="good-model").json()["id"]
    broken = start(client, model="broken-model").json()["id"]
    assert wait_until_finished(client, played)["status"] == "complete"
    assert wait_until_finished(client, broken)["status"] == "partial"
    assert keys_used and set(keys_used) == {KEY}

    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert files
    for path in files:
        assert KEY not in path.read_text(encoding="utf-8", errors="replace"), path
    assert "Incorrect API key provided" in caplog.text
    assert KEY not in caplog.text
    for response in (
        client.get(f"/api/runs/{broken}"),
        client.get("/api/runs", params={"visitor_runs": [broken]}),
    ):
        assert KEY not in response.text


def test_scrub_also_removes_a_masked_echo_of_the_key():
    key = "sk-proj-abcdefghijklmnop1234"
    text = f"Incorrect API key provided: sk-pro**********1234 (full: {key})"
    scrubbed = scrub(text, key)
    assert key not in scrubbed
    assert "sk-pro" not in scrubbed and "1234" not in scrubbed
    assert scrubbed.startswith("Incorrect API key provided: ")
    # A short key's pieces are not removed: they would match ordinary text.
    assert scrub("error 1234 at sk-abc", "sk-abc1234") == "error 1234 at sk-abc"
