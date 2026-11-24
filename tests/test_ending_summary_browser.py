"""The Ending Summary card at the top of Final Routes in the Story (#82).

Runs the real dashboard over the Synthetic Runs in Chromium through Playwright; skips
without a browser. Screenshots go to the test's temporary folder
(docs/images/ending_summary_*.png with UPDATE_DOC_SCREENSHOTS=1).
"""

from __future__ import annotations

import re

SNAKE_CASE = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")


def _open_final_routes(page):
    page.locator(".story-decision").first.wait_for(state="attached")
    page.evaluate("changeChapter('final')")
    card = page.locator("#storyContent .ending-summary")
    card.wait_for()
    return card


def test_desktop_card_opens_final_routes_with_a_column_per_shown_run(
    detroit_dashboard, open_dashboard, shots
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
    assert len(shown) == 6
    columns = card.locator(".ending-run")
    assert [columns.nth(i).get_attribute("data-run-id") for i in range(6)] == shown
    # Side by side, in the Shown Runs' order.
    lefts = [columns.nth(i).bounding_box()["x"] for i in range(6)]
    assert lefts == sorted(lefts) and len(set(lefts)) == 6

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
    card.screenshot(path=str(shots / "ending_summary_desktop.png"))


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


def test_columns_scroll_sideways_instead_of_overlapping_when_the_pane_is_narrow(
    detroit_dashboard, open_dashboard
):
    page = open_dashboard(detroit_dashboard, {"width": 1024, "height": 900})
    card = _open_final_routes(page)
    columns = card.locator(".ending-run")
    boxes = [columns.nth(i).bounding_box() for i in range(columns.count())]
    assert len(boxes) == 6
    # Each column keeps its width and starts after the previous one ends.
    assert all(box["width"] >= 280 for box in boxes)
    assert all(b["x"] >= a["x"] + a["width"] for a, b in zip(boxes, boxes[1:]))
    # The row of columns scrolls inside the card; the card stays within the window.
    row = card.locator(".ending-columns")
    assert row.evaluate("el => el.scrollWidth > el.clientWidth")
    assert row.evaluate("el => getComputedStyle(el).overflowX") == "auto"
    box = card.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= page.viewport_size["width"]
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    # The scrollbar gets its own strip below the columns, so it never covers text
    # (overlay scrollbars draw inside the row, over its bottom edge).
    gap = row.evaluate(
        """row => {
          // The inner edge: a scrollbar that takes up layout space doesn't count.
          const bottom = row.getBoundingClientRect().top + row.clientTop + row.clientHeight;
          const texts = [...row.querySelectorAll('.ending-run *')].filter(el => el.textContent.trim());
          return bottom - Math.max(...texts.map(el => el.getBoundingClientRect().bottom));
        }"""
    )
    assert gap >= 15, gap  # 16px, less clientHeight's rounding


def test_phone_card_stacks_every_shown_run_with_the_followed_run_first(
    detroit_dashboard, open_dashboard, shots
):
    page = open_dashboard(detroit_dashboard, "phone")
    card = _open_final_routes(page)
    assert page.evaluate("document.body.classList.contains('is-phone')")
    shown = page.evaluate("activeRuns().map(run => run.id)")
    followed = page.evaluate("storyRun().id")
    columns = card.locator(".ending-run")
    ids = [columns.nth(i).get_attribute("data-run-id") for i in range(columns.count())]
    assert ids == [followed] + [run_id for run_id in shown if run_id != followed]
    # One above the other, each the card's full width.
    boxes = [columns.nth(i).bounding_box() for i in range(len(ids))]
    assert all(b["y"] >= a["y"] + a["height"] for a, b in zip(boxes, boxes[1:]))
    assert len({round(box["x"]) for box in boxes}) == 1
    box, width = card.bounding_box(), page.viewport_size["width"]
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    assert not SNAKE_CASE.search(card.inner_text())
    assert "recorded route" in card.locator(".ending-note").inner_text()
    page.screenshot(path=str(shots / "ending_summary_phone.png"))


def test_other_chapters_have_no_card(detroit_dashboard, open_dashboard):
    page = open_dashboard(detroit_dashboard)
    page.locator(".story-decision").first.wait_for()
    assert page.locator(".ending-summary").count() == 0
