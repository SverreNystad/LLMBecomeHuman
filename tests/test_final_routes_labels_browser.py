"""Readable Final Routes labels in the Flowchart (#83), in Chromium through Playwright;
skips without a browser."""

from __future__ import annotations

import re

SNAKE_CASE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")


def test_final_routes_nodes_read_like_the_story(detroit_dashboard, open_dashboard):
    page = open_dashboard(detroit_dashboard)
    page.locator("#viewFlow").click()
    page.locator(".flow-node").first.wait_for()
    page.evaluate("changeChapter('final')")
    page.locator('.flow-node[data-node-id="route_kara_final"]').wait_for()

    # The label's own text; CSS may show it in capitals.
    def label(node_id):
        return page.locator(f'.flow-node[data-node-id="{node_id}"] .node-label').text_content()

    assert label("route_kara_final") == "Was Kara captured?"
    assert label("route_connor_final") == "Did Connor become deviant?"
    assert label("route_markus_final") == "Was Markus's revolution peaceful?"

    # Each question is read in full, not cut off by the node.
    clipped = page.evaluate(
        "[...document.querySelectorAll('.flow-node.kind-junction .node-label')]"
        ".filter(el => el.scrollHeight > el.clientHeight + 1"
        " || el.getBoundingClientRect().bottom > el.parentElement.getBoundingClientRect().bottom + 1)"
        ".map(el => el.textContent)"
    )
    assert clipped == []

    labels = page.locator(".flow-node .node-label").all_text_contents()
    assert labels
    for text in labels:
        assert not SNAKE_CASE.search(text), text
        assert text != "STORY BRANCH"
    assert not page.errors
