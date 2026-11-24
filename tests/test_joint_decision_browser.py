"""A Joint Decision in the Story: the decision card names both Characters and says the
choice was made with both their memories (ADR 0005).

Runs the real dashboard over the Synthetic Runs in Chromium through Playwright; the
first decision's story beat is made a Joint Decision in flight, worded as the server
words one. Skips without a browser.
"""

from __future__ import annotations

import json

from detroit_benchmark.run_timeline import decision_question

JOINT = "Decided with Markus's and Connor's memories"


def _as_joint(route):
    body = route.fetch().json()
    decision = next(m for m in body["moments"] if m.get("type") == "decision")
    decision["deciders"] = ["Markus", "Connor"]
    decision["decided"] = JOINT
    decision["question"] = decision_question(None, decision["deciders"])
    route.fulfill(content_type="application/json", body=json.dumps(body))


def test_a_joint_decision_card_says_whose_memories_decided(live_dashboard, open_dashboard):
    page = open_dashboard(live_dashboard, timeout=4500)
    page.route("**/api/runs/*/story?*", _as_joint)
    page.reload()
    page.keyboard.press("Enter")
    card = page.locator(".story-decision").first
    card.wait_for()
    assert card.locator("h3").inner_text() == "What do Markus and Connor do?"
    line = card.locator(".story-deciders")
    assert line.inner_text() == JOINT
    order = card.evaluate("el => [...el.children].map(c => c.className.split(' ')[0])")
    assert order.index("story-deciders") < order.index("story-options")
    color = line.evaluate("el => getComputedStyle(el).color")
    assert color != "rgba(0, 0, 0, 0)"
    # Only the joint decision has the line.
    assert page.locator(".story-deciders").count() == 1
    assert page.errors == []


def _as_markus_alone(route):
    body = route.fetch().json()
    decision = next(m for m in body["moments"] if m.get("type") == "decision")
    decision.update(
        deciders=["Markus"],
        character="Markus",
        decided="Decided as Markus",
        question=decision_question("Markus", ["Markus"]),
    )
    route.fulfill(content_type="application/json", body=json.dumps(body))


def test_a_decision_by_another_character_says_who_decided(live_dashboard, open_dashboard):
    page = open_dashboard(live_dashboard, timeout=4500)
    page.route("**/api/runs/*/story?*", _as_markus_alone)
    page.reload()
    page.keyboard.press("Enter")
    card = page.locator(".story-decision").first
    card.wait_for()
    assert card.locator("h3").inner_text() == "What does Markus do?"
    assert card.locator(".story-deciders").inner_text() == "Decided as Markus"
    assert page.errors == []
