import json
import os
import shutil
import socket
import threading
import time
from pathlib import Path

import pytest
from detroit_benchmark.dashboard import create_app

from tests.dataset import load_dataset

PROJECT = Path(__file__).resolve().parents[1]
RUN_FIXTURES = PROJECT / "tests" / "fixtures" / "runs"
# The three Detroit mock Runs the tests read.
DETROIT_RUNS = RUN_FIXTURES / "detroit"
DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
VIEWPORTS = {"desktop": DESKTOP, "phone": PHONE}


@pytest.fixture(autouse=True)
def _visitor_runs_finish(tmp_path):
    """Waits for the Visitor Runs a test started before its tmp_path is removed (it
    depends on tmp_path, so it is torn down first): a Run left playing would write into
    a deleted folder, or into the next test's time."""
    before = set(threading.enumerate())
    yield
    for thread in set(threading.enumerate()) - before:
        if thread.name.startswith("visitor-run-"):
            thread.join(timeout=60)


@pytest.fixture
def dataset() -> dict:
    """A fresh copy of the real story dataset; tests may change it freely."""
    return load_dataset()


# Copies of the Detroit mock Runs under other model families: with the three originals
# (anthropic, openai, google) every family has a Run, and a seventh Run is one too many
# for the six the bar holds.
MORE_FAMILIES = [
    ("detroit-mock-cautious", "xai"),
    ("detroit-mock-defiant", "deepseek"),
    ("detroit-mock-wildcard", "mistral"),
    ("detroit-mock-defiant", "anthropic"),
]


def runs_of_every_family(root: Path) -> Path:
    """Seven Detroit mock Runs in `root`, at least one per model family. Files are
    symlinks to the fixtures (tmp_path may be another filesystem), except each copy's own
    experiment.json."""
    for source in sorted(DETROIT_RUNS.iterdir()):
        shutil.copytree(source, root / source.name, copy_function=os.symlink)
    for name, family in MORE_FAMILIES:
        copy = root / f"{name}-{family}"
        shutil.copytree(DETROIT_RUNS / name, copy, copy_function=os.symlink)
        experiment = copy / "experiment.json"
        settings = json.loads(experiment.read_text(encoding="utf-8"))
        experiment.unlink()
        settings["display_provider"] = family
        settings["model_id"] = settings["model_id"].replace("mock", f"{family} mock")
        experiment.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return root


def _serve(runs_dir: Path, images_dir: Path):
    """Serves the real dashboard over `runs_dir` on a free local port; yields its URL."""
    uvicorn = pytest.importorskip("uvicorn")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    app = create_app(runs_dir, images_dir=images_dir)
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


@pytest.fixture
def live_dashboard(tmp_path):
    """The real dashboard over seven Detroit mock Runs, every model family, so pages have
    an origin (browser storage) and assets load. The images folder is empty: no title or
    scene art."""
    images = tmp_path / "images"
    images.mkdir()
    runs = tmp_path / "runs"
    runs.mkdir()
    yield from _serve(runs_of_every_family(runs), images)


@pytest.fixture
def detroit_dashboard(tmp_path):
    """The real dashboard over the three Detroit mock Runs, with no art installed."""
    yield from _serve(DETROIT_RUNS, tmp_path)


@pytest.fixture
def browser():
    """Chromium through Playwright; skips the test when either is unavailable."""
    playwright = pytest.importorskip("playwright.sync_api")
    binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        pytest.skip("Chromium executable unavailable")
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(executable_path=binary, args=["--no-sandbox"])
        try:
            yield b
        finally:
            b.close()


@pytest.fixture
def new_page(browser):
    """Makes a fresh page: `new_page(viewport="desktop", *, touch=None, timeout=6000, **options)`.

    `viewport` is "desktop" (1440x900), "phone" (390x844) or a size dict. A touch page
    (the default for "phone") is a mobile, touch, 2x device. Other options go to the
    browser context. Uncaught page errors collect in `page.errors`.
    """

    def make(viewport="desktop", *, touch=None, timeout=6000, **options):
        if touch is None:
            touch = viewport == "phone"
        if touch:
            options = {
                "has_touch": True, "is_mobile": True, "device_scale_factor": 2, **options
            }
        size = VIEWPORTS[viewport] if isinstance(viewport, str) else viewport
        page = browser.new_context(viewport=size, **options).new_page()
        page.set_default_timeout(timeout)
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.touch = touch
        return page

    return make


def pass_title_screen(page):
    """Dismisses the title screen once it accepts input: a tap on touch pages, else a key."""
    page.locator("#titleScreen").wait_for()
    page.wait_for_timeout(400)
    if page.touch:
        size = page.viewport_size
        page.touchscreen.tap(size["width"] / 2, size["height"] / 2)
    else:
        page.keyboard.press("Enter")
    page.locator("#titleScreen").wait_for(state="detached")


@pytest.fixture
def open_dashboard(new_page):
    """Opens `url` on a new page past the title screen: `open_dashboard(url, viewport, **options)`
    with `new_page`'s arguments."""

    def open_(url, viewport="desktop", **options):
        page = new_page(viewport, **options)
        page.goto(url)
        pass_title_screen(page)
        return page

    return open_
