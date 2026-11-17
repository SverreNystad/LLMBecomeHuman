"""Phone keyboard (#79): on a touch phone nothing focuses a text field by itself, so the
keyboard only opens when the reader taps the field. Desktop keeps focusing Search.

Needs Playwright and a Chromium executable on PATH, like test_phone_browser.py.
"""

from __future__ import annotations


def search_focused(page):
    return page.evaluate("() => document.activeElement?.id === 'searchRuns'")


def test_phone_picker_opens_without_the_keyboard(open_dashboard, detroit_dashboard):
    page = open_dashboard(detroit_dashboard, "phone")
    page.locator(".story-decision").first.wait_for()
    page.locator("#pickerToggle").tap()
    page.locator("#searchRuns").wait_for(state="visible")
    page.wait_for_timeout(200)
    assert not search_focused(page)

    page.locator("#searchRuns").tap()
    assert search_focused(page)
    assert page.errors == []


def test_desktop_picker_focuses_search(open_dashboard, detroit_dashboard):
    page = open_dashboard(detroit_dashboard, "desktop")
    page.locator(".story-decision").first.wait_for()
    page.locator("#pickerToggle").click()
    page.locator("#searchRuns").wait_for(state="visible")
    assert search_focused(page)
    assert page.errors == []
