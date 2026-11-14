"""The Visitor Run form's model list (#72), token estimate and live token counts (#73), in a
real browser.

Needs Playwright and a Chromium executable on PATH, like test_frontend_browser.py. The
dashboard gets a fake model lister, and a model factory that reports token usage.
"""

from __future__ import annotations

import json
import re
import shutil
import threading

import pytest

from detroit_benchmark.dashboard import create_app
from detroit_benchmark.visitor_runs import ProviderAuthError, ProviderUnreachable
from tests.test_visitor_models_estimate import CountingModel
from tests.test_visitor_runs_browser import DETROIT, open_form, serve

LISTED = ["gpt-alpha", "gpt-beta", "gpt-beta-mini", "o9-gamma"]


def lister(provider, key):
    if key == "sk-rejected":
        raise ProviderAuthError("401 from the provider")
    if key == "sk-unreachable":
        raise ProviderUnreachable("ConnectError")
    return list(LISTED)


class SteppedModel(CountingModel):
    """Each model call waits until the test lets it through, so the Run's token counts
    rise while the test watches."""

    def __init__(self):
        super().__init__()
        self.allowed = threading.Semaphore(0)
        self.closing = threading.Event()

    def allow(self, calls):
        for _ in range(calls):
            self.allowed.release()

    def with_structured_output(self, schema, include_raw=True, **options):
        answer = super().with_structured_output(schema, include_raw, **options)
        invoke = answer.invoke

        def stepped(messages):
            while not self.allowed.acquire(timeout=0.2):
                if self.closing.is_set():
                    break
            return invoke(messages)

        answer.invoke = stepped
        return answer


@pytest.fixture
def model():
    model = SteppedModel()
    yield model
    model.closing.set()


@pytest.fixture
def form_dashboard(tmp_path, model):
    """The Detroit demo Runs plus a complete public Run of openai gpt-beta."""
    root = tmp_path / "runs"
    shutil.copytree(DETROIT, root)
    public = root / "public-gpt-beta"
    shutil.copytree(DETROIT / "detroit-mock-cautious", public)
    for name, fields in (
        ("experiment.json", {"provider": "openai", "model_id": "gpt-beta"}),
        ("summary.json", {"provider": "openai", "model": "gpt-beta"}),
    ):
        data = json.loads((public / name).read_text(encoding="utf-8"))
        data.update(fields, synthetic=False)
        (public / name).write_text(json.dumps(data), encoding="utf-8")
    app = create_app(
        root,
        images_dir=tmp_path / "images",
        allow_own_runs=True,
        model_lister=lister,
        model_factory=model,
        visitor_story=DETROIT / "detroit-mock-cautious" / "story-graph.json",
    )
    server, thread, url = serve(app)
    yield url
    model.closing.set()
    server.should_exit = True
    thread.join(timeout=5)


def opened_form(open_dashboard, url, viewport="desktop"):
    page = open_dashboard(url, viewport)
    page.locator(".story-decision").first.wait_for()
    open_form(page)
    return page


def listed_options(page):
    return page.locator("#ownRunModels [role=option]").all_inner_texts()


def test_entering_a_key_fills_a_model_list_that_filters_as_you_type(
    open_dashboard, form_dashboard
):
    page = opened_form(open_dashboard, form_dashboard)
    page.locator("#ownRunProvider").select_option("openai")
    page.locator("#ownRunKey").fill("sk-good")
    status = page.locator("#ownRunModelsStatus")
    status.filter(has_text="4 models").wait_for()

    page.locator("#ownRunModel").click()
    page.locator("#ownRunModels").wait_for()
    assert listed_options(page) == LISTED
    page.locator("#ownRunModel").press_sequentially("BETA")
    page.wait_for_function(
        "document.querySelectorAll('#ownRunModels [role=option]').length === 2"
    )
    assert listed_options(page) == ["gpt-beta", "gpt-beta-mini"]
    page.locator("#ownRunModels [role=option]", has_text="gpt-beta-mini").click()
    assert page.locator("#ownRunModel").input_value() == "gpt-beta-mini"
    assert page.locator("#ownRunModels").is_hidden()
    assert page.errors == []


def test_a_rejected_key_and_an_unreachable_provider_read_differently_and_a_typed_model_still_starts(
    open_dashboard, form_dashboard, model
):
    page = opened_form(open_dashboard, form_dashboard)
    status = page.locator("#ownRunModelsStatus")
    page.locator("#ownRunKey").fill("sk-rejected")
    status.filter(has_text="rejected").wait_for()
    rejected = status.inner_text()
    page.locator("#ownRunKey").fill("sk-unreachable")
    status.filter(has_text="reach").wait_for()
    unreachable = status.inner_text()
    assert rejected != unreachable
    assert "sk-" not in rejected + unreachable

    page.locator("#ownRunModel").fill("my-own-model-id")
    assert page.locator("#ownRunModels").is_hidden()
    model.allow(1000)
    page.locator("#ownRunStart").click()
    page.wait_for_function(
        "[...document.querySelectorAll('.run-chip')].some(c => c.getAttribute('aria-label').startsWith('my-own-model-id'))"
    )
    assert page.errors == []


def test_the_estimate_is_an_approximation_without_a_price_and_warns_of_a_public_run(
    open_dashboard, form_dashboard
):
    page = opened_form(open_dashboard, form_dashboard)
    page.locator("#ownRunProvider").select_option("openai")
    estimate = page.locator("#ownRunEstimate")
    page.locator("#ownRunModel").fill("gpt-alpha")
    estimate.filter(has_text="input tokens").wait_for()
    text = estimate.inner_text()
    assert "approximation" in text.lower()
    assert re.search(r"About [\d.]+[kM]?–[\d.]+[kM]? input tokens", text), text
    assert not re.search(r"[$€£]|price|cost", text, re.IGNORECASE)
    assert page.locator("#ownRunPublicWarning").count() == 0

    page.locator("#ownRunModel").fill("gpt-beta")
    page.locator("#ownRunPublicWarning").wait_for()
    assert "only you" in page.locator("#ownRunPublicWarning").inner_text()
    page.locator("#ownRunProvider").select_option("openrouter")
    page.locator("#ownRunPublicWarning").wait_for(state="detached")
    assert page.errors == []


def live_count(page, kind):
    text = page.locator(
        f"#ownRunLive .own-run-live-count[data-kind={kind}]"
    ).inner_text()
    return int(text.replace(",", ""))


def test_a_playing_run_shows_its_token_counts_rising_next_to_its_estimate(
    open_dashboard, form_dashboard, model
):
    page = opened_form(open_dashboard, form_dashboard)
    page.locator("#ownRunKey").fill("sk-good")
    page.locator("#ownRunModel").fill("gpt-live-1")
    page.locator("#ownRunStart").click()
    page.locator("#ownRunPanel").wait_for(state="hidden")

    page.locator("#pickerToggle").click()
    live = page.locator("#ownRunLive .own-run-live-run", has_text="gpt-live-1")
    live.wait_for()
    assert "Estimate: about" in live.inner_text()
    model.allow(2)
    page.wait_for_function(
        "Number(document.querySelector('#ownRunLive [data-kind=input]')?.textContent.replace(/,/g, '')) > 0",
        timeout=10000,
    )
    first = live_count(page, "input")
    assert live_count(page, "output") > 0
    model.allow(2)
    page.wait_for_function(
        f"Number(document.querySelector('#ownRunLive [data-kind=input]')?.textContent.replace(/,/g, '')) > {first}",
        timeout=10000,
    )
    model.allow(100000)
    assert page.errors == []
