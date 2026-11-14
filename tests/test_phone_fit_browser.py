"""The real dashboard on a phone (390x844, touch): the Flowchart keeps what you are reading
on screen. A tapped node's dialogue fits in the visible chart area (#67), and the reasoning
sheet opens shorter and the chart works around it (#68).

Needs Playwright and a Chromium executable on PATH, like test_phone_browser.py.
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
PHONE = {"width": 390, "height": 844}
FLOOR = 0.85
GLIDE_MS = 800


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
def browser():
    playwright = pytest.importorskip("playwright.sync_api")
    binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        pytest.skip("Chromium executable unavailable")
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=binary, args=["--no-sandbox"])
        try:
            yield b
        finally:
            b.close()


def open_dashboard(browser, url, viewport=PHONE, **options):
    context = browser.new_context(
        viewport=viewport, has_touch=True, is_mobile=True, device_scale_factor=2, **options
    )
    page = context.new_page()
    page.set_default_timeout(6000)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url)
    page.locator("#titleScreen").wait_for()
    page.wait_for_timeout(400)
    page.touchscreen.tap(viewport["width"] / 2, viewport["height"] / 2)
    page.locator("#titleScreen").wait_for(state="detached")
    page.locator(".story-decision").first.wait_for(state="attached")
    page.errors = errors
    return page


@pytest.fixture
def phone(browser, detroit_dashboard):
    return open_dashboard(browser, detroit_dashboard)


def open_flowchart(page):
    page.locator("#viewFlow").tap()
    page.locator(".flow-node").first.wait_for()
    page.wait_for_timeout(500)


def visible_chart_area(page):
    """The Flowchart's rectangle on screen, minus the reasoning sheet when it is open."""
    return page.evaluate(
        """() => {
          const vp = document.getElementById('viewport').getBoundingClientRect();
          const sheet = document.getElementById('reasoningDrawer');
          let bottom = vp.bottom;
          if (!sheet.classList.contains('is-hidden')) bottom = Math.min(bottom, sheet.getBoundingClientRect().top);
          return {left: vp.left, top: vp.top, right: vp.right, bottom};
        }"""
    )


def rect(page, selector):
    return page.evaluate(
        "s => { const r = document.querySelector(s).getBoundingClientRect(); return {left: r.left, top: r.top, right: r.right, bottom: r.bottom}; }",
        selector,
    )


def inside(inner, outer, slack=1):
    return (
        inner["left"] >= outer["left"] - slack
        and inner["right"] <= outer["right"] + slack
        and inner["top"] >= outer["top"] - slack
        and inner["bottom"] <= outer["bottom"] + slack
    )


def node_selector(node_id):
    return f'.flow-node[data-node-id="{node_id}"]'


def place_node_low(page, node_id, scale=0.6):
    """Zooms the chart out and pans so the node sits near the bottom of the chart, where its
    dialogue would run off the screen."""
    page.evaluate(
        """([id, scale]) => {
          const vp = document.getElementById('viewport').getBoundingClientRect();
          const n = state.rendered.graph.nodes.get(id);
          state.scale = scale;
          state.panX = vp.width / 2 - (n.x + n.width / 2) * scale;
          state.panY = vp.height - 70 - n.y * scale;
          applyTransform();
        }""",
        [node_id, scale],
    )


def dialogue_node(page, overflowing=False):
    """A node with dialogue; with overflowing, one whose dialogue scrolls inside itself."""
    return page.evaluate(
        """overflowing => {
          const nodes = [...document.querySelectorAll('.flow-node:has(.node-dialogue)')];
          const pick = nodes.find(n => {
            const d = n.querySelector('.node-dialogue');
            return !overflowing || d.scrollHeight > d.clientHeight + 4;
          });
          return pick && pick.dataset.nodeId;
        }""",
        overflowing,
    )


def tap_node(page, node_id):
    page.locator(node_selector(node_id)).tap(position={"x": 12, "y": 8})


# ── A tapped node's dialogue fits on screen (#67) ─────────


def test_a_tapped_nodes_dialogue_glides_into_the_visible_chart_area(phone):
    page = phone
    open_flowchart(page)
    node_id = dialogue_node(page)
    assert node_id
    place_node_low(page, node_id)
    sel = node_selector(node_id)
    tap_node(page, node_id)
    assert "is-peeked" in page.locator(sel).get_attribute("class")
    page.wait_for_timeout(GLIDE_MS)
    area = visible_chart_area(page)
    assert inside(rect(page, sel), area)
    assert inside(rect(page, f"{sel} .node-dialogue"), area)
    assert page.evaluate("state.scale") >= FLOOR - 1e-6
    assert not page.errors


def test_a_dialogue_too_tall_to_fit_puts_the_node_at_the_top_and_scrolls(browser, detroit_dashboard):
    page = open_dashboard(browser, detroit_dashboard)
    open_flowchart(page)
    # A short phone screen: too little chart for a long dialogue at the zoom floor.
    page.set_viewport_size({"width": 390, "height": 380})
    page.wait_for_timeout(400)
    node_id = dialogue_node(page, overflowing=True)
    assert node_id
    place_node_low(page, node_id)
    sel = node_selector(node_id)
    tap_node(page, node_id)
    page.wait_for_timeout(GLIDE_MS)
    area = visible_chart_area(page)
    node = rect(page, sel)
    dialogue = rect(page, f"{sel} .node-dialogue")
    # It cannot fit at the zoom floor, so the node's top goes to the top of the area ...
    assert (dialogue["bottom"] - node["top"]) > (area["bottom"] - area["top"])
    assert abs(page.evaluate("state.scale") - FLOOR) < 1e-6
    assert area["top"] - 1 <= node["top"] <= area["top"] + 16
    # ... and the dialogue still scrolls inside itself.
    assert page.evaluate(
        "s => { const d = document.querySelector(s); return d.scrollHeight > d.clientHeight; }",
        f"{sel} .node-dialogue",
    )
    assert not page.errors


def test_the_dialogue_glide_respects_reduced_motion(browser, detroit_dashboard):
    page = open_dashboard(browser, detroit_dashboard, reduced_motion="reduce")
    open_flowchart(page)
    node_id = dialogue_node(page)
    place_node_low(page, node_id)
    sel = node_selector(node_id)
    tap_node(page, node_id)
    # No glide: the chart is where it ends up straight away.
    assert not page.evaluate("document.getElementById('graphWorld').classList.contains('is-gliding')")
    page.wait_for_timeout(100)
    area = visible_chart_area(page)
    assert inside(rect(page, f"{sel} .node-dialogue"), area)
    assert not page.errors


def test_wider_screens_do_not_move_the_chart_for_a_dialogue(browser, detroit_dashboard):
    page = open_dashboard(browser, detroit_dashboard, viewport={"width": 1024, "height": 768})
    assert not page.evaluate("document.body.classList.contains('is-phone')")
    open_flowchart(page)
    node_id = dialogue_node(page)
    place_node_low(page, node_id)
    before = page.evaluate("[state.scale, state.panX, state.panY]")
    tap_node(page, node_id)
    page.wait_for_timeout(GLIDE_MS)
    assert page.evaluate("[state.scale, state.panX, state.panY]") == before
    assert not page.errors
