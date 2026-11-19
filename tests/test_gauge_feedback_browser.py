"""Gauge Feedback in the Story: the gauges the game flashed after the followed model's
choice read as a short line in its decision card.

Runs the real dashboard over the Detroit mock Runs in Chromium through Playwright; the
first decision's story beat is given feedback in flight. Skips without a browser.
"""

from __future__ import annotations

import json
import re

SNAKE_CASE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")
LINES = ["Probability of success: up sharply", "Relationship with Hank: down"]


def _with_feedback(route):
    body = route.fetch().json()
    decision = next(m for m in body["moments"] if m.get("type") == "decision")
    decision["feedback"] = LINES
    route.fulfill(content_type="application/json", body=json.dumps(body))


def test_a_decision_card_shows_what_the_game_flashed_on_screen(
    live_dashboard, open_dashboard
):
    page = open_dashboard(live_dashboard, timeout=4500)
    page.route("**/api/runs/*/story?*", _with_feedback)
    page.reload()
    page.keyboard.press("Enter")
    card = page.locator(".story-decision").first
    card.wait_for()
    line = card.locator(".story-feedback")
    assert line.locator("span").all_text_contents() == LINES
    text = line.inner_text()
    assert not SNAKE_CASE.search(text), text
    # Between the options and the model's reason, in the theme's colours.
    order = card.evaluate(
        "el => [...el.children].map(c => c.className.split(' ')[0])"
    )
    assert order.index("story-options") < order.index("story-feedback") < order.index(
        "story-why"
    )
    color = line.evaluate("el => getComputedStyle(el).color")
    soft = page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--ink-soft')"
    )
    assert color != "rgba(0, 0, 0, 0)" and soft.strip()
    # Only the decision given feedback has a line.
    assert page.locator(".story-feedback").count() == 1
    assert page.errors == []
