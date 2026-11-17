"""The compact model bar (logos only, at laptop widths): a hovered logo grows into its full
chip in the row, and a click swaps which chip is grown, both animated.

Runs against the real dashboard in Chromium; skipped when Playwright or Chromium is missing.
"""

from __future__ import annotations

LAPTOP = {"width": 1280, "height": 800}


def _compact_bar(page):
    """Show six Runs, so the bar collapses to logos at a laptop width."""
    page.locator("#pickerToggle").click()
    page.locator("#clearRuns").click()
    page.locator("#bestOfEach").click()
    page.wait_for_function("document.querySelectorAll('.run-chip').length === 6")
    page.keyboard.press("Escape")
    page.locator(".story-decision").first.wait_for()
    page.wait_for_function("document.querySelector('#selectedRunChips').classList.contains('is-compact')")
    page.wait_for_timeout(400)


def _widths(page):
    return page.evaluate(
        "[...document.querySelectorAll('.run-chip')].map(c => c.getBoundingClientRect().width)"
    )


def _lefts(page):
    return page.evaluate(
        "[...document.querySelectorAll('.run-chip')].map(c => c.getBoundingClientRect().left)"
    )


def _followed_index(page):
    return page.evaluate(
        "[...document.querySelectorAll('.run-chip')].findIndex(c => c.classList.contains('is-followed'))"
    )


def _collapsed_index(page, *, not_last=True):
    """A collapsed logo with a neighbour on its right."""
    followed = _followed_index(page)
    count = page.locator(".run-chip").count()
    return next(i for i in range(count - (1 if not_last else 0)) if i != followed)


def _move_off_bar(page):
    page.mouse.move(5, 795)


def test_hovering_a_logo_grows_it_into_its_chip_and_pushes_its_neighbour(
    live_dashboard, open_dashboard
):
    page = open_dashboard(live_dashboard, LAPTOP, timeout=4500)
    _compact_bar(page)
    i = _collapsed_index(page)
    before_w, before_l = _widths(page), _lefts(page)
    logo = page.locator(".run-chip").nth(i)

    logo.hover()
    page.wait_for_timeout(450)
    after_w, after_l = _widths(page), _lefts(page)
    assert after_w[i] > before_w[i] + 40, (before_w, after_w)
    # Its name is readable inside the chip, and the right neighbour moved over.
    label = logo.locator(".run-chip-label")
    model = page.evaluate(f"activeRuns()[{i}].model")
    assert model.startswith(label.inner_text().rstrip("…")[:6])
    assert after_l[i + 1] > before_l[i + 1] + 40
    # The Followed Run's chip stays grown meanwhile.
    followed = _followed_index(page)
    assert abs(after_w[followed] - before_w[followed]) < 1
    # No separate name popup.
    assert page.locator(".model-bar-name").count() == 0
    # The dashboard's periodic refresh leaves the hovered chip grown.
    page.evaluate("updateSelectors()")
    page.wait_for_timeout(100)
    assert abs(_widths(page)[i] - after_w[i]) < 1

    # Leaving the bar collapses it back.
    _move_off_bar(page)
    page.wait_for_timeout(450)
    assert abs(_widths(page)[i] - before_w[i]) < 1
    assert not page.errors


def _arrows(page):
    return page.evaluate(
        """() => ['-1', '1'].map(d => !document.querySelector(`.model-bar-arrow[data-scroll="${d}"]`).classList.contains('is-hidden'))"""
    )


def _fit_bar_snugly(page):
    """Leave the bar just room for its logos and the followed chip, so any growth overflows."""
    need = page.evaluate(
        """() => { const chips = [...document.querySelectorAll('.run-chip')];
        return chips.at(-1).getBoundingClientRect().right - chips[0].getBoundingClientRect().left + 12; }"""
    )
    page.add_style_tag(content=f".model-bar {{ flex: 0 0 {need}px; max-width: {need}px; }}")
    page.wait_for_timeout(300)
    assert _arrows(page) == [False, False]


def test_a_logo_grown_by_hover_or_focus_shows_the_arrows_without_scrolling(
    live_dashboard, open_dashboard
):
    page = open_dashboard(live_dashboard, LAPTOP, timeout=4500)
    _compact_bar(page)
    _fit_bar_snugly(page)
    i = _collapsed_index(page)
    page.locator(".run-chip").nth(i).hover()
    page.wait_for_timeout(450)
    assert _arrows(page) == [False, True]
    assert page.evaluate("document.querySelector('#selectedRunChips').scrollLeft") == 0

    _move_off_bar(page)
    page.wait_for_timeout(450)
    assert _arrows(page) == [False, False]

    # Keyboard focus grows a logo the same way.
    before = _widths(page)[i]
    page.locator(".run-chip").nth(i).focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    page.wait_for_timeout(450)
    assert _widths(page)[i] > before + 40
    assert not page.errors


# Clicks chip i, then records every chip's width on each frame for half a second.
CLICK_AND_SAMPLE = """async i => {
  const widths = () => [...document.querySelectorAll('.run-chip')].map(c => c.getBoundingClientRect().width);
  document.querySelectorAll('.run-chip')[i].click();
  const frames = [], start = performance.now();
  while (performance.now() - start < 500) {
    await new Promise(r => requestAnimationFrame(r));
    frames.push(widths());
  }
  return frames;
}"""


def test_clicking_a_logo_grows_it_while_the_old_selection_shrinks(
    live_dashboard, open_dashboard
):
    page = open_dashboard(live_dashboard, LAPTOP, timeout=4500)
    _compact_bar(page)
    old = _followed_index(page)
    new = _collapsed_index(page, not_last=False)
    before = _widths(page)

    frames = page.evaluate(CLICK_AND_SAMPLE, new)
    assert page.evaluate("storyRun().id") == page.locator(".run-chip").nth(new).get_attribute("data-focus-id")
    # Both chips are part-way at the same moment: one motion, not a snap.
    small, large = before[new], before[old]
    assert any(
        small + 5 < f[new] < large - 5 and small + 5 < f[old] < large - 5 for f in frames
    ), (before, frames)

    page.wait_for_timeout(450)
    after = _widths(page)
    assert abs(after[new] - before[old]) < 1 and abs(after[old] - before[new]) < 1
    assert not page.errors


def test_a_newly_selected_chip_ends_fully_in_view(live_dashboard, open_dashboard):
    page = open_dashboard(live_dashboard, LAPTOP, timeout=4500)
    _compact_bar(page)
    page.add_style_tag(content=".model-bar { flex: 0 0 300px; max-width: 300px; }")
    page.wait_for_timeout(300)
    # Scroll to the end, where the last logo sits at the right edge, then pick it.
    page.evaluate("(c => c.scrollLeft = c.scrollWidth)(document.querySelector('#selectedRunChips'))")
    page.wait_for_timeout(100)
    last = page.locator(".run-chip").last
    last.click()
    page.wait_for_timeout(900)
    assert "is-followed" in last.get_attribute("class")
    chip, bar = last.bounding_box(), page.locator("#selectedRunChips").bounding_box()
    assert chip["x"] >= bar["x"] - 0.5 and chip["x"] + chip["width"] <= bar["x"] + bar["width"] + 0.5
    assert chip["width"] > 150

    # Back to the first logo: the bar glides back to show it whole.
    first = page.locator(".run-chip").first
    page.evaluate("document.querySelector('#selectedRunChips').scrollLeft = 70")
    page.wait_for_timeout(100)
    first.dispatch_event("click")
    page.wait_for_timeout(900)
    chip = first.bounding_box()
    assert chip["x"] >= bar["x"] - 0.5 and chip["x"] + chip["width"] <= bar["x"] + bar["width"] + 0.5
    assert not page.errors


def test_reduced_motion_changes_sizes_without_transition(live_dashboard, open_dashboard):
    page = open_dashboard(live_dashboard, LAPTOP, timeout=4500, reduced_motion="reduce")
    _compact_bar(page)
    old = _followed_index(page)
    new = _collapsed_index(page)
    before = _widths(page)
    frames = page.evaluate(CLICK_AND_SAMPLE, new)
    assert all(
        abs(f[new] - before[old]) < 1 and abs(f[old] - before[new]) < 1 for f in frames
    ), frames
    # No glitch burst on hover either.
    logo = page.locator(".run-chip").nth(old)
    logo.hover()
    assert logo.evaluate("el => getComputedStyle(el).animationName") == "none"
    assert not page.errors
