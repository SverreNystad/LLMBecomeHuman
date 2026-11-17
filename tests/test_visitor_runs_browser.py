"""Playing a Visitor Run from the dashboard (#71), in a real browser.

Needs Playwright and a Chromium executable on PATH, like test_frontend_browser.py. The
dashboard plays Visitor Runs with a model factory built on the engine's `mock` provider.
"""

from __future__ import annotations

import shutil
import socket
import threading
import time
from pathlib import Path

import pytest

from detroit_benchmark.dashboard import create_app
from detroit_benchmark.engine import create_model
from tests.conftest import pass_title_screen

PROJECT = Path(__file__).resolve().parents[1]
DETROIT = PROJECT / "demo_runs" / "detroit"
KEY = "sk-sentinel-browser-7c1e"


class Gate:
    """Holds every Visitor Run before its first model call until the test opens it, so the
    Run is seen while it is still playing."""

    def __init__(self):
        self.open = threading.Event()

    def factory(self, provider, model_id, temperature=0, max_tokens=400, api_key=None):
        self.open.wait(timeout=30)
        return create_model("mock", model_id, temperature, max_tokens)


def serve(app):
    uvicorn = pytest.importorskip("uvicorn")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    return server, thread, f"http://127.0.0.1:{port}/"


@pytest.fixture
def gate():
    gate = Gate()
    yield gate
    gate.open.set()


@pytest.fixture
def own_runs_dashboard(tmp_path, gate):
    """The Detroit demo Runs with Visitor Runs on; Visitor Runs play the demos' story."""
    root = tmp_path / "runs"
    shutil.copytree(DETROIT, root)
    app = create_app(
        root,
        images_dir=tmp_path / "images",
        allow_own_runs=True,
        model_factory=gate.factory,
        visitor_story=DETROIT / "detroit-mock-cautious" / "story-graph.json",
    )
    server, thread, url = serve(app)
    yield url
    gate.open.set()
    server.should_exit = True
    thread.join(timeout=5)


def open_form(page):
    page.locator("#pickerToggle").click()
    page.locator("#visitorRunOpen").click()
    page.locator("#visitorRunPanel").wait_for()


def chip_models(page):
    return page.locator(".run-chip").evaluate_all(
        "els => els.map(e => e.getAttribute('aria-label'))"
    )


def test_without_the_flag_there_is_no_form(open_dashboard, detroit_dashboard):
    page = open_dashboard(detroit_dashboard)
    page.locator(".story-decision").first.wait_for()
    page.locator("#pickerToggle").click()
    page.locator("#pickerList .picker-run").first.wait_for()
    page.wait_for_timeout(300)
    assert page.locator("#visitorRunOpen").count() == 0
    assert page.locator("#visitorRunPanel").count() == 0


def test_start_shows_the_run_as_playing_and_it_is_still_listed_after_a_reload(
    open_dashboard, own_runs_dashboard, gate
):
    page = open_dashboard(own_runs_dashboard)
    page.locator(".story-decision").first.wait_for()
    shown_before = len(chip_models(page))
    open_form(page)
    page.locator("#visitorRunProvider").select_option("openai")
    page.locator("#visitorRunKey").fill(KEY)
    assert page.locator("#visitorRunKey").get_attribute("type") == "password"
    assert "never stored" in page.locator("#visitorRunPanel").inner_text()
    page.locator("#visitorRunModel").fill("gpt-visitor-1")
    page.locator("#visitorRunStart").click()

    # Added to the Shown Runs, and listed in the picker as playing.
    page.wait_for_function(
        "[...document.querySelectorAll('.run-chip')].some(c => c.getAttribute('aria-label').startsWith('gpt-visitor-1'))"
    )
    assert len(chip_models(page)) == min(shown_before + 1, 6)
    assert page.locator("#visitorRunPanel").is_hidden()
    page.locator("#pickerToggle").click()
    entry = page.locator(".picker-run", has_text="gpt-visitor-1")
    assert "playing" in entry.inner_text()
    page.keyboard.press("Escape")

    gate.open.set()
    page.reload()
    pass_title_screen(page)
    page.locator("#pickerToggle").click()
    page.locator(".picker-run", has_text="gpt-visitor-1").wait_for()
    assert page.errors == []


def test_on_a_phone_opening_the_form_by_touch_focuses_no_field(
    open_dashboard, own_runs_dashboard
):
    page = open_dashboard(own_runs_dashboard, "phone")
    page.locator(".story-decision").first.wait_for()
    page.locator("#pickerToggle").tap()
    page.locator("#visitorRunOpen").tap()
    page.locator("#visitorRunPanel").wait_for()
    page.wait_for_timeout(400)
    focused = page.evaluate("document.activeElement?.tagName")
    assert focused not in ("INPUT", "SELECT", "TEXTAREA")
    assert page.locator("#visitorRunPanel").bounding_box()["width"] <= 390
