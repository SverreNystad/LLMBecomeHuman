"""The real dashboard on a phone (390x844, touch): the first tap on a model's logo on a
Flowchart node unfolds its decision card, and the chart glides so the node and the whole
card sit in the visible chart area, like a tapped node's dialogue (#81, after #67).

Needs Playwright and a Chromium executable on PATH, like test_phone_browser.py.
"""

from __future__ import annotations

import pytest

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


def decision_node(page):
    """A node a model made a decision at, so its card has a choice and a reason."""
    return page.evaluate(
        """() => [...document.querySelectorAll('.flow-node .node-model-button')]
          .map(b => b.closest('.flow-node').dataset.nodeId)
          .find(id => state.rendered.graph.nodes.get(id)?.type === 'choice')"""
    )


def place_node_low(page, node_id, scale=0.6):
    """Zooms the chart out and pans so the node sits near the bottom right of the chart,
    where its card would run off the screen."""
    page.evaluate(
        """([id, scale]) => {
          const vp = document.getElementById('viewport').getBoundingClientRect();
          const n = state.rendered.graph.nodes.get(id);
          state.scale = scale;
          state.panX = vp.width - 20 - (n.x + n.width) * scale;
          state.panY = vp.height - 40 - (n.y + n.height) * scale;
          applyTransform();
        }""",
        [node_id, scale],
    )
    page.wait_for_timeout(GLIDE_MS)  # any glide still running ends first


def logo_point(page, node_id):
    box = page.locator(f"{node_selector(node_id)} .node-model-button").first.bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def first_tap(page, node_id):
    """A raw tap on the node's first model logo: a locator's tap may scroll the chart."""
    x, y = logo_point(page, node_id)
    page.touchscreen.tap(x, y)
    page.locator("#unfoldCard.is-open").wait_for()


def settle(page):
    """Waits for the chart's glide to end, and a frame for the card to catch up."""
    page.wait_for_function("!document.getElementById('graphWorld').classList.contains('is-gliding')")
    page.wait_for_timeout(100)


def test_the_first_tap_on_a_logo_glides_the_node_and_its_card_into_view(phone):
    page = phone
    open_flowchart(page)
    node_id = decision_node(page)
    assert node_id
    place_node_low(page, node_id)
    first_tap(page, node_id)
    settle(page)
    area = visible_chart_area(page)
    assert inside(rect(page, node_selector(node_id)), area), (rect(page, node_selector(node_id)), area)
    assert inside(rect(page, "#unfoldCard"), area), (rect(page, "#unfoldCard"), area)
    assert page.evaluate("state.scale") >= FLOOR - 1e-6
    assert not page.errors


def test_a_card_too_tall_to_fit_is_pinned_to_the_top_and_scrolls_inside(
    open_dashboard, detroit_dashboard
):
    page = ready(open_dashboard(detroit_dashboard, "phone"))
    open_flowchart(page)
    # A short phone screen: too little chart for the node and a whole card at the floor.
    page.set_viewport_size({"width": 390, "height": 420})
    page.wait_for_timeout(400)
    node_id = decision_node(page)
    place_node_low(page, node_id)
    first_tap(page, node_id)
    settle(page)
    area = visible_chart_area(page)
    node = rect(page, node_selector(node_id))
    card = rect(page, "#unfoldCard")
    assert abs(page.evaluate("state.scale") - FLOOR) < 1e-6
    # The node goes to the top of the visible area with its card right below ...
    assert area["top"] - 1 <= node["top"] <= area["top"] + 16, (node, area)
    assert node["bottom"] <= card["top"] <= node["bottom"] + 20, (node, card)
    assert inside(card, area), (card, area)
    # ... and the card scrolls inside itself.
    assert page.evaluate(
        "() => { const b = document.querySelector('#unfoldCard .unfold-card-body'); return b.scrollHeight > b.clientHeight + 1; }"
    )
    assert not page.errors


def test_the_second_tap_on_the_logo_opens_the_reasoning_sheet(phone):
    page = phone
    open_flowchart(page)
    node_id = decision_node(page)
    place_node_low(page, node_id)
    first_tap(page, node_id)
    settle(page)
    assert page.locator("#reasoningDrawer.is-hidden").count() == 1
    # The logo has moved with the chart; tap it where it is now.
    x, y = logo_point(page, node_id)
    page.touchscreen.tap(x, y)
    page.locator("#reasoningDrawer").wait_for()
    assert page.evaluate("state.selected.id") == node_id
    assert not page.errors


def test_the_card_fit_respects_reduced_motion(open_dashboard, detroit_dashboard):
    page = ready(open_dashboard(detroit_dashboard, "phone", reduced_motion="reduce"))
    open_flowchart(page)
    node_id = decision_node(page)
    place_node_low(page, node_id)
    first_tap(page, node_id)
    # No glide: the chart, and the card with it, are where they end up straight away.
    assert not page.evaluate("document.getElementById('graphWorld').classList.contains('is-gliding')")
    page.wait_for_timeout(100)
    area = visible_chart_area(page)
    assert inside(rect(page, node_selector(node_id)), area)
    assert inside(rect(page, "#unfoldCard"), area)
    assert not page.errors


def test_wider_screens_do_not_move_the_chart_for_a_card(open_dashboard, detroit_dashboard):
    page = ready(
        open_dashboard(detroit_dashboard, {"width": 1024, "height": 768}, touch=True)
    )
    assert not page.evaluate("document.body.classList.contains('is-phone')")
    open_flowchart(page)
    node_id = decision_node(page)
    place_node_low(page, node_id)
    before = page.evaluate("[state.scale, state.panX, state.panY]")
    first_tap(page, node_id)
    settle(page)
    assert page.evaluate("[state.scale, state.panX, state.panY]") == before
    # The card still unfolds beside its marker.
    assert page.evaluate("document.getElementById('unfoldCard').dataset.side") in ("left", "right")
    assert not page.errors
