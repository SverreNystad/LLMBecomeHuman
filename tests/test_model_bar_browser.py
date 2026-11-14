"""The model bar (the Shown Runs beside the + button) stays on one line at laptop widths.

Runs against the real dashboard in Chromium; skipped when Playwright or Chromium is missing.
"""

from __future__ import annotations

import shutil
import socket
import threading
import time
from pathlib import Path

import pytest
from detroit_benchmark.dashboard import create_app

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def live_dashboard(tmp_path):
    """The real dashboard on a local port, serving the Aurora demo runs."""
    uvicorn = pytest.importorskip("uvicorn")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(PROJECT / "demo_runs" / "aurora", images_dir=tmp_path)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)


def _launch_chromium(p):
    binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        pytest.skip("Chromium executable unavailable")
    return p.chromium.launch(executable_path=binary, args=["--no-sandbox"])


def _open_with_six_runs(page, url):
    """Pass the title screen and show six Runs (the most the bar ever holds)."""
    page.goto(url)
    page.locator("#titleScreen").wait_for()
    page.wait_for_timeout(400)
    page.keyboard.press("Enter")
    page.locator("#titleScreen").wait_for(state="detached")
    page.locator("#pickerToggle").click()
    page.locator("#clearRuns").click()
    page.locator("#bestOfEach").click()
    page.wait_for_function("document.querySelectorAll('.run-chip').length === 6")
    page.keyboard.press("Escape")
    page.locator(".story-decision").first.wait_for()


BAR_LAYOUT = """() => {
  const bar = document.querySelector('#selectedRunChips').getBoundingClientRect();
  const panel = document.querySelector('.control-strip').getBoundingClientRect();
  return [...document.querySelectorAll('.run-chip')].map(chip => {
    const box = chip.getBoundingClientRect();
    const label = chip.querySelector('.run-chip-label');
    return {
      id: chip.dataset.focusId, title: chip.title, top: Math.round(box.top),
      right: box.right, barRight: bar.right, panelRight: panel.right,
      followed: chip.classList.contains('is-followed'),
      named: !!label && label.getBoundingClientRect().width > 0,
    };
  });
}"""


def test_crowded_bar_collapses_to_logos_except_followed_run(live_dashboard):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = _launch_chromium(p)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.set_default_timeout(4500)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open_with_six_runs(page, live_dashboard)
            followed = page.evaluate("storyRun().id")

            chips = page.evaluate(BAR_LAYOUT)
            # One line, and nothing runs off the panel.
            assert len({c["top"] for c in chips}) == 1
            assert all(c["right"] <= c["panelRight"] + 0.5 for c in chips)
            # Only the Followed Run keeps its name; the others are logos named on hover.
            assert [c["id"] for c in chips if c["followed"]] == [followed]
            assert [c["id"] for c in chips if c["named"]] == [followed]
            names = page.evaluate("activeRuns().map(r => [r.id, r.model])")
            titles = {c["id"]: c["title"] for c in chips}
            for run_id, model in names:
                assert model in titles[run_id]

            # A logo can still be removed from view: its × shows on hover.
            collapsed = page.locator(".run-chip:not(.is-followed)").last
            collapsed.hover()
            collapsed.locator(".run-chip-remove").click()
            page.wait_for_function("document.querySelectorAll('.run-chip').length === 5")

            # Widening the window brings the full chips back.
            page.set_viewport_size({"width": 2560, "height": 900})
            page.wait_for_function(
                "[...document.querySelectorAll('.run-chip-label')].every(l => l.getBoundingClientRect().width > 0)"
            )
            assert len({c["top"] for c in page.evaluate(BAR_LAYOUT)}) == 1
            assert not errors
        finally:
            browser.close()


ARROWS = """() => {
  const visible = sel => {
    const el = document.querySelector(sel);
    return getComputedStyle(el).display !== 'none' && el.getBoundingClientRect().width > 0;
  };
  const mask = getComputedStyle(document.querySelector('#selectedRunChips'));
  return {
    back: visible('.model-bar-arrow[data-scroll="-1"]'),
    more: visible('.model-bar-arrow[data-scroll="1"]'),
    faded: (mask.maskImage || mask.webkitMaskImage || 'none') !== 'none',
  };
}"""


def test_overflowing_logos_get_scroll_arrows_and_fades(live_dashboard):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = _launch_chromium(p)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.set_default_timeout(4500)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            _open_with_six_runs(page, live_dashboard)
            # Room for barely a couple of logos: six Runs never overflow this far at real
            # desktop widths, so squeeze the panel itself.
            squeeze = page.add_style_tag(content=".control-strip { max-width: 260px; }")
            page.wait_for_function(
                "!document.querySelector('.model-bar-arrow[data-scroll=\"1\"]').classList.contains('is-hidden')"
            )
            assert page.evaluate(ARROWS) == {"back": False, "more": True, "faded": True}
            chips = page.evaluate(BAR_LAYOUT)
            assert len({c["top"] for c in chips}) == 1

            # Scrolling to the end flips the arrows.
            for _ in range(10):
                if not page.evaluate(ARROWS)["more"]:
                    break
                page.locator('.model-bar-arrow[data-scroll="1"]').click()
                page.wait_for_timeout(450)
            assert page.evaluate(ARROWS) == {"back": True, "more": False, "faded": True}
            page.locator('.model-bar-arrow[data-scroll="-1"]').click()
            page.wait_for_timeout(450)
            assert page.evaluate(ARROWS)["more"]

            # Room again: no arrows, no fades.
            squeeze.evaluate("el => el.remove()")
            page.wait_for_function(
                "document.querySelector('.model-bar-arrow[data-scroll=\"-1\"]').classList.contains('is-hidden')"
                " && document.querySelector('.model-bar-arrow[data-scroll=\"1\"]').classList.contains('is-hidden')"
            )
            assert page.evaluate(ARROWS) == {"back": False, "more": False, "faded": False}
            assert not errors
        finally:
            browser.close()
