"""Switching the Followed Run keeps the Story's reading position (#65).

Drives the real dashboard over the Detroit demo runs, on a desktop and on a phone.
Needs Playwright and a Chromium executable on PATH, like test_frontend_browser.py.

In chapter 1 the cautious run reaches every scene; the wildcard run shares its later
decisions but skips the kitchen; the defiant run goes straight from the investigation to
going outside. Only the cautious run reached chapter 32.4.
"""

from __future__ import annotations

import base64

import pytest


def run_id(name):
    return base64.b64encode(f"detroit-mock-{name}".encode()).decode().rstrip("=")


CAUTIOUS, WILDCARD, DEFIANT = run_id("cautious"), run_id("wildcard"), run_id("defiant")


@pytest.fixture
def desktop(open_dashboard, detroit_dashboard):
    return _ready(open_dashboard(detroit_dashboard))


@pytest.fixture
def phone(open_dashboard, detroit_dashboard):
    page = _ready(open_dashboard(detroit_dashboard, "phone"))
    assert page.evaluate("document.body.classList.contains('is-phone')")
    return page


def _ready(page):
    page.locator(".story-decision").first.wait_for()
    assert page.evaluate("storyRun().id") == CAUTIOUS
    return page


# The scene heading or decision being read: the last one at or above the upper third of
# the story pane. Decisions are named by their node, headings by their text.
READING = """() => {
  const box = document.getElementById('storyScroll').getBoundingClientRect();
  const line = Math.max(box.top, 0) + Math.min(box.height, innerHeight) / 3;
  let current = null;
  for (const el of document.querySelectorAll('#storyContent .story-section, #storyContent .story-decision')) {
    if (!el.getClientRects().length) continue;
    if (current && el.getBoundingClientRect().top > line) break;
    current = el;
  }
  if (!current) return null;
  return {
    name: current.classList.contains('story-decision') ? current.dataset.moment : current.textContent,
    top: Math.round(current.getBoundingClientRect().top),
  };
}"""


def reading(page):
    return page.evaluate(READING)


def scroll_offsets(page):
    return page.evaluate(
        "[document.getElementById('storyScroll').scrollTop, document.querySelector('.main-panel').scrollTop]"
    )


def read_at(page, selector, above=10):
    """Scrolls so `selector` sits `above` pixels over the upper third of the story pane, being read."""
    page.locator(selector).first.evaluate(
        """(el, above) => {
          const scroller = document.getElementById('storyScroll'), box = scroller.getBoundingClientRect();
          const line = Math.max(box.top, 0) + Math.min(box.height, innerHeight) / 3;
          scroller.scrollTop += el.getBoundingClientRect().top - line + above;
          scroller.dispatchEvent(new Event('scroll'));
        }""",
        above,
    )
    page.wait_for_timeout(350)


def decision(node):
    return f'#storyContent .story-decision[data-moment="{node}"]'


def heading(text):
    return f'#storyContent .story-section:text-is("{text}")'


def follow_by_chip(page, run):
    version = page.evaluate("storyVersion")
    page.locator(f'.run-chip[data-focus-id="{run}"] .run-chip-label').click()
    settle(page, run, version)


def settle(page, run, version):
    page.wait_for_function(f"storyRun().id === {run!r}")
    page.wait_for_function(
        f"storyVersion > {version} && document.querySelector('#storyContent .story-section, #storyContent .story-empty')"
    )
    page.wait_for_timeout(400)


def test_following_another_run_keeps_the_decision_being_read(desktop):
    page = desktop
    read_at(page, decision("ch1_00063"))
    before = reading(page)
    assert before["name"] == "ch1_00063"
    follow_by_chip(page, WILDCARD)
    after = reading(page)
    assert after["name"] == "ch1_00063"
    assert abs(after["top"] - before["top"]) <= 2
    assert not page.errors


def test_a_run_that_skipped_the_scene_lands_on_the_nearest_earlier_one_it_reached(
    desktop,
):
    page = desktop
    read_at(page, heading("In the kitchen"))
    before = reading(page)
    assert before["name"] == "In the kitchen"
    follow_by_chip(page, DEFIANT)
    # The defiant run never went into the house; its last shared step is the investigation.
    after = reading(page)
    assert after["name"] == "ch1_x0001"
    assert abs(after["top"] - before["top"]) <= 2
    assert scroll_offsets(page)[0] > 0
    assert not page.errors


def test_clicking_the_followed_chip_keeps_the_scroll_position(desktop):
    page = desktop
    read_at(page, decision("ch1_00063"))
    before = scroll_offsets(page)
    assert before[0] > 0
    page.locator(f'.run-chip[data-focus-id="{CAUTIOUS}"] .run-chip-label').click()
    page.wait_for_timeout(400)
    assert scroll_offsets(page) == before
    assert reading(page)["name"] == "ch1_00063"
    assert not page.errors


def test_changing_chapter_still_opens_at_its_top(desktop):
    page = desktop
    follow_by_chip(page, WILDCARD)
    read_at(page, decision("ch1_00063"))
    assert scroll_offsets(page)[0] > 0
    page.locator('#chapterList [data-chapter="3"]').click()
    page.wait_for_function("state.chapter === '3'")
    page.locator(heading("Greek District")).wait_for()
    page.wait_for_timeout(400)
    assert scroll_offsets(page) == [0, 0]
    assert not page.errors


def test_a_run_that_never_reached_the_chapter_says_so(desktop):
    page = desktop
    page.locator('#chapterList [data-chapter="32.4"]').click()
    page.wait_for_function("state.chapter === '32.4'")
    page.locator("#storyContent .story-decision").first.wait_for()
    page.wait_for_timeout(400)
    read_at(page, "#storyContent .story-decision")
    assert scroll_offsets(page)[0] > 0
    follow_by_chip(page, WILDCARD)
    empty = page.locator("#storyContent .story-empty")
    assert "never got here" in empty.inner_text()
    assert scroll_offsets(page) == [0, 0]
    assert not page.errors


def test_phone_following_menu_keeps_the_decision_being_read(phone):
    page = phone
    read_at(page, decision("ch1_00063"), above=50)
    # A small scroll up brings back the toolbar with the Following menu.
    page.evaluate(
        "() => { const s = document.getElementById('storyScroll'); s.scrollTop -= 40; s.dispatchEvent(new Event('scroll')); }"
    )
    page.wait_for_timeout(350)
    before = reading(page)
    assert before["name"] == "ch1_00063"
    version = page.evaluate("storyVersion")
    page.locator("#storyRun").tap()
    menu = page.locator("#storyRunMenu")
    menu.wait_for(state="visible")
    menu.locator(f'[data-run-id="{WILDCARD}"]').tap()
    settle(page, WILDCARD, version)
    after = reading(page)
    assert after["name"] == "ch1_00063"
    assert abs(after["top"] - before["top"]) <= 2
    assert not page.errors
