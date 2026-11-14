"""A Visitor Run's life over HTTP (#74, #75): Stop, partial Runs and the play limits.

Runs play with the engine's `mock` provider. A Gate holds a Run "playing" by blocking its
first model call until the test opens it.
"""

from __future__ import annotations

import json
import threading
import time

from fastapi.testclient import TestClient

from detroit_benchmark.dashboard import create_app
from detroit_benchmark.engine import create_model

KEY = "sk-sentinel-lifecycle-5d2e8b"


class Gate:
    """Every Visitor Run waits at its first model call until the gate opens."""

    def __init__(self):
        self.open = threading.Event()
        self.waiting = threading.Semaphore(0)

    def factory(self, provider, model_id, temperature=0, max_tokens=400, api_key=None):
        self.waiting.release()
        self.open.wait(timeout=30)
        if model_id == "broken-model":
            raise RuntimeError(f"Incorrect API key provided: {api_key}")
        return create_model("mock", model_id, temperature, max_tokens)


def visitor_client(tmp_path, gate, **options):
    app = create_app(
        tmp_path, allow_own_runs=True, model_factory=gate.factory, **options
    )
    return TestClient(app)


def start(client, model="gpt-test-1", ip=None, key=KEY):
    headers = {"CF-Connecting-IP": ip} if ip else {}
    return client.post(
        "/api/visitor-runs",
        json={"provider": "openai", "model": model, "key": key},
        headers=headers,
    )


def stop(client, run_id):
    return client.post(f"/api/visitor-runs/{run_id}/stop")


def listed(client, run_id):
    runs = client.get("/api/runs", params={"visitor_runs": [run_id]}).json()["runs"]
    return next(r for r in runs if r["id"] == run_id)


def wait_until_finished(client, run_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = listed(client, run_id)
        if run["status"] != "running":
            return run
        time.sleep(0.05)
    raise AssertionError("the Visitor Run did not finish")


def test_stop_ends_a_playing_run_after_the_current_model_call_and_keeps_it_partial(
    tmp_path,
):
    gate = Gate()
    client = visitor_client(tmp_path, gate)
    run_id = start(client).json()["id"]
    assert gate.waiting.acquire(timeout=10)
    assert listed(client, run_id)["status"] == "running"

    assert stop(client, run_id).status_code == 202
    gate.open.set()

    run = wait_until_finished(client, run_id)
    assert run["status"] == "partial"
    assert run["stop_reason"] == "Stopped by the visitor"
    # The model call under way when Stop was pressed is kept; the Run went no further.
    assert run["choices"] <= 1
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["run"]["status"] == "partial"
    assert detail["events"]


def test_only_a_playing_visitor_run_can_be_stopped(tmp_path):
    gate = Gate()
    gate.open.set()
    client = visitor_client(tmp_path, gate)
    assert stop(client, "not-a-run").status_code == 404
    run_id = start(client).json()["id"]
    assert wait_until_finished(client, run_id)["status"] == "complete"
    assert stop(client, run_id).status_code == 404
    assert listed(client, run_id)["status"] == "complete"


def test_a_run_that_fails_ends_partial_with_a_readable_reason_and_no_key(tmp_path):
    gate = Gate()
    gate.open.set()
    client = visitor_client(tmp_path, gate)
    run_id = start(client, model="broken-model").json()["id"]
    run = wait_until_finished(client, run_id)
    assert run["status"] == "partial"
    assert "Incorrect API key provided" in run["stop_reason"]
    assert KEY not in run["stop_reason"]


def test_on_start_up_a_visitor_run_left_in_progress_is_reported_partial(tmp_path):
    gate = Gate()
    client = visitor_client(tmp_path, gate)
    run_id = start(client).json()["id"]
    assert gate.waiting.acquire(timeout=10)
    assert listed(client, run_id)["status"] == "running"

    # A redeploy: a new dashboard process over the same folder; the old Run's key is gone.
    restarted = visitor_client(tmp_path, Gate())
    run = listed(restarted, run_id)
    assert run["status"] == "partial"
    assert "restart" in run["stop_reason"]
    gate.open.set()


def test_a_non_visitor_run_in_progress_is_left_alone_on_start_up(tmp_path):
    folder = tmp_path / "runs" / "live"
    folder.mkdir(parents=True)
    checkpoint = {"state": {"status": "running", "decisions": []}}
    (folder / "checkpoint.json").write_text(json.dumps(checkpoint))
    (folder / "events.jsonl").write_text("")
    visitor_client(tmp_path, Gate())
    assert json.loads((folder / "checkpoint.json").read_text()) == checkpoint


# Play limits (#75)


def test_a_third_concurrent_start_is_refused_as_busy(tmp_path):
    gate = Gate()
    client = visitor_client(tmp_path, gate)
    assert start(client, ip="198.51.100.1").status_code == 200
    assert start(client, ip="198.51.100.2").status_code == 200
    busy = start(client, ip="198.51.100.3")
    assert busy.status_code == 503
    assert "busy" in busy.json()["detail"].lower()
    assert "try again later" in busy.json()["detail"].lower()
    gate.open.set()


def test_a_second_start_from_the_same_visitor_is_refused_as_already_playing(tmp_path):
    gate = Gate()
    client = visitor_client(tmp_path, gate)
    assert start(client, ip="203.0.113.7").status_code == 200
    again = start(client, ip="203.0.113.7")
    assert again.status_code == 409
    assert "already" in again.json()["detail"].lower()
    assert "busy" not in again.json()["detail"].lower()
    assert start(client, ip="203.0.113.8").status_code == 200
    gate.open.set()


def test_without_the_cloudflare_header_the_socket_peer_identifies_the_visitor(
    tmp_path,
):
    gate = Gate()
    client = visitor_client(tmp_path, gate, max_playing=5)
    assert start(client).status_code == 200
    assert start(client).status_code == 409
    # The same socket peer behind Cloudflare is a different visitor per connecting IP.
    assert start(client, ip="192.0.2.10").status_code == 200
    gate.open.set()


def test_the_limits_are_constructor_parameters(tmp_path):
    gate = Gate()
    client = visitor_client(tmp_path, gate, max_playing=1, max_playing_per_visitor=2)
    assert start(client, ip="192.0.2.1").status_code == 200
    assert start(client, ip="192.0.2.2").status_code == 503
    gate.open.set()


def starts_soon(client, ip, timeout=5):
    """A slot frees just after its Run is listed as ended (the thread finishes)."""
    deadline = time.time() + timeout
    while True:
        response = start(client, ip=ip)
        if response.status_code == 200 or time.time() > deadline:
            return response.status_code
        time.sleep(0.05)


def _fill_both_slots(client, gate):
    first = start(client, ip="192.0.2.1").json()["id"]
    second = start(client, ip="192.0.2.2").json()["id"]
    assert gate.waiting.acquire(timeout=10) and gate.waiting.acquire(timeout=10)
    assert start(client, ip="192.0.2.3").status_code == 503
    assert start(client, ip="192.0.2.1").status_code == 409
    return first, second


def test_a_slot_frees_when_a_run_completes(tmp_path):
    gate = Gate()
    client = visitor_client(tmp_path, gate)
    first, second = _fill_both_slots(client, gate)
    gate.open.set()
    assert wait_until_finished(client, first)["status"] == "complete"
    assert wait_until_finished(client, second)["status"] == "complete"
    assert starts_soon(client, "192.0.2.3") == 200
    assert starts_soon(client, "192.0.2.1") == 200


def test_a_slot_frees_when_a_run_is_stopped(tmp_path):
    gate = Gate()
    client = visitor_client(tmp_path, gate)
    first, _ = _fill_both_slots(client, gate)
    stop(client, first)
    gate.open.set()
    assert wait_until_finished(client, first)["status"] == "partial"
    assert starts_soon(client, "192.0.2.1") == 200


def test_a_slot_frees_when_a_run_fails(tmp_path):
    gate = Gate()
    client = visitor_client(tmp_path, gate, max_playing=1)
    broken = start(client, model="broken-model", ip="192.0.2.1").json()["id"]
    assert start(client, ip="192.0.2.2").status_code == 503
    gate.open.set()
    assert wait_until_finished(client, broken)["status"] == "partial"
    assert starts_soon(client, "192.0.2.1") == 200


def test_a_start_that_cannot_begin_frees_its_slot(tmp_path):
    gate = Gate()
    gate.open.set()
    client = visitor_client(
        tmp_path, gate, max_playing=1, visitor_story=tmp_path / "missing.json"
    )
    assert start(client, ip="192.0.2.1").status_code == 500
    assert start(client, ip="192.0.2.1").status_code == 500  # not 409 or 503
