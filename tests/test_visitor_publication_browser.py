"""Visitor Runs becoming public (#76), in a real browser.

Needs Playwright and a Chromium executable on PATH, like test_frontend_browser.py. The
dashboard plays Visitor Runs with a model factory built on the engine's `mock` provider.
"""

from __future__ import annotations

import json
import shutil
import time

import httpx
import pytest

from detroit_benchmark.dashboard import create_app
from detroit_benchmark.engine import create_model
from tests.test_visitor_runs_browser import open_form, serve
from tests.conftest import DETROIT_RUNS

STORY = DETROIT_RUNS / "detroit-mock-cautious" / "story-graph.json"
WARNING = "A public Run of this model already exists. Yours will be saved but only you will see it."


def mock_factory(provider, model_id, temperature=0, max_tokens=400, api_key=None):
    return create_model("mock", model_id, temperature, max_tokens)


@pytest.fixture
def publishing_dashboard(tmp_path):
    """The Detroit demo Runs, plus a maintainers' Run of openai/gpt-baked-1, with Visitor Runs on."""
    root = tmp_path / "runs"
    shutil.copytree(DETROIT_RUNS, root)
    baked = root / "maintainers" / "gpt-baked-1"
    shutil.copytree(DETROIT_RUNS / "detroit-mock-cautious", baked)
    experiment = json.loads((baked / "experiment.json").read_text())
    experiment.update(provider="openai", model_id="gpt-baked-1", synthetic=False)
    (baked / "experiment.json").write_text(json.dumps(experiment))
    app = create_app(
        root,
        images_dir=tmp_path / "images",
        allow_own_runs=True,
        model_factory=mock_factory,
        visitor_story=STORY,
    )
    server, thread, url = serve(app)
    yield url
    server.should_exit = True
    thread.join(timeout=5)


def play_to_completion(url, model):
    deadline = time.time() + 30
    # A visitor plays one Run at a time; the last one frees its slot just after it ends.
    while (
        response := httpx.post(
            url + "api/visitor-runs",
            json={"provider": "openai", "model": model, "key": "sk-other-visitor"},
        )
    ).status_code == 409 and time.time() < deadline:
        time.sleep(0.05)
    run_id = response.json()["id"]
    while time.time() < deadline:
        runs = httpx.get(url + "api/runs", params={"visitor_runs": [run_id]}).json()
        run = next(r for r in runs["runs"] if r["id"] == run_id)
        if run["status"] != "running":
            return run
        time.sleep(0.1)
    raise AssertionError("the Visitor Run did not finish")


def test_the_form_warns_before_start_when_a_public_run_of_the_model_exists(
    open_dashboard, publishing_dashboard
):
    page = open_dashboard(publishing_dashboard)
    page.locator(".story-decision").first.wait_for()
    open_form(page)
    warning = page.locator("#visitorRunWarning")
    page.locator("#visitorRunProvider").select_option("openai")

    page.locator("#visitorRunModel").fill("gpt-nobody-ran")
    page.wait_for_timeout(600)
    assert warning.is_hidden()

    page.locator("#visitorRunModel").fill("gpt-baked-1")
    warning.wait_for()
    assert warning.inner_text() == WARNING

    # The same model id under another provider is another model.
    page.locator("#visitorRunProvider").select_option("openrouter")
    warning.wait_for(state="hidden")
    assert page.errors == []


def test_a_public_visitor_run_is_listed_for_everyone_like_any_other_run(
    open_dashboard, publishing_dashboard
):
    run = play_to_completion(publishing_dashboard, "gpt-first-1")
    private = play_to_completion(publishing_dashboard, "gpt-first-1")
    assert run["status"] == private["status"] == "complete"

    # A visitor who started neither Run.
    page = open_dashboard(publishing_dashboard)
    page.locator(".story-decision").first.wait_for()
    page.locator("#pickerToggle").click()
    entries = page.locator(".picker-run", has_text="gpt-first-1")
    entries.first.wait_for()
    assert entries.count() == 1
    baked = page.locator(".picker-run", has_text="gpt-baked-1")
    assert entries.first.evaluate("e => e.className") == baked.evaluate(
        "e => e.className"
    )
    assert "playing" not in entries.first.inner_text()

    page.keyboard.press("Escape")
    open_form(page)
    page.locator("#visitorRunProvider").select_option("openai")
    page.locator("#visitorRunModel").fill("gpt-first-1")
    page.locator("#visitorRunWarning").wait_for()
    assert page.errors == []
