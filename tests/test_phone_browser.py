"""The real dashboard on a phone (390x844, touch): the three-level layout (#36).

Needs Playwright and a Chromium executable on PATH, like test_frontend_browser.py.
Screenshots are written to docs/images/phone_*.png.
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
SHOTS = PROJECT / "docs" / "images"
PHONE = {"width": 390, "height": 844}


@pytest.fixture
def detroit_dashboard(tmp_path):
    uvicorn = pytest.importorskip("uvicorn")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(PROJECT / "demo_runs" / "detroit", images_dir=tmp_path)
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


@pytest.fixture
def phone(detroit_dashboard):
    playwright = pytest.importorskip("playwright.sync_api")
    binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        pytest.skip("Chromium executable unavailable")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=binary, args=["--no-sandbox"])
        try:
            context = browser.new_context(
                viewport=PHONE, has_touch=True, is_mobile=True, device_scale_factor=2
            )
            page = context.new_page()
            page.set_default_timeout(6000)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(detroit_dashboard)
            page.locator("#titleScreen").wait_for()
            page.wait_for_timeout(400)
            page.touchscreen.tap(195, 420)
            page.locator("#titleScreen").wait_for(state="detached")
            page.locator(".story-decision").first.wait_for()
            page.errors = errors
            yield page
        finally:
            browser.close()


def on_screen(page, selector):
    box = page.locator(selector).first.bounding_box()
    return bool(box) and box["y"] >= 0 and box["y"] + box["height"] <= PHONE["height"]


def swipe(page, selector, dy):
    page.evaluate(
        """([selector, dy]) => {
          const el = document.querySelector(selector), r = el.getBoundingClientRect();
          const x = r.left + r.width / 2, y = r.top + r.height / 2;
          const touch = (cy) => new Touch({identifier: 1, target: el, clientX: x, clientY: cy});
          el.dispatchEvent(new TouchEvent('touchstart', {touches: [touch(y)], changedTouches: [touch(y)], bubbles: true}));
          el.dispatchEvent(new TouchEvent('touchend', {touches: [], changedTouches: [touch(y + dy)], bubbles: true}));
        }""",
        [selector, dy],
    )


def scroll_story(page, to):
    page.evaluate(
        "y => { const s = document.getElementById('storyScroll'); s.scrollTop = y; s.dispatchEvent(new Event('scroll')); }",
        to,
    )
    page.wait_for_timeout(350)


LEVEL1 = ["#chapterList", ".view-tabs", "#pickerToggle"]


def test_phone_story_keeps_level_one_on_screen_and_hides_level_two(phone):
    page = phone
    assert page.evaluate("document.body.classList.contains('is-phone')")
    assert not page.locator("#selectedRunChips").is_visible()
    assert page.locator(".phone-l3 .brand").is_visible()
    # Middle of a long chapter: level 1 stays, levels 2 and 3 have gone.
    middle = page.evaluate("document.getElementById('storyScroll').scrollHeight / 2")
    assert middle > 1500
    scroll_story(page, middle)
    assert page.evaluate("document.body.classList.contains('phone-scrolled')")
    assert page.evaluate("document.body.classList.contains('phone-l2-hidden')")
    for selector in LEVEL1:
        assert on_screen(page, selector), selector
    assert not page.locator(".phone-l2 .story-toolbar").is_visible()
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / "phone_story_scrolled.png"))
    # A small scroll up brings level 2 back; level 3 only returns at the top.
    scroll_story(page, middle - 40)
    assert not page.evaluate("document.body.classList.contains('phone-l2-hidden')")
    assert page.evaluate("document.body.classList.contains('phone-scrolled')")
    page.screenshot(path=str(SHOTS / "phone_story_level2.png"))
    scroll_story(page, 0)
    assert not page.evaluate("document.body.classList.contains('phone-scrolled')")
    assert not page.errors


def test_phone_chapter_row_swipes_and_changes_chapter(phone):
    page = phone
    row = page.locator("#chapterList")
    assert page.evaluate(
        "(() => { const r = document.getElementById('chapterList'); return r.scrollWidth > r.clientWidth; })()"
    )
    before = page.locator("#chapterTitle").inner_text()
    target = page.locator("#chapterList .chapter-entry").nth(4)
    target.scroll_into_view_if_needed()
    target.tap()
    page.wait_for_function(
        "t => document.getElementById('chapterTitle').innerText !== t", arg=before
    )
    active = page.locator("#chapterList .chapter-entry.active").bounding_box()
    box = row.bounding_box()
    assert active["x"] >= box["x"] - 1 and active["x"] + active["width"] <= box["x"] + box["width"] + 1
    assert not page.errors


def test_phone_flowchart_fills_the_screen_and_swiping_the_bars_grows_it(phone):
    page = phone
    page.locator("#viewFlow").tap()
    page.locator(".flow-node").first.wait_for()
    page.wait_for_timeout(400)
    assert not page.locator(".phone-l2 .story-toolbar").is_visible()
    chart = page.locator("#viewport").bounding_box()
    assert chart["y"] + chart["height"] >= PHONE["height"] - 2
    swipe(page, "#phoneBar", -60)
    page.wait_for_timeout(450)
    assert page.evaluate("document.body.classList.contains('phone-l2-hidden')")
    taller = page.locator("#viewport").bounding_box()
    assert taller["height"] > chart["height"] + 20
    for selector in LEVEL1:
        assert on_screen(page, selector), selector
    page.screenshot(path=str(SHOTS / "phone_flowchart.png"))
    swipe(page, "#phoneBar", 60)
    page.wait_for_timeout(450)
    assert not page.evaluate("document.body.classList.contains('phone-l2-hidden')")
    assert not page.errors


def test_wider_screens_keep_todays_layout(detroit_dashboard):
    playwright = pytest.importorskip("playwright.sync_api")
    binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        pytest.skip("Chromium executable unavailable")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=binary, args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": 1024, "height": 768})
            page.goto(detroit_dashboard)
            page.locator(".story-decision").first.wait_for(state="attached")
            assert not page.evaluate("document.body.classList.contains('is-phone')")
            assert page.locator(".chapter-rail #chapterList").count() == 1
            assert page.locator(".control-strip #selectedRunChips").is_visible()
            # Turning a phone to landscape (844 wide) restores the normal layout.
            page.set_viewport_size({"width": 390, "height": 844})
            page.wait_for_function("document.body.classList.contains('is-phone')")
            page.set_viewport_size({"width": 844, "height": 390})
            page.wait_for_function("!document.body.classList.contains('is-phone')")
            assert page.locator(".chapter-rail #chapterList").count() == 1
            assert page.locator(".chapter-heading .view-tabs").count() == 1
        finally:
            browser.close()


def test_phone_levels_respect_reduced_motion(detroit_dashboard):
    playwright = pytest.importorskip("playwright.sync_api")
    binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        pytest.skip("Chromium executable unavailable")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=binary, args=["--no-sandbox"])
        try:
            context = browser.new_context(
                viewport=PHONE, has_touch=True, is_mobile=True, reduced_motion="reduce"
            )
            page = context.new_page()
            page.goto(detroit_dashboard)
            page.locator(".phone-l2").wait_for(state="attached")
            duration = page.evaluate(
                "parseFloat(getComputedStyle(document.querySelector('.phone-l2')).transitionDuration)"
            )
            assert duration < 0.01
        finally:
            browser.close()
