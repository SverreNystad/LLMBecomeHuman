"""The Ending Summary card at the top of Final Routes in the Story (#82).

Runs the real dashboard over the Detroit demo Runs in Chromium through Playwright; skips
without a browser. Screenshots go to docs/images/ending_summary_*.png.
"""

from __future__ import annotations

import re
from pathlib import Path

SHOTS = Path(__file__).resolve().parents[1] / "docs" / "images"
SNAKE_CASE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")


def _open_final_routes(page):
    page.locator(".story-decision").first.wait_for(state="attached")
    page.evaluate("changeChapter('final')")
    card = page.locator("#storyContent .ending-summary")
    card.wait_for()
    return card


def test_desktop_card_opens_final_routes_with_a_column_per_shown_run(
    detroit_dashboard, open_dashboard
):
    # Tall enough for the whole card to fit in the Story pane, for the screenshot.
    page = open_dashboard(detroit_dashboard, {"width": 1440, "height": 1300})
    card = _open_final_routes(page)

    # It is the first thing in the chapter (after the synthetic-preview caveat).
    first = page.evaluate(
        "[...document.querySelector('#storyContent').children]"
        ".find(el => !el.matches('.story-caveat')).className"
    )
    assert "ending-summary" in first

    shown = page.evaluate("activeRuns().map(run => run.id)")
    assert len(shown) == 3
    columns = card.locator(".ending-run")
    assert [columns.nth(i).get_attribute("data-run-id") for i in range(3)] == shown
    # Side by side, in the Shown Runs' order.
    lefts = [columns.nth(i).bounding_box()["x"] for i in range(3)]
    assert lefts == sorted(lefts) and len(set(lefts)) == 3

    first_column = columns.first
    assert first_column.locator(".ending-character dt").all_text_contents() == [
        "Connor",
        "Kara",
        "Markus",
    ]
    assert first_column.locator(".ending-fates li").count() == 7
    assert first_column.locator(".ending-news li").count() == 3
    assert "recorded route" in card.locator(".ending-note").inner_text()

    text = card.inner_text()
    assert not SNAKE_CASE.search(text), SNAKE_CASE.search(text)
    assert not page.errors
    card.screenshot(path=str(SHOTS / "ending_summary_desktop.png"))


def test_an_unfinished_run_says_story_not_finished(detroit_dashboard, open_dashboard):
    page = open_dashboard(detroit_dashboard)
    _open_final_routes(page)
    page.evaluate(
        """() => {
          const id = activeRuns()[1].id, detail = state.details.get(id);
          state.details.set(id, {...detail, ending_summary: {...detail.ending_summary, finished: false}});
          storyCache.clear();
          return renderStory();
        }"""
    )
    column = page.locator(".ending-run").nth(1)
    column.locator(".ending-unfinished").wait_for()
    assert column.locator(".ending-unfinished").inner_text() == "Story not finished"
    assert column.locator(".ending-character").count() == 0


def test_phone_card_shows_only_the_followed_run(detroit_dashboard, open_dashboard):
    page = open_dashboard(detroit_dashboard, "phone")
    card = _open_final_routes(page)
    assert page.evaluate("document.body.classList.contains('is-phone')")
    columns = card.locator(".ending-run")
    assert columns.count() == 1
    assert columns.first.get_attribute("data-run-id") == page.evaluate("storyRun().id")
    box, width = card.bounding_box(), page.viewport_size["width"]
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert not SNAKE_CASE.search(card.inner_text())
    assert "recorded route" in card.locator(".ending-note").inner_text()
    page.screenshot(path=str(SHOTS / "ending_summary_phone.png"))


def test_other_chapters_have_no_card(detroit_dashboard, open_dashboard):
    page = open_dashboard(detroit_dashboard)
    page.locator(".story-decision").first.wait_for()
    assert page.locator(".ending-summary").count() == 0
