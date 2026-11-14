"""The real dashboard on a phone (390x844, touch): the Flowchart keeps what you are reading
on screen. A tapped node's dialogue fits in the visible chart area (#67), and the reasoning
sheet opens shorter and the chart works around it (#68).

Needs Playwright and a Chromium executable on PATH, like test_phone_browser.py.
"""

from __future__ import annotations

import pytest

PHONE = {"width": 390, "height": 844}
FLOOR = 0.85
GLIDE_MS = 800


def ready(page):
    page.locator(".story-decision").first.wait_for(state="attached")
    return page


@pytest.fixture
def phone(open_dashboard, detroit_dashboard):
    return ready(open_dashboard(detroit_dashboard, "phone"))


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


def test_a_dialogue_too_tall_to_fit_puts_the_node_at_the_top_and_scrolls(
    open_dashboard, detroit_dashboard
):
    page = ready(open_dashboard(detroit_dashboard, "phone"))
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


def test_the_dialogue_glide_respects_reduced_motion(open_dashboard, detroit_dashboard):
    page = ready(open_dashboard(detroit_dashboard, "phone", reduced_motion="reduce"))
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


def test_wider_screens_do_not_move_the_chart_for_a_dialogue(open_dashboard, detroit_dashboard):
    page = ready(
        open_dashboard(detroit_dashboard, {"width": 1024, "height": 768}, touch=True)
    )
    assert not page.evaluate("document.body.classList.contains('is-phone')")
    open_flowchart(page)
    node_id = dialogue_node(page)
    place_node_low(page, node_id)
    before = page.evaluate("[state.scale, state.panX, state.panY]")
    tap_node(page, node_id)
    page.wait_for_timeout(GLIDE_MS)
    assert page.evaluate("[state.scale, state.panX, state.panY]") == before
    assert not page.errors


# ── A shorter reasoning sheet the chart works around (#68) ─


def open_moment(page):
    """Opens a Moment's details from a model's marker: the first tap shows its card, the
    second the sheet. Returns the selected node's id."""
    index = page.evaluate(
        """() => {
          const vp = document.getElementById('viewport').getBoundingClientRect();
          return [...document.querySelectorAll('.flow-node.visited .node-model-button')].findIndex(m => {
            const r = m.getBoundingClientRect();
            return r.left >= vp.left && r.right <= vp.right && r.top >= vp.top && r.bottom <= vp.bottom;
          });
        }"""
    )
    assert index >= 0, "no model marker on screen"
    box = page.locator(".flow-node.visited .node-model-button").nth(index).bounding_box()
    # Raw taps: a locator's tap may scroll the chart's own box to reach the marker.
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.touchscreen.tap(x, y)
    page.locator("#unfoldCard.is-open").wait_for()
    page.touchscreen.tap(x, y)
    page.locator("#reasoningDrawer").wait_for()
    page.wait_for_timeout(GLIDE_MS)
    return page.evaluate("state.selected.id")


def drag_grip(page, dy):
    page.evaluate(
        """dy => {
          const grip = document.querySelector('.drawer-grip'), r = grip.getBoundingClientRect();
          const x = r.left + r.width / 2, y = r.top + r.height / 2;
          const fire = (type, d) => grip.dispatchEvent(new PointerEvent(type, {pointerId: 7, pointerType: 'touch', isPrimary: true, clientX: x, clientY: y + d, bubbles: true}));
          fire('pointerdown', 0);
          for (let i = 1; i <= 6; i++) fire('pointermove', dy * i / 6);
          fire('pointerup', dy);
        }""",
        dy,
    )
    page.wait_for_timeout(GLIDE_MS)


def sheet_height(page):
    return page.locator("#reasoningDrawer").bounding_box()["height"]


def assert_shown_above_sheet(page, selector):
    area = visible_chart_area(page)
    assert inside(rect(page, selector), area), (rect(page, selector), area)
    assert page.evaluate("state.scale") >= FLOOR - 1e-6


def test_a_moment_opens_a_sheet_at_about_45_percent_with_its_node_above(phone):
    page = phone
    open_flowchart(page)
    node_id = open_moment(page)
    assert 0.40 * PHONE["height"] <= sheet_height(page) <= 0.50 * PHONE["height"]
    box = page.locator("#reasoningDrawer").bounding_box()
    assert abs(box["y"] + box["height"] - PHONE["height"]) <= 2
    assert_shown_above_sheet(page, node_selector(node_id))
    assert not page.errors


def test_dragging_the_sheet_up_grows_it_to_70_percent_and_the_node_stays_above(phone):
    page = phone
    open_flowchart(page)
    node_id = open_moment(page)
    drag_grip(page, -400)
    assert 0.65 * PHONE["height"] <= sheet_height(page) <= 0.70 * PHONE["height"] + 2
    assert_shown_above_sheet(page, node_selector(node_id))
    # Back down to the opening height; the chart follows.
    drag_grip(page, 120)
    assert 0.40 * PHONE["height"] <= sheet_height(page) <= 0.50 * PHONE["height"]
    assert_shown_above_sheet(page, node_selector(node_id))
    # Dragging down far still closes it.
    drag_grip(page, 300)
    page.locator("#reasoningDrawer").wait_for(state="hidden")
    assert not page.errors


def test_the_selected_nodes_dialogue_fits_above_the_open_sheet(phone):
    page = phone
    open_flowchart(page)
    node_id = open_moment(page)
    sel = node_selector(node_id)
    if not page.locator(f"{sel} .node-dialogue").count():
        pytest.skip("the first visited node has no dialogue")
    tap_node(page, node_id)
    assert "is-peeked" in page.locator(sel).get_attribute("class")
    page.wait_for_timeout(GLIDE_MS)
    assert page.locator("#reasoningDrawer").is_visible()
    assert_shown_above_sheet(page, sel)
    assert_shown_above_sheet(page, f"{sel} .node-dialogue")
    assert not page.errors
