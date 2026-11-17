"""The dashboard after Clear (no Shown Runs left) keeps its chapters and Character theme (#66).

Needs Playwright and a Chromium executable on PATH, like test_frontend_browser.py.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def desktop(open_dashboard, detroit_dashboard):
    return _ready(open_dashboard(detroit_dashboard))


@pytest.fixture
def phone(open_dashboard, detroit_dashboard):
    return _ready(open_dashboard(detroit_dashboard, "phone"))


def _ready(page):
    page.locator(".story-decision").first.wait_for()
    return page


def clear(page):
    page.locator("#pickerToggle").click()
    page.locator("#clearRuns").click()
    page.keyboard.press("Escape")
    page.wait_for_function("document.querySelectorAll('.run-chip').length === 0")
    page.locator(".story-empty").wait_for()


def chapter_entries(page):
    return page.locator("#chapterList .chapter-entry").evaluate_all(
        """els => els.map(e => ({chapter: e.dataset.chapter, character: e.dataset.character,
             active: e.classList.contains('active'), faded: e.classList.contains('not-reached')}))"""
    )


def theme(page):
    return page.evaluate("document.body.dataset.character")


def test_clear_keeps_every_chapter_faded_with_the_current_one_highlighted(desktop):
    page = desktop
    before = chapter_entries(page)
    current = next(e for e in before if e["active"])
    title = page.locator("#chapterTitle").inner_text()
    assert current["character"] in ("connor", "kara", "markus")

    clear(page)
    after = chapter_entries(page)
    assert [e["chapter"] for e in after] == [e["chapter"] for e in before]
    assert all(e["faded"] for e in after)
    assert [e["chapter"] for e in after if e["active"]] == [current["chapter"]]
    # The theme is the current chapter's Character, not the default blue.
    assert theme(page) == current["character"]
    assert page.locator("#chapterTitle").inner_text() == title
    assert "Choose a model" in page.locator(".story-empty").inner_text()

    # The periodic refresh of the Run list leaves this state alone.
    page.evaluate("refreshRuns()")
    page.wait_for_timeout(300)
    assert chapter_entries(page) == after
    assert theme(page) == current["character"]
    assert not page.errors


def test_after_clear_a_chapter_click_re_themes_and_both_views_still_ask_for_a_model(
    desktop,
):
    page = desktop
    clear(page)
    entries = chapter_entries(page)
    current = next(e for e in entries if e["active"])
    other = next(
        e
        for e in entries
        if e["character"] != current["character"]
        and e["character"] in ("connor", "kara", "markus")
    )
    page.locator(f'#chapterList .chapter-entry[data-chapter="{other["chapter"]}"]').click()
    page.wait_for_function(
        f"document.querySelector('.chapter-entry.active')?.dataset.chapter === {other['chapter']!r}"
    )
    assert theme(page) == other["character"]
    assert all(e["faded"] for e in chapter_entries(page))
    assert "Choose a model" in page.locator(".story-empty").inner_text()
    page.locator("#viewFlow").click()
    page.locator("#graphEmpty").wait_for(state="visible")
    assert "Choose a model" in page.locator("#graphEmpty").inner_text()
    assert page.locator("#graphNodes .flow-node").count() == 0
    assert theme(page) == other["character"]
    assert not page.errors


def picker_is_open(page):
    return page.locator("#pickerPanel").is_visible() and (
        page.locator("#pickerToggle").get_attribute("aria-expanded") == "true"
    )


def test_choose_a_model_in_the_story_opens_the_picker(desktop):
    page = desktop
    clear(page)
    assert not picker_is_open(page)
    page.locator(".story-empty").get_by_role("button", name="Choose a model").click()
    page.wait_for_function(
        "document.querySelector('#pickerToggle').getAttribute('aria-expanded') === 'true'"
    )
    assert picker_is_open(page)
    assert not page.errors


def test_choose_a_model_in_the_flowchart_opens_the_picker(desktop):
    page = desktop
    clear(page)
    page.locator("#viewFlow").click()
    page.locator("#graphEmpty").wait_for(state="visible")
    page.wait_for_function(
        "document.querySelector('#viewerWrap').getAnimations().length === 0"
    )
    page.locator("#graphEmpty").get_by_role("button", name="Choose a model").click()
    page.wait_for_function(
        "document.querySelector('#pickerToggle').getAttribute('aria-expanded') === 'true'"
    )
    assert picker_is_open(page)
    assert not page.errors


def test_choosing_a_model_after_clear_restores_the_current_chapter(desktop):
    page = desktop
    clear(page)
    entries = chapter_entries(page)
    # A chapter other than the one the Runs open on, so a reset would show.
    target = entries[2]
    assert not target["active"]
    page.locator(
        f'#chapterList .chapter-entry[data-chapter="{target["chapter"]}"]'
    ).click()
    page.wait_for_function(
        f"document.querySelector('.chapter-entry.active')?.dataset.chapter === {target['chapter']!r}"
    )
    page.locator(".story-empty").get_by_role("button", name="Choose a model").click()
    page.locator("#pickerList input[data-run-id]").first.check()
    page.keyboard.press("Escape")
    page.wait_for_function("document.querySelectorAll('.run-chip').length === 1")
    page.wait_for_function(
        "!document.querySelector('.story-empty [data-choose-model]')"
    )
    assert [e["chapter"] for e in chapter_entries(page) if e["active"]] == [
        target["chapter"]
    ]
    assert theme(page) == target["character"]
    # Chapters the model reached are no longer faded.
    assert not all(e["faded"] for e in chapter_entries(page))
    page.locator("#viewFlow").click()
    page.locator("#graphNodes .flow-node").first.wait_for()
    assert page.locator("#graphEmpty").is_hidden()
    assert not page.errors


def test_phone_choose_a_model_opens_the_picker_in_the_phone_bar(phone):
    page = phone
    page.locator("#pickerToggle").tap()
    page.locator("#clearRuns").tap()
    page.wait_for_function("document.querySelectorAll('.run-chip').length === 0")
    page.keyboard.press("Escape")
    page.wait_for_function(
        "document.querySelector('#pickerPanel').classList.contains('is-hidden')"
    )
    entries = chapter_entries(page)
    assert entries and all(e["faded"] for e in entries)
    assert theme(page) == next(e for e in entries if e["active"])["character"]

    page.locator(".story-empty").get_by_role("button", name="Choose a model").tap()
    page.locator("#pickerPanel").wait_for(state="visible")
    assert page.locator("#phoneBar #pickerPanel").count() == 1
    assert picker_is_open(page)

    page.keyboard.press("Escape")
    page.wait_for_function(
        "document.querySelector('#pickerPanel').classList.contains('is-hidden')"
    )
    page.locator("#viewFlow").tap()
    page.locator("#graphEmpty").wait_for(state="visible")
    page.wait_for_function(
        "document.querySelector('#viewerWrap').getAnimations().length === 0"
    )
    page.locator("#graphEmpty").get_by_role("button", name="Choose a model").tap()
    page.locator("#pickerPanel").wait_for(state="visible")
    assert picker_is_open(page)
    assert not page.errors
