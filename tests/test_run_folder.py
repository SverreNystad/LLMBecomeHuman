"""A Run's folder: how a Run is saved, resumed, stopped and read back."""

import json

import pytest

from detroit_benchmark.engine import Runner
from detroit_benchmark.run_folder import RunFolder, find_runs
from tests.test_benchmark import three_segment_graph


def _played(tmp_path, steps=None):
    """A mock Run of the three-segment story, played to its end or for ``steps``."""
    runner = Runner(three_segment_graph(), "mock", None, tmp_path / "run")
    if steps is None:
        runner.run()
    else:
        for _ in range(steps):
            runner.step()
    return runner


def test_a_finished_run_reads_back_from_its_summary(tmp_path):
    runner = _played(tmp_path)
    meta = RunFolder(tmp_path / "run").metadata()
    assert meta["status"] == "complete"
    assert meta["provider"] == "mock"
    assert meta["choices"] == len(runner.state["decisions"])
    assert RunFolder(tmp_path / "run").is_complete()


def test_a_playing_run_reads_back_from_its_latest_checkpoint(tmp_path):
    runner = _played(tmp_path, steps=3)
    folder = RunFolder(tmp_path / "run")
    assert folder.metadata()["status"] == "running"
    assert folder.metadata()["chapters_visited"] == runner.state["chapters_visited"]
    assert not folder.is_complete()
    assert [e["index"] for e in folder.events()] == [0, 1, 2]


def test_a_run_cut_off_by_a_restart_is_kept_as_partial_with_why(tmp_path):
    _played(tmp_path, steps=2)
    folder = RunFolder(tmp_path / "run")
    folder.stop("Cut off")
    meta = RunFolder(tmp_path / "run").metadata()
    assert (meta["status"], meta["stop_reason"]) == ("partial", "Cut off")


def test_stopping_a_run_that_ended_changes_nothing(tmp_path):
    _played(tmp_path)
    before = (tmp_path / "run" / "checkpoint.json").read_text()
    RunFolder(tmp_path / "run").stop("Cut off")
    assert (tmp_path / "run" / "checkpoint.json").read_text() == before


def test_a_checkpoint_from_before_character_memory_resumes_with_empty_memories(
    tmp_path,
):
    _played(tmp_path, steps=2)
    path = tmp_path / "run" / "checkpoint.json"
    saved = json.loads(path.read_text())
    for part in (
        "character_memories",
        "segment_events",
        "news",
        "pending_moments",
        "seen",
    ):
        del saved["state"][part]
    path.write_text(json.dumps(saved))
    runner = Runner(three_segment_graph(), "mock", None, tmp_path / "run", resume=True)
    assert runner.state["character_memories"] == {
        "Connor": "",
        "Kara": "",
        "Markus": "",
    }
    assert runner.state["news"] == [] and runner.state["seen"] == []
    runner.run()
    assert RunFolder(tmp_path / "run").is_complete()


def test_a_run_resumes_only_with_the_model_it_was_played_with(tmp_path):
    _played(tmp_path, steps=2)
    with pytest.raises(ValueError, match="different graph, provider, or model"):
        Runner(three_segment_graph(), "mock", "other", tmp_path / "run", resume=True)


def test_runs_are_found_under_a_root_in_path_order(tmp_path):
    for name in ("b", "a"):
        Runner(three_segment_graph(), "mock", None, tmp_path / "runs" / name).run()
    (tmp_path / "runs" / "notes").mkdir()
    found = find_runs((tmp_path / "runs").resolve())
    assert [folder.path.name for folder in found] == ["a", "b"]
