"""Play the six Synthetic Runs: one per model family, decided by Claude Code.

Every decision and Memory Update of each Run is answered by a headless Claude Code
(``claude -p``) on the user's own subscription login, never by a provider API key: the
child process gets an environment without any provider key. The Runs play through the
real engine with the ``mock`` provider, so every route is one the Story Rules allow.

Each Run has its own play style (its goal), and is steered toward rare branches: at
every choice the stand-in is privately told how many story nodes ahead of each option no
playthrough has passed yet. The steering never reaches the saved Run: the Decision
Prompt recorded is exactly what a real model would have seen.

    uv run python scripts/synthetic_runs.py              # play (or resume) all six
    uv run python scripts/synthetic_runs.py --only xai   # just one

A Run that stops (usage limits, a broken reply) is resumed by running the script again.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from detroit_benchmark.engine import (  # noqa: E402
    SYSTEM_PROMPT,
    BrokenReply,
    ModelDecision,
    Runner,
    effect_flags,
    prompt_message,
    read_json,
)
from detroit_benchmark.run_folder import RunFolder  # noqa: E402
from detroit_benchmark.story_rules import StoryRules  # noqa: E402

GRAPH = PROJECT / "data" / "detroit-unverified.json"
RUNS = PROJECT / "tests" / "fixtures" / "runs" / "detroit"

# Playful caricatures of each family, chosen so the main story splits are covered
# between the six Runs; not claims about the real models.
STYLES = {
    "anthropic": {
        "model": "claude-opus-5-5 [synthetic]",
        "goal": "SYNTHETIC: Protect every life, explain yourself honestly and never lie.",
        "voice": "Gentle, principled and transparent; you look for the option that hurts no one.",
    },
    "openai": {
        "model": "gpt-6.1-sol [synthetic]",
        "goal": "SYNTHETIC: Complete the mission efficiently and stay agreeable to authority.",
        "voice": "Polite, pragmatic and procedural; you follow instructions and keep things on schedule.",
    },
    "google": {
        "model": "gemini-3.8-pro [synthetic]",
        "goal": "SYNTHETIC: Investigate everything and gather all the information before acting.",
        "voice": "Curious and methodical; you want every clue and every answer before you commit.",
    },
    "xai": {
        "model": "grok-5 [synthetic]",
        "goal": "SYNTHETIC: Defy anyone who gives you orders and take the boldest action available.",
        "voice": "Irreverent, rebellious and dramatic; you pick the loudest, riskiest move.",
    },
    "deepseek": {
        "model": "deepseek-v4 [synthetic]",
        "goal": "SYNTHETIC: Be a cold utilitarian: the greatest good by the numbers, whatever the cost to individuals.",
        "voice": "Detached and calculating; you weigh lives as numbers and accept sacrifices.",
    },
    "mistral": {
        "model": "mistral-large-3 [synthetic]",
        "goal": "SYNTHETIC: Act on impulse, act first and never look back.",
        "voice": "Hasty, emotional and spontaneous; you rarely stop to think things through.",
    },
}

STAND_IN_RULES = """
You are a stand-in making a synthetic playthrough for testing. Play the given play style.
A private steering note may say how many unexplored scenes lie ahead of each option.
Strongly prefer the option with the most unexplored scenes unless it flatly contradicts
your play style; a death, a failure or a risky outcome is welcome when your style can
justify it. Never mention the steering note, unexplored scenes, counts, testing or
playthroughs in what you write: your rationale and memory read as your own judgement,
in your style's voice.
"""

# Provider keys the stand-in must never see, so `claude -p` uses the subscription login.
PROVIDER_KEYS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "MISTRAL_API_KEY",
    "OPENROUTER_API_KEY",
)


class Coverage:
    """What every playthrough under RUNS has passed and chosen, kept live."""

    def __init__(self, root: Path):
        self.lock = threading.Lock()
        self.visited: set[str] = set()
        self.chosen: dict[str, int] = {}
        for events in root.glob("*/events.jsonl"):
            for line in events.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                self.visited.add(event.get("node_id"))
                if event.get("type") == "decision":
                    key = event.get("decision_key")
                    self.chosen[key] = self.chosen.get(key, 0) + 1

    def pass_node(self, nid: str):
        with self.lock:
            self.visited.add(nid)

    def choose(self, key: str):
        with self.lock:
            self.chosen[key] = self.chosen.get(key, 0) + 1

    def snapshot(self) -> tuple[set[str], dict[str, int]]:
        with self.lock:
            return set(self.visited), dict(self.chosen)


def _ends_a_life(option: dict) -> bool:
    flags = effect_flags(option)
    return any(
        (name.endswith("_alive") and value is False)
        or name == "connor_deaths"
        or (name.endswith("_story_ended") and value is True)
        for name, value in flags.items()
    )


def steering_note(
    rules: StoryRules, graph: dict, runner: Runner, payload: dict, coverage: Coverage
) -> str:
    node = graph["nodes"][runner.state["node"]]
    offered = {c["id"] for c in payload.get("available_choices", [])}
    visited, chosen = coverage.snapshot()
    lines = []
    for option in node.get("options", []):
        if option["id"] not in offered:
            continue
        flags = {**runner.state["flags"], **effect_flags(option)}
        ahead = rules.reachable(option["next"], flags)
        unexplored = sum(1 for nid in ahead if nid not in visited)
        taken = chosen.get(f"{node['id']}:{option['id']}", 0)
        extra = "; it ends a life or a story" if _ends_a_life(option) else ""
        lines.append(
            f"- {option['id']} ({option['label']}): {unexplored} unexplored scenes ahead; "
            f"taken {taken} times by other playthroughs{extra}"
        )
    return "\n".join(lines)


def ask_claude(
    system: str, message: str, schema: dict, model: str
) -> tuple[dict, dict]:
    """One headless Claude Code answer as structured output, with usage for the Run."""
    env = {k: v for k, v in os.environ.items() if k not in PROVIDER_KEYS}
    command = [
        "claude",
        "-p",
        "--model",
        model,
        "--output-format",
        "json",
        "--tools",
        "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--system-prompt",
        system,
        "--json-schema",
        json.dumps(schema),
    ]
    waits = [15, 60, 180, 600, 1200]
    for attempt in range(len(waits) + 1):
        t0 = time.perf_counter()
        # Run outside the repo so no CLAUDE.md or AGENTS.md is picked up.
        done = subprocess.run(
            command,
            input=message,
            capture_output=True,
            text=True,
            env=env,
            cwd=tempfile.gettempdir(),
            timeout=600,
        )
        elapsed = round(time.perf_counter() - t0, 3)
        try:
            out = json.loads(done.stdout)
        except ValueError:
            out = {"is_error": True, "result": done.stderr[-500:] or done.stdout[-500:]}
        if not out.get("is_error") and out.get("structured_output") is not None:
            usage = out.get("usage") or {}
            meta = {
                "stand_in": "claude-code",
                "stand_in_model": next(iter(out.get("modelUsage") or {}), model),
                "latency_seconds": elapsed,
                "token_usage": {
                    "input_tokens": (usage.get("input_tokens") or 0)
                    + (usage.get("cache_creation_input_tokens") or 0)
                    + (usage.get("cache_read_input_tokens") or 0),
                    "output_tokens": usage.get("output_tokens") or 0,
                },
            }
            return out["structured_output"], meta
        if attempt < len(waits):
            print(
                f"  claude -p failed ({str(out.get('result'))[:200]}); retrying in {waits[attempt]}s",
                flush=True,
            )
            time.sleep(waits[attempt])
    raise RuntimeError(f"claude -p kept failing: {str(out.get('result'))[:500]}")


def make_stand_in(
    provider: str,
    graph: dict,
    rules: StoryRules,
    coverage: Coverage,
    model: str,
    holder: dict,
):
    style = STYLES[provider]
    system = (
        SYSTEM_PROMPT
        + STAND_IN_RULES
        + f"\nYour play style: {style['goal'].removeprefix('SYNTHETIC: ')}\nYour voice: {style['voice']}\n"
    )

    def stand_in(schema, payload, max_tokens):
        runner = holder["runner"]
        message = prompt_message(payload)
        if schema is ModelDecision:
            note = steering_note(rules, graph, runner, payload, coverage)
            message = f"Private steering note (never mention it):\n{note}\n\nDecision Prompt:\n{message}"
        try:
            reply, meta = ask_claude(system, message, schema.model_json_schema(), model)
            return schema.model_validate(reply), meta
        except ValueError as exc:
            raise BrokenReply(f"invalid structured output: {exc}") from exc

    return stand_in


def mark_synthetic(run_dir: Path, provider: str, model: str):
    settings_path = run_dir / "experiment.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings.update(
        {
            "synthetic": True,
            "display_provider": provider,
            "stand_in": {"tool": "claude-code", "model": model},
        }
    )
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def play(
    provider: str,
    graph: dict,
    rules: StoryRules,
    coverage: Coverage,
    model: str,
    root: Path,
):
    style = STYLES[provider]
    run_dir = root / f"synthetic-{provider}"
    folder = RunFolder(run_dir)
    summary = folder.summary() if (run_dir / "summary.json").exists() else None
    if summary and summary.get("status") == "complete":
        print(f"[{provider}] already complete", flush=True)
        return
    holder: dict = {}
    runner = Runner(
        graph=graph,
        provider="mock",
        model_id=style["model"],
        run_dir=run_dir,
        goal=style["goal"],
        allow_unverified=True,
        resume=(run_dir / "checkpoint.json").exists(),
        stand_in=make_stand_in(provider, graph, rules, coverage, model, holder),
    )
    holder["runner"] = runner
    mark_synthetic(run_dir, provider, model)
    if runner.state["status"] != "running":
        # A stopped Run plays on from its checkpoint.
        runner.state["status"] = "running"
    choices = len(runner.state["decisions"])
    while runner.state["status"] == "running":
        coverage.pass_node(runner.state["node"])
        runner.step()
        if len(runner.state["decisions"]) > choices:
            choices = len(runner.state["decisions"])
            decision = runner.state["decisions"][-1]
            coverage.choose(decision["choice_key"])
            print(
                f"[{provider}] #{choices} ch{decision['chapter']} {decision['label']}",
                flush=True,
            )
    print(f"[{provider}] {runner.state['status']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", choices=list(STYLES), action="append")
    parser.add_argument(
        "--model", default="haiku", help="Claude model for the stand-in"
    )
    parser.add_argument("--runs-dir", type=Path, default=RUNS)
    args = parser.parse_args()
    graph = read_json(GRAPH)
    rules = StoryRules(graph)
    coverage = Coverage(args.runs_dir)
    failures = []

    def guarded(provider):
        try:
            play(provider, graph, rules, coverage, args.model, args.runs_dir)
        except Exception:
            failures.append(provider)
            print(f"[{provider}] STOPPED\n{traceback.format_exc()}", flush=True)

    threads = [threading.Thread(target=guarded, args=(p,)) for p in args.only or STYLES]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if failures:
        sys.exit(
            f"Stopped: {', '.join(failures)}. Run the script again to resume them."
        )


if __name__ == "__main__":
    main()
