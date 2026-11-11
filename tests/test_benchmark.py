import json
from pathlib import Path
import pytest
from bs4 import BeautifulSoup

from detroit_benchmark.engine import Runner, validate_graph, evaluate_condition
from detroit_benchmark.ingest import (
    Compiler,
    render_expr,
    translation_map,
    discover_chapters,
)

DATA = Path(__file__).resolve().parents[1] / "examples" / "synthetic_game.json"


def graph():
    return json.loads(DATA.read_text())


def test_clean_graph_and_branches(tmp_path):
    g = graph()
    assert validate_graph(g, strict=True)["valid"]
    run = Runner(g, "mock", None, tmp_path / "run")
    result = run.run()
    assert result["status"] == "complete"
    assert result["final_flags"]["sensor_inspected"] is True
    assert result["chapters_visited"] == ["demo-1", "demo-2"]
    ev = [
        json.loads(line)
        for line in (tmp_path / "run" / "events.jsonl").read_text().splitlines()
    ]
    assert "no_code" not in [e["node_id"] for e in ev]
    decision = next(e for e in ev if e["type"] == "decision")
    assert "Guard" in json.dumps(decision["input"])
    assert decision["output"]["rationale"]


def test_segment_narrative_includes_earlier_choices_and_dialogue(tmp_path):
    g = graph()
    g["nodes"]["has_code"]["next"] = "second_choice"
    g["nodes"]["second_choice"] = {
        "id": "second_choice",
        "type": "choice",
        "chapter": "demo-2",
        "character": "Investigator",
        "heading": "Final choice",
        "description": "How to proceed?",
        "options": [
            {"id": "finish", "label": "Finish", "next": "end", "effects": {"flags": {}}}
        ],
    }
    Runner(g, "mock", None, tmp_path / "run").run()
    decisions = [e for e in read_events(tmp_path / "run") if e["type"] == "decision"]
    assert len(decisions) == 2
    # No chapter exit in this graph, so the whole run is one Chapter Segment.
    narrative = decisions[1]["input"]["narrative_since_chapter_start"]
    assert [e.get("heading") or e.get("your_choice") for e in narrative] == [
        "Arrival",
        "Inspect the sensor",
        "Investigation",
        "Control room",
        "Unlocked",
    ]
    assert narrative[0]["dialogue"] == [
        {
            "speaker": "Guard",
            "text": "The sensor may explain the alarm.",
            "source_keys": [],
        }
    ]
    assert narrative[1]["rationale"] == "Mock policy: first listed choice."


def test_decision_prompt_contains_only_the_allowed_context(tmp_path):
    Runner(three_segment_graph(), "mock", None, tmp_path / "run").run()
    decisions = [e for e in read_events(tmp_path / "run") if e["type"] == "decision"]
    for decision in decisions:
        assert list(decision["input"]) == [
            "current_scene",
            "character_memory",
            "narrative_since_chapter_start",
            "goal",
            "available_choices",
        ]
        assert set(decision["input"]["current_scene"]) == {
            "chapter",
            "character",
            "heading",
            "description",
        }
    # The segment restarts at each chapter exit.
    third = decisions[2]["input"]["narrative_since_chapter_start"]
    assert [e.get("heading") for e in third] == ["Interrogation"]


def test_resume(tmp_path):
    d = tmp_path / "run"
    first = Runner(graph(), "mock", None, d)
    first.step()
    second = Runner(graph(), "mock", None, d, resume=True)
    summary = second.run()
    assert summary["events_recorded"] == 7
    assert [
        json.loads(line)["index"]
        for line in (d / "events.jsonl").read_text().splitlines()
    ] == list(range(7))


def test_unknown_condition_fails_strict(tmp_path):
    g = graph()
    g["nodes"]["gate"]["branches"][0]["when"] = None
    with pytest.raises(ValueError):
        Runner(g, "mock", None, tmp_path / "strict")
    result = Runner(g, "mock", None, tmp_path / "approx", allow_unverified=True).run()
    assert result["warnings"]


def test_does_not_mix_alternative_dialogue():
    t = {"TEXT.FOO": "Actual English string", "CHOICE.FOO": "Investigate"}
    html = """<section><h1>Apartment</h1><app-choice-group>
      <app-choice-item [choiceLabel]="t('CHOICE.FOO')"><app-dialogue-line name="A">{{ t('TEXT.FOO') }}</app-dialogue-line></app-choice-item>
      <app-choice-item [choiceLabel]="t('CHOICE.FOO')"><app-dialogue-line name="B">{{ t('TEXT.FOO') }}</app-dialogue-line></app-choice-item>
      </app-choice-group></section>"""
    comp = Compiler(t, "1", "Connor")
    end = comp.add("ending", description="end")
    start = comp.compile_seq(BeautifulSoup(html, "html.parser").contents, end)
    begin = comp.nodes[start]
    node = comp.nodes[begin["next"]]
    assert node["type"] == "choice"
    assert len(node["options"]) == 2
    assert comp.nodes[node["options"][0]["next"]]["dialogue"][0]["speaker"] == "A"
    assert comp.nodes[node["options"][1]["next"]]["dialogue"][0]["speaker"] == "B"
    assert comp.nodes[node["options"][0]["next"]]["next"] == end


def test_translation_slices_and_nested_keys():
    t = translation_map(
        {"X": {"Y": {"Z": {"1": "Hello", "2": "world"}}}, "LIST": ["A", "B", "C"]}
    )
    text, keys = render_expr('translationService.translateObject("X.Y.Z", 0, 2)', t)
    assert text == "Hello world" and keys == ["X.Y.Z"]
    text, keys = render_expr('t("LIST")', t)
    assert text == "A B C"


def test_discover_repo_manifest(tmp_path):
    service = tmp_path / "src/app/shared/services"
    service.mkdir(parents=True)
    header = []
    data = []
    for i in range(1, 32):
        header.append(
            f"import {{ Test{i}ChapterContentComponent }} from '../../chapters/components/chapter-contents/{i}-demo/demo.component';"
        )
        data.append(
            f"new Chapter(i++, '{i}', Character.Connor, 'Chapter{i}.jpg', 'X', Test{i}ChapterContentComponent),"
        )
    (service / "chapter.service.ts").write_text("\n".join(header + data))
    result = discover_chapters(tmp_path)
    assert len(result) == 31
    assert result[0]["path"].endswith("/1-demo/demo.component.html")


def test_condition_evaluator():
    assert (
        evaluate_condition(
            {"all": [{"flag": "a"}, {"not": {"flag": "b"}}]}, {"a": True, "b": False}
        )
        is True
    )
    assert evaluate_condition({"flag": "missing"}, {}) is None


def test_full_chapter_routing_with_stub_transcripts(tmp_path):
    """40 source components -> playable 37-chapter path with 3 exclusive finales."""
    from detroit_benchmark.ingest import compile_from_repo

    repo = tmp_path / "upstream"
    (repo / "src/app/shared/services").mkdir(parents=True)
    (repo / "public/i18n").mkdir(parents=True)
    (repo / "public/i18n/en.json").write_text(
        json.dumps({"MESSAGE": "hello", "CHOICE": "Continue"})
    )
    nums = (
        [str(i) for i in range(1, 30)]
        + ["30.1", "30.2", "30.3", "31.1", "31.2"]
        + [f"32.{i}" for i in range(1, 7)]
    )
    imports = []
    rows = []
    for i, num in enumerate(nums):
        name = f"Demo{i}ChapterContentComponent"
        rel = f"{num}-demo/demo.component"
        imports.append(
            f"import {{ {name} }} from '../../chapters/components/chapter-contents/{rel}';"
        )
        rows.append(
            f"new Chapter(i++, '{num}', Character.Connor, 'image.jpg', 'C', {name}),"
        )
        html = (
            repo
            / "src/app/chapters/components/chapter-contents"
            / f"{num}-demo/demo.component.html"
        )
        html.parent.mkdir(parents=True)
        html.write_text(
            '<section><h1>Chapter</h1><app-dialogue-line name="Narrator">{{ t("MESSAGE") }}</app-dialogue-line><app-choice-group><app-choice-item [choiceLabel]="t(\'CHOICE\')"><p>First</p></app-choice-item><app-choice-item [choiceLabel]="t(\'CHOICE\')"><p>Second</p></app-choice-item></app-choice-group></section>'
        )
    (repo / "src/app/shared/services/chapter.service.ts").write_text(
        "\n".join(imports + rows)
    )
    compiled = compile_from_repo(repo)
    assert compiled["metadata"]["chapters_indexed"] == 40
    report = validate_graph(compiled)
    assert report["valid"], report["errors"][:10]
    assert report["choice_nodes"] == 40
    assert report["ending_nodes"] == 1
    # No conditional branches in fake source, but final route assumptions are flagged.
    output = Runner(
        compiled, "mock", None, tmp_path / "run", allow_unverified=True
    ).run()
    assert output["status"] == "complete"
    assert len(output["chapters_visited"]) == 37
    assert output["number_of_choices"] == 37
    assert output["warnings"]


def test_additional_providers_are_wired_without_external_calls(monkeypatch):
    import sys
    from types import SimpleNamespace
    from detroit_benchmark.engine import create_model

    captured = {}

    def FakeOpenAI(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setitem(
        sys.modules, "langchain_openai", SimpleNamespace(ChatOpenAI=FakeOpenAI)
    )
    monkeypatch.setenv("XAI_API_KEY", "test-only-key")
    result = create_model("xai", "grok-demo", 0)
    assert result["model"] == "grok-demo"
    assert result["base_url"] == "https://api.x.ai/v1"
    assert result["api_key"] == "test-only-key"
    assert create_model("mock", None) is None
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    import pytest

    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        create_model("deepseek", None)


def read_events(run_dir):
    return [
        json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()
    ]


def test_overlong_reply_is_retried_once_briefly_then_accepted(tmp_path):
    long_reply = json.dumps({"choice_id": "inspect", "rationale": "word " * 2000})
    short_reply = json.dumps({"choice_id": "storage", "rationale": "Brief."})
    run = Runner(
        graph(), "mock", None, tmp_path / "run", mock_replies=[long_reply, short_reply]
    )
    run.run()
    [decision] = [e for e in read_events(tmp_path / "run") if e["type"] == "decision"]
    assert decision["output"]["choice_id"] == "storage"
    assert decision["model_info"]["attempts"] == 2
    assert "answer briefly" in decision["model_info"]["retry_instruction"].lower()


def test_second_broken_reply_stops_the_run(tmp_path):
    long_reply = json.dumps({"choice_id": "inspect", "rationale": "word " * 2000})
    run = Runner(
        graph(),
        "mock",
        None,
        tmp_path / "run",
        mock_replies=[long_reply, "not json at all", "{}"],
    )
    with pytest.raises(RuntimeError, match="after one brief retry"):
        run.run()
    assert run.mock_replies == ["{}"]  # exactly two attempts consumed
    assert not [e for e in read_events(tmp_path / "run") if e["type"] == "decision"]


def three_segment_graph():
    """Connor (chapter 1), Kara (chapter 2), Connor again (chapter 3)."""

    def segment(n, character, heading, label):
        return {
            f"s{n}": {
                "id": f"s{n}",
                "type": "scene",
                "chapter": str(n),
                "character": character,
                "heading": heading,
                "description": f"{heading} description.",
                "dialogue": [{"speaker": "Someone", "text": f"Line in {heading}."}],
                "observations": [],
                "next": f"c{n}",
            },
            f"c{n}": {
                "id": f"c{n}",
                "type": "choice",
                "chapter": str(n),
                "character": character,
                "heading": f"{heading} choice",
                "description": "What now?",
                "options": [
                    {
                        "id": "a",
                        "label": label,
                        "next": f"t{n}",
                        "effects": {"flags": {}},
                    },
                    {
                        "id": "b",
                        "label": "Do nothing",
                        "next": f"t{n}",
                        "effects": {"flags": {}},
                    },
                ],
            },
            f"t{n}": {
                "id": f"t{n}",
                "type": "scene",
                "chapter": str(n),
                "character": character,
                "heading": f"{heading} aftermath",
                "description": "It is done.",
                "dialogue": [],
                "observations": [],
                "next": f"x{n}",
            },
            f"x{n}": {
                "id": f"x{n}",
                "type": "chapter_exit",
                "chapter": str(n),
                "character": character,
                "description": f"End of chapter {n}",
                "next": f"s{n + 1}" if n < 3 else "end",
            },
        }

    nodes = {
        **segment(1, "Connor", "Rooftop", "Save the girl"),
        **segment(2, "Kara", "Kitchen", "Protect Alice"),
        **segment(3, "Connor", "Interrogation", "Press the suspect"),
        "end": {"id": "end", "type": "ending", "chapter": "3", "description": "Done"},
    }
    return {
        "metadata": {"title": "Three segments", "fidelity": "verified_game_rules"},
        "start": "s1",
        "nodes": nodes,
    }


def test_connor_prompt_never_contains_karas_memory(tmp_path):
    Runner(three_segment_graph(), "mock", None, tmp_path / "run").run()
    events = read_events(tmp_path / "run")
    memories = {
        e["character"]: e["memory"] for e in events if e["type"] == "memory_update"
    }
    assert "Kitchen" in memories["Kara"]
    connor_later = [e for e in events if e["type"] == "decision"][2]
    assert connor_later["input"]["current_scene"]["character"] == "Connor"
    assert "Rooftop" in connor_later["input"]["character_memory"]
    assert "Kitchen" not in json.dumps(connor_later["input"])
    kara = [e for e in events if e["type"] == "decision"][1]
    assert kara["input"]["character_memory"] == ""


def test_memory_update_at_every_chapter_exit(tmp_path):
    Runner(three_segment_graph(), "mock", None, tmp_path / "run").run()
    events = read_events(tmp_path / "run")
    updates = [e for e in events if e["type"] == "memory_update"]
    assert [(u["character"], u["chapter"]) for u in updates] == [
        ("Connor", "1"),
        ("Kara", "2"),
        ("Connor", "3"),
    ]
    # Each update comes right before its chapter exit.
    kinds = [e["type"] for e in events]
    assert kinds.count("chapter_exit") == 3
    for update in updates:
        assert kinds[update["index"] + 1] == "chapter_exit"
    last = updates[2]
    assert last["input"]["instruction"] == (
        "This is the only thing you will remember of your time as Connor. "
        "Rewrite your memory to include this chapter in at most 6000 characters."
    )
    assert last["input"]["previous_memory"] == updates[0]["memory"]
    segment = last["input"]["chapter_segment"]
    assert segment[0]["dialogue"][0]["text"] == "Line in Interrogation."
    assert segment[1]["your_choice"] == "Press the suspect"
    assert segment[1]["rationale"] == "Mock policy: first listed choice."
    assert last["length"] == len(last["memory"]) and last["truncated"] is False


def test_over_limit_memory_gets_one_shorten_retry_then_truncation(tmp_path):
    choice = json.dumps({"choice_id": "a", "rationale": "Ok."})
    shortened = json.dumps({"memory": "Saved her."})
    still_long = json.dumps({"memory": "x" * 80})
    run = Runner(
        three_segment_graph(),
        "mock",
        None,
        tmp_path / "run",
        memory_max_chars=40,
        mock_replies=[
            choice,
            still_long,
            shortened,  # chapter 1: retry fixes it
            choice,
            still_long,
            still_long,  # chapter 2: still too long, truncated
        ],
    )
    run.run()
    first, second, _ = [
        e for e in read_events(tmp_path / "run") if e["type"] == "memory_update"
    ]
    assert first["memory"] == "Saved her." and first["truncated"] is False
    assert first["over_limit_length_before_retry"] == 80
    assert run.mock_replies == []  # exactly one shorten retry per update
    assert second["memory"] == "x" * 40
    assert second["length"] == 40 and second["truncated"] is True


def test_resume_keeps_character_memories(tmp_path):
    d = tmp_path / "run"
    first = Runner(three_segment_graph(), "mock", None, d)
    for _ in range(4):  # scene, choice, scene, Memory Update; then "crash"
        first.step()
    assert read_events(d)[-1]["type"] == "memory_update"
    resumed = Runner(three_segment_graph(), "mock", None, d, resume=True)
    resumed.run()
    events = read_events(d)
    connor_later = [e for e in events if e["type"] == "decision"][2]
    assert "Rooftop" in connor_later["input"]["character_memory"]
    assert [e["index"] for e in events] == list(range(len(events)))


def test_experiment_records_decision_token_and_reasoning_settings(tmp_path):
    Runner(graph(), "google", "gemini-2.5-flash", tmp_path / "run")
    experiment = json.loads((tmp_path / "run" / "experiment.json").read_text())
    limits = experiment["decision_limits"]
    assert limits["max_output_tokens"] == 400
    assert limits["rationale_max_sentences"] == 2
    assert limits["broken_reply_retries"] == 1
    assert limits["reasoning"] == {"thinking_budget": 0}


def fake_chat_module(monkeypatch, module, cls):
    import sys
    from types import SimpleNamespace

    captured = {}

    def Fake(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setitem(sys.modules, module, SimpleNamespace(**{cls: Fake}))
    return captured


@pytest.mark.parametrize(
    "provider,model,module,cls,token_key,reasoning",
    [
        ("openai", "gpt-4.1-mini", "langchain_openai", "ChatOpenAI", "max_tokens", {}),
        (
            "openai",
            "o4-mini",
            "langchain_openai",
            "ChatOpenAI",
            "max_tokens",
            {"reasoning_effort": "low"},
        ),
        (
            "openai",
            "gpt-5-mini",
            "langchain_openai",
            "ChatOpenAI",
            "max_tokens",
            {"reasoning_effort": "minimal"},
        ),
        (
            "anthropic",
            "claude-sonnet-4-5",
            "langchain_anthropic",
            "ChatAnthropic",
            "max_tokens",
            {},
        ),
        (
            "anthropic",
            "claude-sonnet-5",
            "langchain_anthropic",
            "ChatAnthropic",
            "max_tokens",
            {"thinking": {"type": "disabled"}},
        ),
        (
            "google",
            "gemini-2.5-flash",
            "langchain_google_genai",
            "ChatGoogleGenerativeAI",
            "max_output_tokens",
            {"thinking_budget": 0},
        ),
        (
            "google",
            "gemini-3-pro-preview",
            "langchain_google_genai",
            "ChatGoogleGenerativeAI",
            "max_output_tokens",
            {"thinking_level": "low"},
        ),
        (
            "deepseek",
            "deepseek-chat",
            "langchain_openai",
            "ChatOpenAI",
            "max_tokens",
            {},
        ),
        (
            "openrouter",
            "x/y",
            "langchain_openai",
            "ChatOpenAI",
            "max_tokens",
            {"extra_body": {"reasoning": {"effort": "low"}}},
        ),
    ],
)
def test_providers_get_decision_token_limit_and_lowest_reasoning(
    monkeypatch, provider, model, module, cls, token_key, reasoning
):
    from detroit_benchmark.engine import create_model

    captured = fake_chat_module(monkeypatch, module, cls)
    for env in ("GOOGLE_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.setenv(env, "test-only-key")
    create_model(provider, model, 0)
    assert captured[token_key] == 400
    for key, value in reasoning.items():
        assert captured[key] == value
    for key in ("reasoning_effort", "thinking", "thinking_budget", "thinking_level"):
        if key not in reasoning:
            assert key not in captured


def test_chapter_briefing_is_in_the_decision_prompt(tmp_path):
    g = three_segment_graph()
    g["chapter_briefings"] = {"1": "A rooftop at night. A child is in danger."}
    Runner(g, "mock", None, tmp_path / "run").run()
    decisions = [e for e in read_events(tmp_path / "run") if e["type"] == "decision"]
    assert decisions[0]["input"]["chapter_briefing"].startswith("A rooftop")
    assert "chapter_briefing" not in decisions[1]["input"]


def test_public_news_from_one_character_reaches_the_others(tmp_path):
    g = three_segment_graph()
    g["nodes"]["c2"]["options"][0]["effects"] = {
        "flags": {"kara_protected_alice": True},
        "news": [
            {
                "headline": "Android flees with child",
                "source": "https://detroit-become-human.fandom.com/wiki/Stormy_Night",
            }
        ],
    }
    Runner(g, "mock", None, tmp_path / "run").run()
    decisions = [e for e in read_events(tmp_path / "run") if e["type"] == "decision"]
    assert "news" not in decisions[0]["input"]
    assert decisions[2]["input"]["news"] == ["Android flees with child"]
    # Raw flags never leak into the prompt.
    assert "kara_protected_alice" not in json.dumps(decisions[2]["input"])
