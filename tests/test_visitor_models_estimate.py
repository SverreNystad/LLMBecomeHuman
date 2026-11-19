"""The Visitor Run form's model list (#72) and token estimate (#73), over HTTP.

Real providers are never called: the dashboard gets an injected model lister, and the real
listers are exercised against httpx's MockTransport.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from detroit_benchmark.dashboard import create_app
from detroit_benchmark.visitor_estimate import (
    CALIBRATION_TOLERANCE,
    Route,
    token_range,
)
from detroit_benchmark.visitor_runs import (
    MAX_MODEL_PAGES,
    ProviderAuthError,
    ProviderUnreachable,
    RateLimit,
    TooManyRequests,
    list_models,
)

KEY = "sk-sentinel-models-5b8e1d2c"


def visitor_client(tmp_path, **options):
    options.setdefault("allow_own_runs", True)
    return TestClient(create_app(tmp_path, **options))


def models(client, provider="openai", key=KEY):
    return client.post(
        "/api/visitor-runs/models", json={"provider": provider, "key": key}
    )


# --- Listing models (#72) -------------------------------------------------------------


def test_with_the_flag_off_listing_and_estimating_are_absent(tmp_path):
    client = TestClient(create_app(tmp_path, model_lister=lambda p, k: ["m"]))
    assert models(client).status_code == 404
    estimate = client.get(
        "/api/visitor-runs/estimate", params={"provider": "openai", "model": "m"}
    )
    assert estimate.status_code == 404


def test_listing_returns_the_model_ids_the_provider_gives_for_the_key(tmp_path):
    asked = []

    def lister(provider, key):
        asked.append((provider, key))
        return ["mistral-small-latest", "mistral-large-latest"]

    response = models(visitor_client(tmp_path, model_lister=lister), "mistral")
    assert response.status_code == 200
    assert response.json() == {
        "models": ["mistral-small-latest", "mistral-large-latest"]
    }
    assert asked == [("mistral", KEY)]


def test_a_rejected_key_and_an_unreachable_provider_give_distinct_errors_without_the_key(
    tmp_path,
):
    def rejecting(provider, key):
        raise ProviderAuthError(f"401 Unauthorized: bad key {key}")

    def unreachable(provider, key):
        raise ProviderUnreachable(f"Connection refused while sending {key}")

    rejected = models(visitor_client(tmp_path, model_lister=rejecting))
    down = models(visitor_client(tmp_path, model_lister=unreachable))
    assert rejected.status_code != down.status_code
    assert rejected.json()["detail"] != down.json()["detail"]
    assert "key" in rejected.json()["detail"].lower()
    assert "reach" in down.json()["detail"].lower()
    for response in (rejected, down):
        assert response.status_code >= 400
        assert KEY not in response.text


def test_listing_refuses_an_unknown_provider_or_an_empty_key(tmp_path):
    client = visitor_client(tmp_path, model_lister=lambda p, k: ["m"])
    assert models(client, provider="nobody").status_code == 422
    assert models(client, key="  ").status_code == 422


# The shape of each provider's list-models reply, and the ids in it.
PROVIDER_REPLIES = {
    "openai": ("api.openai.com", {"data": [{"id": "gpt-b"}, {"id": "gpt-a"}]}),
    "xai": ("api.x.ai", {"data": [{"id": "grok-b"}, {"id": "grok-a"}]}),
    "deepseek": (
        "api.deepseek.com",
        {"data": [{"id": "deepseek-reasoner"}, {"id": "deepseek-chat"}]},
    ),
    "mistral": (
        "api.mistral.ai",
        {"data": [{"id": "mistral-small"}, {"id": "mistral-large"}]},
    ),
    "openrouter": (
        "openrouter.ai",
        {"data": [{"id": "vendor/model-b"}, {"id": "vendor/model-a"}]},
    ),
    "anthropic": (
        "api.anthropic.com",
        {"data": [{"id": "claude-b"}, {"id": "claude-a"}], "has_more": False},
    ),
    "google": (
        "generativelanguage.googleapis.com",
        {
            "models": [
                {
                    "name": "models/gemini-b",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/gemini-a",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {
                    "name": "models/text-embedding-x",
                    "supportedGenerationMethods": ["embedContent"],
                },
            ]
        },
    ),
}


EXPECTED_IDS = {
    "openai": ["gpt-a", "gpt-b"],
    "xai": ["grok-a", "grok-b"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "mistral": ["mistral-large", "mistral-small"],
    "openrouter": ["vendor/model-a", "vendor/model-b"],
    "anthropic": ["claude-a", "claude-b"],
    "google": ["gemini-a", "gemini-b"],
}


def sends_key(request: httpx.Request) -> bool:
    return any(KEY in value for value in request.headers.values())


@pytest.mark.parametrize("provider", sorted(PROVIDER_REPLIES))
def test_each_providers_real_lister_reads_its_list_models_endpoint(provider):
    host, body = PROVIDER_REPLIES[provider]
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path.endswith("/key"):  # OpenRouter's key check
            return httpx.Response(200, json={"data": {"label": "visitor"}})
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ids = list_models(provider, KEY, client=client)
    # Sorted, and for Google only the models that can chat.
    assert ids == EXPECTED_IDS[provider]
    assert seen and all(r.url.host == host for r in seen)
    assert all(sends_key(r) for r in seen)
    assert all(KEY not in str(r.url) for r in seen)


@pytest.mark.parametrize("provider", sorted(PROVIDER_REPLIES))
def test_each_real_lister_tells_a_rejected_key_from_an_unreachable_provider(provider):
    def rejecting(request):
        if provider == "google":  # Google answers a bad key with 400 API_KEY_INVALID.
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "API key not valid.",
                        "details": [{"reason": "API_KEY_INVALID"}],
                    }
                },
            )
        return httpx.Response(401, json={"error": {"message": f"bad key {KEY}"}})

    def down(request):
        raise httpx.ConnectError(f"Connection refused ({KEY})", request=request)

    def failing(request):
        return httpx.Response(503, text="upstream unavailable")

    for handler, error in (
        (rejecting, ProviderAuthError),
        (down, ProviderUnreachable),
        (failing, ProviderUnreachable),
    ):
        with (
            httpx.Client(transport=httpx.MockTransport(handler)) as client,
            pytest.raises(error) as raised,
        ):
            list_models(provider, KEY, client=client)
        assert KEY not in str(raised.value)


# --- Token estimate (#73) -------------------------------------------------------------


def estimate(client, provider="openai", model="gpt-new-1"):
    response = client.get(
        "/api/visitor-runs/estimate", params={"provider": provider, "model": model}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_the_estimate_gives_input_and_output_token_ranges_for_the_story(tmp_path):
    found = estimate(visitor_client(tmp_path))
    low_in, high_in = found["input_tokens"]["low"], found["input_tokens"]["high"]
    low_out, high_out = found["output_tokens"]["low"], found["output_tokens"]["high"]
    assert 0 < low_in <= high_in
    assert 0 < low_out <= high_out
    # Every call sends a long prompt and gets a short answer.
    assert low_in > 10 * low_out and high_in > 10 * high_out
    assert found["approximate"] is True
    assert "price" not in json.dumps(found).lower()
    assert "cost" not in json.dumps(found).lower()


def write_run(directory, provider, model, status="complete", synthetic=False):
    directory.mkdir(parents=True)
    (directory / "experiment.json").write_text(
        json.dumps({"provider": provider, "model_id": model, "synthetic": synthetic})
    )
    (directory / "events.jsonl").write_text("")
    if status == "complete":
        (directory / "summary.json").write_text(
            json.dumps({"status": "complete", "provider": provider, "model": model})
        )


def test_the_estimate_says_whether_a_public_run_of_the_exact_model_exists(tmp_path):
    write_run(tmp_path / "runs" / "public-run", "openai", "gpt-public-1")
    write_run(tmp_path / "runs" / "unfinished", "openai", "gpt-unfinished-1", "running")
    client = visitor_client(tmp_path)
    assert estimate(client, "openai", "gpt-public-1")["public_run_exists"] is True
    assert estimate(client, "openrouter", "gpt-public-1")["public_run_exists"] is False
    assert estimate(client, "openai", "gpt-public-1-2026")["public_run_exists"] is False
    assert estimate(client, "openai", "gpt-unfinished-1")["public_run_exists"] is False


PROJECT = Path(__file__).resolve().parents[1]


# What the maintainers' real Runs of the whole story sent their models, and what the
# providers counted for it: the prompt characters, decisions and memory updates are
# summed from each Run's recorded prompts, the tokens are from its summary.
CALIBRATION = json.loads(
    (PROJECT / "tests" / "fixtures" / "token_calibration.json").read_text(
        encoding="utf-8"
    )
)


def test_there_are_real_runs_to_calibrate_against():
    assert len(CALIBRATION) >= 5


@pytest.mark.parametrize("run", CALIBRATION, ids=lambda r: r["run"])
def test_each_real_runs_recorded_tokens_fall_within_the_range_for_its_own_prompts(run):
    """The calibration: the characters-per-token range and per-call output tokens the
    estimate uses cover what the providers really counted, within the tolerance."""
    route = Route(run["prompt_characters"], run["decisions"], run["memory_updates"])
    found = token_range(route, route)
    for kind in ("input_tokens", "output_tokens"):
        recorded = run[kind]
        low, high = found[kind]["low"], found[kind]["high"]
        assert low * (1 - CALIBRATION_TOLERANCE) <= recorded, (kind, recorded, low)
        assert recorded <= high * (1 + CALIBRATION_TOLERANCE), (kind, recorded, high)


class CountingModel:
    """A model factory whose model picks the first listed choice and reports usage at
    4 characters a token, as providers do."""

    def __init__(self, delay=0.0):
        self.delay = delay

    def __call__(self, provider, model_id, temperature=0, max_tokens=400, api_key=None):
        return self

    def with_structured_output(self, schema, include_raw=True, **_):
        def invoke(messages):
            time.sleep(self.delay)
            prompt = json.loads(messages[1].content)
            if "available_choices" in prompt:
                parsed = schema(
                    choice_id=prompt["available_choices"][0]["id"],
                    rationale="It seems least harmful.",
                )
            else:
                parsed = schema(memory="I remember this chapter.")
            chars = sum(len(m.content) for m in messages)
            raw = SimpleNamespace(
                usage_metadata={"input_tokens": chars // 4, "output_tokens": 100},
                response_metadata={},
                id=None,
            )
            return {"raw": raw, "parsed": parsed}

        return SimpleNamespace(invoke=invoke)


def listed(client, run_id):
    runs = client.get("/api/runs", params={"visitor_runs": [run_id]}).json()["runs"]
    return next(r for r in runs if r["id"] == run_id)


def test_a_run_of_the_story_uses_tokens_within_the_estimate_and_its_counts_rise_as_it_plays(
    tmp_path,
):
    client = visitor_client(tmp_path, model_factory=CountingModel())
    found = estimate(client)
    run_id = client.post(
        "/api/visitor-runs",
        json={"provider": "openai", "model": "gpt-counting-1", "key": KEY},
    ).json()["id"]

    seen = []
    deadline = time.time() + 120
    while time.time() < deadline:
        run = listed(client, run_id)
        if run["status"] != "running":
            break
        seen.append(run["total_input_tokens"])
        time.sleep(0.2)
    assert run["status"] == "complete"
    # Live counts: the listing showed them rising while it played.
    assert len(set(seen)) >= 3 and seen == sorted(seen)
    for kind in ("input_tokens", "output_tokens"):
        assert found[kind]["low"] <= run[f"total_{kind}"] <= found[kind]["high"], kind


def test_listing_is_limited_per_visitor_to_ten_a_minute(tmp_path):
    client = visitor_client(tmp_path, model_lister=lambda provider, key: ["m"])
    ip = {"CF-Connecting-IP": "203.0.113.20"}

    def send(headers):
        return client.post(
            "/api/visitor-runs/models",
            json={"provider": "openai", "key": KEY},
            headers=headers,
        )

    assert [send(ip).status_code for _ in range(10)] == [200] * 10
    refused = send(ip)
    assert refused.status_code == 429
    assert "Wait a minute" in refused.json()["detail"]
    # Another visitor is not held back.
    assert send({"CF-Connecting-IP": "203.0.113.21"}).status_code == 200


def test_the_rate_limit_forgets_requests_outside_its_window():
    now = [0.0]
    limit = RateLimit(2, window=60, clock=lambda: now[0])
    limit.check("a")
    limit.check("a")
    with pytest.raises(TooManyRequests):
        limit.check("a")
    now[0] = 61
    limit.check("a")


@pytest.mark.parametrize("provider", ["anthropic", "google"])
def test_a_paged_model_list_is_read_at_most_twenty_pages_deep(provider):
    pages = []

    def handler(request):
        pages.append(request)
        n = len(pages)
        if provider == "anthropic":
            body = {"data": [{"id": f"m{n}"}], "has_more": True, "last_id": f"m{n}"}
        else:
            body = {"models": [{"name": f"models/m{n}"}], "nextPageToken": f"t{n}"}
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        ids = list_models(provider, KEY, client=client)
    assert len(pages) == MAX_MODEL_PAGES == 20
    assert len(ids) == 20
