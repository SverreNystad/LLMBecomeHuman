"""The title screen is always dark, with or without title art (issue #62).

Runs the real dashboard in Chromium through Playwright; skipped when either is unavailable.
"""

from __future__ import annotations

import shutil
import socket
import threading
import time
from pathlib import Path

import pytest
from detroit_benchmark.dashboard import create_app

PROJECT = Path(__file__).resolve().parents[1]

# Relative luminance (0..1) of a computed CSS colour painted over black, read in the page.
LUMINANCE_JS = """el => {
  const probe = document.createElement('canvas').getContext('2d');
  const lum = css => {
    probe.clearRect(0, 0, 1, 1); probe.fillStyle = '#000'; probe.fillRect(0, 0, 1, 1);
    probe.fillStyle = css; probe.fillRect(0, 0, 1, 1);
    const [r, g, b] = probe.getImageData(0, 0, 1, 1).data;
    const lin = c => { c /= 255; return c <= .03928 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4; };
    return .2126 * lin(r) + .7152 * lin(g) + .0722 * lin(b);
  };
  return lum;
}"""


@pytest.fixture
def live_dashboard(tmp_path):
    """The real dashboard on a local port, with an empty images folder (no title art)."""
    uvicorn = pytest.importorskip("uvicorn")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(PROJECT / "demo_runs" / "aurora", images_dir=tmp_path)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)


def _launch_chromium(p):
    binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        pytest.skip("Chromium executable unavailable")
    return p.chromium.launch(executable_path=binary, args=["--no-sandbox"])


def _luminance(page, css_color: str) -> float:
    return page.evaluate(f"css => ({LUMINANCE_JS})()(css)", css_color)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_title_screen_without_art_is_dark_over_a_light_dashboard(live_dashboard, scheme):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = _launch_chromium(p)
        try:
            page = browser.new_page(
                viewport={"width": 1440, "height": 900}, color_scheme=scheme
            )
            page.set_default_timeout(4500)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(live_dashboard)
            title = page.locator("#titleScreen")
            title.wait_for()
            page.wait_for_load_state("networkidle")
            # No art is installed, so the art never loads.
            assert "has-art" not in (title.get_attribute("class") or "")

            styles = page.evaluate("""() => {
              const s = document.getElementById('titleScreen');
              const cs = el => getComputedStyle(el);
              return {
                background: cs(s).backgroundColor,
                llm: cs(s.querySelector('.title-llm')).color,
                become: cs(s.querySelector('.title-become')).color,
                prompt: cs(s.querySelector('.title-prompt')).color,
                veil: cs(s.querySelector('.title-veil')).backgroundImage,
              };
            }""")
            # A dark background with light lettering (soft lettering is translucent,
            # so it is measured over the dark ground, as a contrast ratio).
            ground = _luminance(page, styles["background"])
            assert ground < 0.02
            for part in ("llm", "become", "prompt"):
                ratio = (_luminance(page, styles[part]) + 0.05) / (ground + 0.05)
                assert ratio > 4.5, (part, styles[part])
            # The blue glow behind the LED ring.
            assert "radial-gradient" in styles["veil"]
            glow = page.evaluate("""() => {
              const veil = document.querySelector('#titleScreen .title-veil');
              const m = getComputedStyle(veil).backgroundImage.match(/rgba?\\([^)]*\\)|color\\([^)]*\\)/);
              return m && m[0];
            }""")
            assert glow, styles["veil"]
            rgb = page.evaluate(
                """css => { const c = document.createElement('canvas').getContext('2d');
                  c.fillStyle = css; c.fillRect(0, 0, 1, 1);
                  return Array.from(c.getImageData(0, 0, 1, 1).data).slice(0, 3); }""",
                glow,
            )
            assert rgb[2] > rgb[0], f"glow is not blue: {glow}"

            # The dashboard behind stays in its light theme.
            body_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
            assert _luminance(page, body_bg) > 0.7
            page.wait_for_timeout(400)
            page.keyboard.press("Enter")
            title.wait_for(state="detached")
            body_bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
            assert _luminance(page, body_bg) > 0.7
            assert not errors
        finally:
            browser.close()
