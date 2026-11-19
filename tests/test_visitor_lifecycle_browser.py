"""Stopping a Visitor Run and the play limits (#74, #75), in a real browser.

Needs Playwright and a Chromium executable on PATH, like test_frontend_browser.py. Visitor
Runs play with the engine's `mock` provider; a Gate holds them playing until it opens.
"""

from __future__ import annotations

import shutil

import pytest

from detroit_benchmark.dashboard import create_app
from tests.test_visitor_lifecycle import Gate
from tests.conftest import DETROIT_RUNS
from tests.test_visitor_runs_browser import open_form, serve

KEY = "sk-sentinel-lifecycle-browser-91ab"


@pytest.fixture
def gate():
    gate = Gate()
    yield gate
    gate.open.set()


@pytest.fixture
def dashboard(tmp_path, gate):
    """Makes the Detroit demo dashboard with Visitor Runs on: `dashboard(**create_app options)`."""
    servers = []

    def make(**options):
        root = tmp_path / "runs"
        shutil.copytree(DETROIT_RUNS, root)
        app = create_app(
            root,
            images_dir=tmp_path / "images",
            allow_own_runs=True,
            model_factory=gate.factory,
            visitor_story=DETROIT_RUNS / "synthetic-anthropic" / "story-graph.json",
            **options,
        )
        server, thread, url = serve(app)
        servers.append((server, thread))
        return url

    yield make
    gate.open.set()
    for server, thread in servers:
        server.should_exit = True
        thread.join(timeout=5)


def start_from_form(page, model):
    open_form(page)
    page.locator("#visitorRunKey").fill(KEY)
    page.locator("#visitorRunModel").fill(model)
    page.locator("#visitorRunStart").click()


def test_stop_shows_only_on_the_visitors_own_playing_run_and_leaves_it_partial(
    open_dashboard, new_page, dashboard, gate
):
    url = dashboard()
    page = open_dashboard(url)
    page.locator(".story-decision").first.wait_for()
    # Nothing of this visitor's is playing: no Stop button anywhere.
    page.locator("#pickerToggle").click()
    page.locator("#pickerList .picker-run").first.wait_for()
    assert page.locator("[data-stop-run]").count() == 0
    page.keyboard.press("Escape")

    start_from_form(page, "gpt-stoppable-1")
    page.wait_for_function(
        "[...document.querySelectorAll('.run-chip')].some(c => c.getAttribute('aria-label').startsWith('gpt-stoppable-1'))"
    )
    page.locator("#pickerToggle").click()
    stop = page.locator("[data-stop-run]")
    stop.wait_for()
    assert stop.count() == 1
    assert "gpt-stoppable-1" in page.locator(".visitor-run-playing").inner_text()

    # Another visitor (a fresh browser) sees no Stop button for it.
    other = new_page()
    other.goto(url)
    other.locator("#pickerToggle").wait_for()
    other.wait_for_timeout(500)
    assert other.locator("[data-stop-run]").count() == 0

    stop.click()
    gate.open.set()
    entry = page.locator(".picker-run", has_text="gpt-stoppable-1")
    entry.locator("small", has_text="partial").wait_for(timeout=15000)
    page.locator("[data-stop-run]").wait_for(state="detached", timeout=15000)
    assert page.errors == []


@pytest.mark.parametrize(
    "limits,expected",
    [
        ({"max_playing": 1, "max_playing_per_visitor": 2}, "busy"),
        (
            {"max_playing": 2, "max_playing_per_visitor": 1},
            "already have a Run playing",
        ),
    ],
)
def test_the_form_shows_the_busy_and_already_playing_messages(
    open_dashboard, dashboard, limits, expected
):
    page = open_dashboard(dashboard(**limits))
    page.locator(".story-decision").first.wait_for()
    start_from_form(page, "gpt-first-1")
    page.locator("#visitorRunPanel").wait_for(state="hidden")

    start_from_form(page, "gpt-second-1")
    error = page.locator("#visitorRunError")
    error.wait_for()
    page.wait_for_function(
        "document.querySelector('#visitorRunError').textContent.length > 0"
    )
    assert expected in error.inner_text()
    assert "Try again later" in error.inner_text() or expected != "busy"
    assert page.locator("#visitorRunPanel").is_visible()
    assert "is-notice" in error.get_attribute("class")
    assert page.errors == []
