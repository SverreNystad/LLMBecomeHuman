"""The README's Flowchart and Story screenshots, over the six Synthetic Runs with the
Synthetic Scene Art installed, in Chromium through Playwright; skips without a browser.

Screenshots go to the test's temporary folder (docs/images/readme_*.png with
UPDATE_DOC_SCREENSHOTS=1). Chapter 26 is where the six Runs' routes differ most, and
both shots show its decision that splits the models the most ways.
"""

from __future__ import annotations

CHAPTER = "26"


def _open_widest_split(page):
    """Opens the chapter in the Story at the decision the models split on most ways."""
    page.locator(".story-decision").first.wait_for(state="attached")
    page.evaluate(f"changeChapter('{CHAPTER}')")
    page.wait_for_function(f"state.chapter === '{CHAPTER}'")
    assert page.evaluate("activeRuns().length") == 6
    split = page.locator(".story-decision:has(.story-agreement.splits)")
    split.first.wait_for()
    ways = [
        len(split.nth(i).locator(".story-agreement").inner_text().split("/"))
        for i in range(split.count())
    ]
    assert max(ways) >= 3
    widest = split.nth(ways.index(max(ways)))
    widest.evaluate("el => el.scrollIntoView({block: 'center'})")
    page.wait_for_timeout(300)
    return widest.get_attribute("data-moment")


def _wait_for_art(page):
    page.locator(".backdrop-art-layer.is-shown").wait_for(state="attached")
    page.wait_for_timeout(1500)  # the art fades in


def test_flowchart_draws_every_run_over_the_chapter(
    detroit_dashboard_with_art, open_dashboard, shots
):
    page = open_dashboard(detroit_dashboard_with_art, timeout=15000)
    moment = _open_widest_split(page)
    # As a click on the decision in the Story does: the Flowchart, centred on it.
    page.evaluate("moment => showMomentOnFlowchart(moment)", moment)
    page.locator(".flow-node.selected").wait_for()
    page.evaluate("closeDrawer()")
    _wait_for_art(page)
    assert not page.errors
    page.screenshot(path=str(shots / "readme_flowchart.png"))


def test_story_shows_where_the_models_split(
    detroit_dashboard_with_art, open_dashboard, shots
):
    page = open_dashboard(detroit_dashboard_with_art, timeout=15000)
    _open_widest_split(page)
    _wait_for_art(page)
    assert not page.errors
    page.screenshot(path=str(shots / "readme_story.png"))
