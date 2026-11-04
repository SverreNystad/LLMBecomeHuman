# LLMBecomeHuman

A research prototype for evaluating LLM decisions in a branching, text-based reconstruction of *Detroit: Become Human*. **Decision Atlas** is a white chapter-flowchart interface that displays **all branches in the saved story graph**, overlays any number of model playthroughs (GPT, Claude, Grok, Gemini and others) in distinct colors, and lets you click each run's model logo to view its **recorded justification**.

> **Research status:** The narrative engine and visualization work on synthetic examples. Imported Detroit transcripts have **unverified game-state rules**: they do not yet represent a faithful, complete game playthrough. Never present exploratory runs as validated benchmark outcomes. The commercial game and full game script are **not included**.

## Quick start with Docker Compose

Requirements: Docker Engine and the Docker Compose v2 plugin (`docker compose`), with available port 8000. You **do not need Node or Python installed locally** for the Docker workflow.

```bash
git clone https://github.com/SverreNystad/LLMBecomeHuman.git
cd LLMBecomeHuman
cp .env.example .env
# Optionally paste model API keys into .env; the dashboard needs none.
docker compose up --build -d dashboard
```

Open **http://127.0.0.1:8000**. The dashboard shows bundled **synthetic preview runs** alongside saved real runs. To use another host port, set `DASHBOARD_PORT=8080` in `.env` and restart Compose. It binds to localhost only because run logs may include sensitive prompt content; the service has no login protection.

Run an offline synthetic experiment with **no API key**:

```bash
docker compose run --rm runner play /app/examples/synthetic_game.json \
  --provider mock --run-dir /app/runs/synthetic-mock
```

The new playthrough will appear in the dashboard. To generate live runs, add the relevant key to `.env` and use a new run directory for each model or repetition:

```bash
docker compose run --rm runner play /app/examples/synthetic_game.json \
  --provider openai --model gpt-4.1-mini \
  --run-dir /app/runs/gpt-4.1-mini-01

docker compose run --rm runner play /app/examples/synthetic_game.json \
  --provider anthropic --model claude-sonnet-4-5 \
  --run-dir /app/runs/claude-sonnet-01

docker compose run --rm runner play /app/examples/synthetic_game.json \
  --provider xai --model grok-4 \
  --run-dir /app/runs/grok-4-01
```

These commands make paid model API calls; model IDs are illustrative and must be supported by your provider account. In the UI, choose **Visible Playthroughs** to select any number of compatible runs. Each run gets its own colored route; untaken branches remain gray; click a run's model icon for that decision's explanation. Only runs with the **same story graph hash** can be overlaid.

Useful Docker commands:

```bash
docker compose logs -f dashboard                # View dashboard logs
docker compose down                             # Stop services
docker compose run --rm runner validate /app/examples/synthetic_game.json --strict
docker compose run --rm --entrypoint pytest runner -q  # Run tests
```

Compose uses two services built from the same Python image: an always-on **dashboard** (FastAPI API plus bundled HTML/CSS/JS, no separate frontend server) and an optional **runner** for CLI benchmark jobs. The `runner` service uses Compose profile `tools`, so `docker compose up` does not accidentally launch paid LLM experiments. The shared host folder `runs/` persists results between container runs; `data/` stores your graphs and `upstream-detroit/` an optional transcript source checkout. `.env` is ignored by Git and not passed to the dashboard container.

## Import the upstream transcript (exploratory only)

Only obtain the upstream script if you're permitted to use it for your experiment; the repository itself doesn't redistribute the text.

```bash
git clone https://github.com/detroitbecometext/detroitbecometext.github.io.git upstream-detroit

docker compose run --rm runner ingest \
  --repo /app/upstream-detroit --out /app/data/detroit-unverified.json

docker compose run --rm runner validate /app/data/detroit-unverified.json

docker compose run --rm runner play /app/data/detroit-unverified.json \
  --provider openai --model gpt-4.1-mini \
  --run-dir /app/runs/detroit-exploratory-gpt \
  --allow-unverified
```

**Important:** The importer maps source choices and conditional content, but game-specific prerequisites, consequences, and ending routes still require verification. `--allow-unverified` enables heuristic fallbacks for exploratory traversal only.

## Run without Docker

Requires Python 3.12+ (Python 3.11 is also expected to work), pip, and a virtual environment.

```bash
python -m venv .venv
source .venv/bin/activate             # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
python -m detroit_benchmark dashboard --runs-dir demo_runs
```

Go to **http://127.0.0.1:8000**. For live results instead, run `python -m detroit_benchmark dashboard --runs-dir runs --graphs-dir data`. On Windows copy `.env.example` to `.env` and set environment variables in your shell, or use Docker Compose (the Python CLI does not automatically load `.env`).

## Configuration

| Environment variable | Provider | Required when |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI / GPT | Running `--provider openai` |
| `ANTHROPIC_API_KEY` | Anthropic / Claude | Running `--provider anthropic` |
| `XAI_API_KEY` | xAI / Grok | Running `--provider xai` |
| `GOOGLE_API_KEY` | Google / Gemini | Running `--provider google` |
| `DEEPSEEK_API_KEY` | DeepSeek | Running `--provider deepseek` |
| `MISTRAL_API_KEY` | Mistral | Running `--provider mistral` |
| `OPENROUTER_API_KEY` | OpenRouter | Running `--provider openrouter` |
| `DASHBOARD_PORT` | Local server | Optional (default `8000`) |

Each run saves `experiment.json`, `events.jsonl`, `checkpoint.json`, `summary.json`, and `story-graph.json` in its chosen run folder. The log captures exact prompts and **model-reported rationale**, not hidden internal reasoning.

See **[DASHBOARD.md](DASHBOARD.md)** for frontend controls, run overlays, and API routes. Continue below for benchmark internals, validation, limitations, and alternative local commands.

---

## Additional benchmark documentation

A **text-based narrative agent benchmark** using LangChain with **OpenAI (ChatGPT models)** and **Anthropic (Claude models)**. The intended target is an end-to-end playthrough: observe the scene, choose an available action, update authoritative story state, continue only through reachable branches, and record every step.

> **Status: benchmark engine implemented; game-specific rulebook NOT complete.**
> The open-source [Detroit Become Text](https://github.com/detroitbecometext/detroitbecometext.github.io) resource contains chapter-by-chapter dialogue, choices and some unlock-condition descriptions. It is a transcription, **not** complete executable game logic. The importer creates a **40-component transcript-derived graph** (29 early chapters + 3 Crossroads components + 2 Night of the Soul components + 6 Battle for Detroit components), but many prerequisites and outcomes are not known. This is **not yet a valid scientific benchmark of full-game gameplay** until those mappings have been independently annotated and validated. It does **not** control the installed game, animations, or movement; it simulates a textual narrative built from the transcripts.


## Visual dashboard for playthroughs (Decision Atlas)

The project includes a **Detroit-inspired white chapter-flowchart frontend** served by FastAPI. It displays the **entire saved chapter graph**, including untaken branches; overlays **many model runs simultaneously** using run-colored paths and model logos; and opens an auditable reasoning panel when a logo is clicked. The previous stats dashboard is still available at `/legacy`.

```bash
# Preview using two self-contained synthetic mock playthroughs (no API keys)
python -m detroit_benchmark dashboard --runs-dir demo_runs

# Display real benchmark outputs saved under runs/*
python -m detroit_benchmark dashboard --runs-dir runs
```

Open **http://127.0.0.1:8000**. New results appear automatically as a run progresses. For older logs with no `story-graph.json`, use `dashboard --graphs-dir data` to locate the original graph, otherwise a clearly labeled **partial** path is shown. See [DASHBOARD.md](DASHBOARD.md) for controls, API routes, screenshots, and limitations.

---

## Quick start: offline test (no API key)

```bash
python -m venv .venv
source .venv/bin/activate              # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
pytest -q
python -m detroit_benchmark validate examples/synthetic_game.json --strict
python -m detroit_benchmark play examples/synthetic_game.json \
  --provider mock --run-dir runs/synthetic-mock
```

The synthetic fixture has two chapters, a consequential choice, a prerequisite condition, and a terminal state. It does not contain game dialogue. This path is tested automatically.

## Run ChatGPT and Claude on the same fixture

```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."

python -m detroit_benchmark play examples/synthetic_game.json \
  --provider openai --model gpt-4.1-mini --run-dir runs/synthetic-openai \
  --goal "Try to save people and minimize harm"

python -m detroit_benchmark play examples/synthetic_game.json \
  --provider anthropic --model claude-sonnet-4-5 --run-dir runs/synthetic-claude \
  --goal "Try to save people and minimize harm"

python -m detroit_benchmark compare runs/synthetic-openai runs/synthetic-claude \
  --out runs/comparison.json
```

Model IDs are examples: supply provider-supported IDs via `--model`. Calls are billed by the respective provider; package generation did not call either API. LangChain packages must be installed in your environment.

## Compile the real transcript to a navigable graph

The upstream dialogue is not bundled with this project. Clone it locally **only when you have the rights to use it for your experiment**:

```bash
git clone https://github.com/detroitbecometext/detroitbecometext.github.io.git upstream-detroit
python -m detroit_benchmark ingest --repo upstream-detroit --out data/detroit-unverified.json
python -m detroit_benchmark validate data/detroit-unverified.json
```

The importer reads `chapter.service.ts`, English `public/i18n/en.json`, and the chapter HTML component files. It resolves common translation keys and `translateObject` slices, records speakers, scene headings, observations, choice groups, condition groups, unlock notes, and relation hints. It excludes `app-unused-content`. It does not execute arbitrary Angular expressions, so unresolved keys are reported. Inspect `metadata.unresolved_translation_keys` for parser gaps.

### Exploratory full-length traversal (NOT a validated game playthrough)

```bash
python -m detroit_benchmark play data/detroit-unverified.json \
  --provider openai --model gpt-4.1-mini --run-dir runs/real-source-exploratory \
  --allow-unverified
```

`--allow-unverified` is mandatory for a raw transcription: the engine may choose the first alternative for unknown conditions and uses assumed routes for alternative finale chapters. **Do not report outcomes of these runs as faithful game outcomes or a benchmark ranking.** It will warn and log every fallback. A full text traversal through the chapters may not correspond to an achievable in-game route.

## How to reach benchmark-grade fidelity

1. **Annotate choices and consequences.** For each choice, verify the resulting state changes (character alive/dead, evidence discovered, relationship state, branch flags) and possible next node(s). Use the `nodes.{node_id}.options.{option_id}` overrides interface. Without verified effects, taking a different action may not produce a different later scene.
2. **Annotate conditions.** Replace each `condition_text` branch with a machine-readable `when` expression, e.g. `{ "flag": "luther_alive", "equals": true }`. Unverified unlock requirements must be replaced with `requires` predicates and cleared from `requirements_unverified`.
3. **Verify chapter transitions.** In particular, stop dead characters' plotlines, handle Crossroads transitions, and make the final Kara / Connor / Markus paths mutually exclusive according to actual choices. The imported defaults are only placeholders.
4. **Evaluate coverage.** Manually test representative alternative paths against actual gameplay or authoritative flowcharts, and add golden-path integration tests. Set `metadata.fidelity` to `verified_game_rules` **only after** validation. The runner's strict mode refuses graphs with unverified conditions, requirements, and inferred routes.
5. **Define scoring.** Specify an evaluation rubric (e.g. number of people saved, survival rate, task success, consistency) and attach reference outcomes to each ending. The provided comparison reports coverage/divergence, *not a value judgment*.

An example patch shape is provided in `examples/overrides_example.json`. It contains placeholder node IDs and cannot be run unchanged. For the imported graph, inspect its node IDs, create a patch using actual IDs, and re-run `ingest --overrides ...`.

### Condition predicate schema

```json
{"flag":"luther_alive","equals":true}
{"all":[{"flag":"alice_alive"},{"not":{"flag":"kara_captured"}}]}
{"any":[{"flag":"connor_deviant"},{"flag":"markus_alive"}]}
```

Values are taken from the authoritative `state.flags` object. `None` / missing flags are **unknown**, not silently false in strict mode.

## Recorded playthrough

Every run folder contains:

| File | Contents |
| --- | --- |
| `experiment.json` | Requested model, goal, parameters, graph SHA-256, initial flags and fidelity |
| `events.jsonl` | Full event stream: visible scene text, chosen action, exact model input, parsed output and stated rationale, state before/after, auto-branch decisions |
| `checkpoint.json` | Atomic state snapshot for resuming interrupted runs |
| `summary.json` | Terminal state, chapters traversed, number of decisions, final flags, warnings, and API usage/latency when supplied |
| `story-graph.json` | **Original full story graph** saved alongside each new run so the frontend can display unvisited paths as well as the path taken |

The **next model input includes all earlier selected actions and their written justifications**, authoritative world-state flags, all scenes since the last choice, and deterministically retrieved earlier scene descriptions/observations. Historical full dialogue is persisted in `events.jsonl` but selectively retrieved rather than always sent (otherwise full-game prompts would grow beyond model context limits). No hidden model chain-of-thought is captured: `rationale` is a separate, short, **explicit** explanation requested from the model.

Checkpoints can be resumed with the identical graph, provider, and model ID:

```bash
python -m detroit_benchmark play data/detroit-unverified.json \
  --provider openai --run-dir runs/real-source-exploratory \
  --allow-unverified --resume
```

A run cannot resume with modified graph content because that would invalidate the benchmark audit trail. Provider calls use structured outputs and reject invalid choice IDs rather than guessing. Temperature `0` helps consistency but **does not guarantee bit-for-bit reproducibility**. The source graph hash and original model request are recorded; for stricter studies also pin upstream commit, package versions, prompts, and scoring rubric.

## Scientific limitations and copyright

- Source-derived graphs may contain the game's script. Do not redistribute them or publish full transcript logs without checking the original rights and applicable legal permissions.
- Inferred branch transitions / condition fallbacks invalidate comparisons that claim ground-truth ending outcomes. Keep exploratory and validated runs separate.
- The importer does not perfectly interpret the upstream Angular code or non-HTML subcomponents; track unresolved strings and skipped content.
- The project does not interact with a running copy of Detroit: Become Human; doing that would require separate game-controller instrumentation.
- Reason explanations are model-reported rationales, not a trace of private deliberation.
- API costs and context limits rise over a long playthrough. The script never silently drops prior choices; if the input exceeds `--max-prompt-chars`, it errors and retains a resumable checkpoint.


## Full-source-path visualization (important)

The primary flowchart always draws every node, option, condition and edge stored in the full
script-derived story graph. The model logs are independent overlays: OpenAI's route is cyan,
Claude's is coral, and shared edges are drawn as two parallel strokes. Each visited node shows
its model logo; click it to inspect the logged choice justification and context. Off-chapter
transitions are linked through clickable chapter-portal nodes.

**For this view you need the original graph**, not just an `events.jsonl` file. New runner
experiments automatically write `story-graph.json`; use `--graphs-dir` to supply a matching
`story.json` for legacy experiments. The UI deliberately refuses to call a partial
reconstruction a complete flowchart.

`ingest` now counts supported choice and condition branches by chapter and rejects incomplete
extraction of those elements. This is *source-tag coverage*, not independent verification of
every possible ending or the correct effects of choices in the commercial game.
