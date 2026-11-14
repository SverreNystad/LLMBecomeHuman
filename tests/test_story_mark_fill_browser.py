"""Story decision cards: the logo whose reason is shown is filled with its Run's colour.

Runs the real dashboard in Chromium through Playwright; skips without a browser.
"""

from __future__ import annotations

import re
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest
from detroit_benchmark.dashboard import create_app

PROJECT = Path(__file__).resolve().parents[1]

# Reads what the eye sees on a mark: its fill, border colour, shadows and icon colouring.
MARK_LOOK = """el => {
  const s = getComputedStyle(el), icon = el.querySelector('img, .mock-icon');
  const is = icon && getComputedStyle(icon);
  return {
    background: s.backgroundColor, border: s.borderTopColor, shadow: s.boxShadow,
    iconFilter: icon && icon.tagName === 'IMG' ? is.filter : null,
    iconColor: icon && icon.tagName !== 'IMG' ? is.color : null,
  };
}"""


@pytest.fixture
def live_dashboard(tmp_path):
    """The real dashboard on a local port, so pages have an origin and assets load."""
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


def _open_story(page, url):
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
    card = page.locator(".story-decision").first
    card.wait_for()
    return card


def _shadows(value):
    """Splits a computed box-shadow into its layers (commas inside rgba() kept)."""
    if not value or value == "none":
        return []
    return [s.strip() for s in re.split(r",(?![^(]*\))", value)]


def _is_visible_outer(shadow):
    """An outer (non-inset) shadow that paints something: spread or blur above zero."""
    if "inset" in shadow or "rgba(0, 0, 0, 0)" in shadow:
        return False
    lengths = [float(n) for n in re.findall(r"(-?[\d.]+)px", shadow)]
    return any(n > 0 for n in lengths[2:])


def _assert_filled(look):
    assert look["background"] == look["border"], look  # flooded with its Run's colour
    assert look["background"] not in ("rgb(255, 255, 255)", "rgba(0, 0, 0, 0)")
    layers = _shadows(look["shadow"])
    assert not any(_is_visible_outer(s) for s in layers), look  # no outer ring
    assert any("inset" in s for s in layers), look  # a faint inner glow
    if look["iconFilter"] is not None:
        assert "invert(1)" in look["iconFilter"] and "brightness(0)" in look["iconFilter"]
    else:
        assert look["iconColor"] == "rgb(255, 255, 255)"


def test_followed_runs_mark_starts_filled_and_hover_keeps_outer_ring(live_dashboard):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = _launch_chromium(p)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(4500)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            card = _open_story(page, live_dashboard)
            followed = page.evaluate("storyRun().id")

            # Every decision card opens with the Followed Run's logo filled.
            cards = page.locator(".story-decision")
            for i in range(cards.count()):
                own = cards.nth(i).locator(f'.story-mark[data-why-run="{followed}"]')
                if own.count():
                    assert own.get_attribute("aria-pressed") == "true"
                    _assert_filled(own.evaluate(MARK_LOOK))

            # Hovering an unselected logo keeps today's soft outer ring, unfilled.
            other = card.locator(f'.story-mark:not([data-why-run="{followed}"])').first
            other.hover()
            page.wait_for_timeout(350)
            look = other.evaluate(MARK_LOOK)
            assert look["background"] == "rgb(255, 255, 255)"
            assert any(_is_visible_outer(s) for s in _shadows(look["shadow"])), look
            assert errors == []
        finally:
            browser.close()


def test_clicked_mark_fills_with_a_ring_shrinking_inward(live_dashboard):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = _launch_chromium(p)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(4500)
            card = _open_story(page, live_dashboard)
            followed = page.evaluate("storyRun().id")
            own = card.locator(f'.story-mark[data-why-run="{followed}"]')
            other = card.locator(f'.story-mark:not([data-why-run="{followed}"])').first

            other.click()
            # The ring's shrink plays as a box-shadow transition of about 250ms.
            durations = other.evaluate(
                """el => el.getAnimations()
                  .filter(a => a.transitionProperty === 'box-shadow')
                  .map(a => a.effect.getTiming().duration)"""
            )
            assert durations and all(230 <= d <= 300 for d in durations), durations

            page.mouse.move(0, 0)
            page.wait_for_timeout(400)
            _assert_filled(other.evaluate(MARK_LOOK))
            # The previously shown logo empties again.
            assert own.evaluate(MARK_LOOK)["background"] == "rgb(255, 255, 255)"
        finally:
            browser.close()


def test_clicked_mark_fills_without_animation_under_reduced_motion(live_dashboard):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = _launch_chromium(p)
        try:
            page = browser.new_page(
                viewport={"width": 1440, "height": 900}, reduced_motion="reduce"
            )
            page.set_default_timeout(4500)
            card = _open_story(page, live_dashboard)
            followed = page.evaluate("storyRun().id")
            other = card.locator(f'.story-mark:not([data-why-run="{followed}"])').first

            other.click()
            durations = other.evaluate(
                "el => el.getAnimations().map(a => a.effect.getTiming().duration)"
            )
            assert all(d < 1 for d in durations), durations
            page.mouse.move(0, 0)
            page.wait_for_timeout(50)
            _assert_filled(other.evaluate(MARK_LOOK))
        finally:
            browser.close()
