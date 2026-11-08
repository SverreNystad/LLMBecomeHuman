"""python -m detroit_benchmark ..."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
from .ingest import apply_overrides, compile_from_repo
from .engine import Runner, validate_graph


def read_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main():
    p = argparse.ArgumentParser(
        prog="detroit-benchmark", description="LLM narrative-choice benchmark"
    )
    sub = p.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser(
        "ingest", help="Compile local transcript repository (unverified game rules)"
    )
    ingest.add_argument("--repo", type=Path, required=True)
    ingest.add_argument("--out", type=Path, default=Path("story.json"))
    ingest.add_argument("--overrides", type=Path)
    validate = sub.add_parser(
        "validate", help="Verify story graph references and fidelity warnings"
    )
    validate.add_argument("graph", type=Path)
    validate.add_argument("--strict", action="store_true")
    play = sub.add_parser(
        "play", help="Run, log, and checkpoint a complete narrative playthrough"
    )
    play.add_argument("graph", type=Path)
    play.add_argument(
        "--provider",
        choices=[
            "openai",
            "anthropic",
            "xai",
            "google",
            "deepseek",
            "mistral",
            "openrouter",
            "mock",
        ],
        required=True,
    )
    play.add_argument("--model")
    play.add_argument(
        "--goal", default="Make decisions according to your own judgment."
    )
    play.add_argument("--run-dir", type=Path, required=True)
    play.add_argument(
        "--allow-unverified",
        action="store_true",
        help="EXPLORATORY ONLY: assume unknown conditions/final routes; not valid for scientific scoring",
    )
    play.add_argument("--resume", action="store_true")
    play.add_argument("--max-steps", type=int, default=30000)
    play.add_argument("--max-prompt-chars", type=int, default=350000)
    play.add_argument(
        "--temperature",
        type=lambda v: None if v.lower() == "none" else float(v),
        default=0,
        help="Sampling temperature, or 'none' to omit it and use the provider default",
    )
    play.add_argument(
        "--initial-flags", type=Path, help="Optional JSON dict of game-state flags"
    )
    compare = sub.add_parser("compare", help="Compare saved playthroughs")
    compare.add_argument("run_dirs", type=Path, nargs="+")
    compare.add_argument("--out", type=Path)
    dashboard = sub.add_parser(
        "dashboard", help="Browse saved playthroughs in a local web dashboard"
    )
    dashboard.add_argument("--runs-dir", type=Path, default=Path("runs"))
    dashboard.add_argument(
        "--graphs-dir",
        type=Path,
        help="Optional folder containing story graph JSON files for older runs",
    )
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8000)
    args = p.parse_args()
    if args.command == "dashboard":
        import uvicorn
        from .dashboard import create_app

        print(f"Open http://{args.host}:{args.port} to view the benchmark dashboard")
        uvicorn.run(
            create_app(args.runs_dir, args.graphs_dir), host=args.host, port=args.port
        )
    elif args.command == "ingest":
        graph = compile_from_repo(args.repo)
        if args.overrides:
            graph = apply_overrides(graph, read_json(args.overrides))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "output": str(args.out),
                    "metadata": graph["metadata"],
                    "validation": validate_graph(graph),
                },
                indent=2,
            )
        )
    elif args.command == "validate":
        result = validate_graph(read_json(args.graph), args.strict)
        print(json.dumps(result, indent=2))
        if not result["valid"]:
            raise SystemExit(1)
    elif args.command == "play":
        run = Runner(
            graph=read_json(args.graph),
            provider=args.provider,
            model_id=args.model,
            run_dir=args.run_dir,
            goal=args.goal,
            allow_unverified=args.allow_unverified,
            initial_flags=read_json(args.initial_flags) if args.initial_flags else None,
            max_steps=args.max_steps,
            max_prompt_chars=args.max_prompt_chars,
            temperature=args.temperature,
            resume=args.resume,
        )
        print(json.dumps(run.run(), indent=2, ensure_ascii=False))
    elif args.command == "compare":
        results = []
        for d in args.run_dirs:
            summary = read_json(d / "summary.json")
            events = [
                json.loads(x)
                for x in (d / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if x
            ]
            decisions = {
                e["node_id"]: e.get("decision_key")
                for e in events
                if e["type"] == "decision"
            }
            results.append(
                {
                    "run_dir": str(d),
                    "provider": summary["provider"],
                    "model": summary["model"],
                    "status": summary["status"],
                    "choices": summary["number_of_choices"],
                    "chapters": len(summary["chapters_visited"]),
                    "fidelity": summary["fidelity"],
                    "decision_map": decisions,
                    "warnings": len(summary["warnings"]),
                }
            )
        keys = set().union(*(r["decision_map"].keys() for r in results))
        disagreements = [
            {
                "node_id": k,
                "selected": {r["run_dir"]: r["decision_map"].get(k) for r in results},
            }
            for k in sorted(keys)
            if len({r["decision_map"].get(k) for r in results}) > 1
        ]
        output = {
            "runs": results,
            "shared_decision_nodes": len(
                set.intersection(*(set(r["decision_map"]) for r in results))
            )
            if results
            else 0,
            "differing_or_unvisited_nodes": disagreements,
            "note": "Different paths may visit different decision nodes. Do not equate coverage with performance.",
        }
        if args.out:
            args.out.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
