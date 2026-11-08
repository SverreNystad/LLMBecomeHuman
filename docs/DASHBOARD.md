# Decision Atlas — story reader and Detroit-style flowcharts

A **local, read-only** viewer for the full-playthrough narrative LLM benchmark. It opens on the **Story** view, and the **Flowchart** tab holds the chapter graph. The frontend is a self-contained HTML/CSS/JavaScript application served by the existing FastAPI backend, with no Node toolchain, external frontend dependencies, or third-party CDN requests.

The visual language follows the white end-of-chapter flowchart design of *Detroit: Become Human*: compact rectangular story nodes, fine branch connectors, model paths in color, and every untaken script branch remaining visible in pale gray. A small model-family icon is attached to each visited node for **each selected run**, including multiple versions of the same provider. Click a logo on a choice to inspect that model's **recorded justification**, its exact offered actions, earlier choice explanations, and resulting state changes. Visited scene nodes show their observations and the last preceding model choice when available. This is a *stated justification*, not private internal chain-of-thought.

## Start the frontend

```bash
uv sync
uv run python -m detroit_benchmark dashboard --runs-dir demo_runs
```

Open **http://127.0.0.1:8000**. The included two playthroughs are **synthetic, deterministic mock-agent runs** of the fictional *Aurora Station* story. They are not actual Detroit gameplay or model API responses.

To visualize real benchmark experiments:

```bash
uv run python -m detroit_benchmark play story.json --provider openai \
  --model gpt-4.1-mini --run-dir runs/chatgpt --allow-unverified
uv run python -m detroit_benchmark play story.json --provider anthropic \
  --model claude-sonnet-4-5 --run-dir runs/claude --allow-unverified
uv run python -m detroit_benchmark dashboard --runs-dir runs
```

Supply appropriate API keys to run the models. The dashboard itself uses **no** API keys or model calls. `--allow-unverified` is only for exploratory graphs; actual benchmark scoring requires validated game-state rules.

## Story view

Read what happened in a run, one chapter at a time.

- **Following:** choose the run to read. The other selected runs appear as comparisons. Clicking a run chip follows that run too.
- **Script text:** each section shows its dialogue, and the current protagonist's lines are highlighted. Boxes show what was inspected.
- **Decision cards:** each card shows the options, the followed run's choice and stated reason, and whether the selected models agreed or split. Click a model's mark to read why it chose differently.
- **Amber notes:** these mark outcomes the benchmark assumed because the transcript has no executable rule. A model's decision did not pick them.
- **Decisions only:** shortens the text between decisions to a short lead-in and outcome. The rest expands on click.
- **Number strip:** jumps to a decision. Amber numbers are decisions where the selected models split.
- **Chapter rail:** shows titles, the playable character and this run's decision count. Chapters the run never reached are dimmed.
- **Links between views:** a card's **Show on flowchart** opens that node, and the drawer's **Read this moment in the story** comes back.

The text is rebuilt from a fan transcript, so optional and alternate scenes can run back to back. It is not what a player sees in the game.

Chapter titles are kept in `dashboard.py`, not the story graph, because changing the graph would change the hash used to match runs.

## Multi-run flowchart controls

- **Choose runs:** The new `VISIBLE PLAYTHROUGHS` button opens a searchable panel grouped by provider. Check any number of playthroughs, use **Select all compatible**, or remove individual colored chips. All runs that recorded decisions on the newest real story graph are selected automatically.
- **Graph compatibility:** Only runs with the **same story graph SHA-256** can be overlaid. Incompatible runs are disabled; clear the selection to select a different story graph. This avoids aligning unrelated decisions.
- **All script paths remain on screen:** The full saved chapter graph provides the unchanging gray background. Each selected run traces **its own route** in a separate color; shared edges are rendered as parallel, narrow colored lines. No available source branch is removed.
- **Merged scenes:** Scenes that follow each other with no way to branch are one node, showing their full dialogue and inspected details. Scroll inside a node to read long passages, or click it to read the script in the side panel, including on branches the run didn't take. Choices, conditions and every branch keep their own nodes.
- **Individual model markers:** Every node visited by a selected run gets a compact, clickable model-family mark, with colors distinguishing runs of the same model family. Nodes expand vertically to fit all marks rather than hiding extra visits. Click the specific mark to inspect only that playthrough's logged choice.
- **Complete provenance:** The reasoning drawer includes the chosen action, other options, recorded public justification, prior decision history, world-state delta, full model input/output, and inference telemetry. It also identifies *which run* the record came from.
- **Legend:** Expand the legend at the top left to see all visible runs by color, model logo, and model ID. The top strip shows removable run chips.
- **Pan / zoom:** Long chapters open at a readable zoom on their first node. Drag the canvas, scroll to zoom, or choose Fit View to see the whole chapter. All chapters, even unvisited ones, are reachable from the chapter rail. Cross-chapter portals navigate without losing run selections.
- **Run status:** A run with no final summary and no new events for 15 minutes shows as stopped rather than running.
- **Live updates:** The dashboard polls for new events and refreshes active runs without discarding your run selection or canvas position. The service is read-only and uses no model API keys.
- **Legacy dashboard:** The previous experiment summary remains available at `/legacy`.

### Additional providers

Run metadata is provider-agnostic: the viewer recognizes OpenAI, Anthropic, xAI/Grok, Google/Gemini, DeepSeek and Mistral marks, with a labeled generic mark for other providers. You can display multiple models **and repeated runs of the same model** at once.

The benchmark runner now supports these `--provider` values:

| Provider     | Key variable         | Example model flag                    |
| ------------ | -------------------- | ------------------------------------- |
| `openai`     | `OPENAI_API_KEY`     | `--model gpt-4.1-mini`                |
| `anthropic`  | `ANTHROPIC_API_KEY`  | `--model claude-sonnet-4-5`           |
| `xai`        | `XAI_API_KEY`        | `--model grok-4`                      |
| `google`     | `GOOGLE_API_KEY`     | `--model gemini-2.5-flash`            |
| `deepseek`   | `DEEPSEEK_API_KEY`   | `--model deepseek-chat`               |
| `mistral`    | `MISTRAL_API_KEY`    | `--model mistral-large-latest`        |
| `openrouter` | `OPENROUTER_API_KEY` | `--model <provider/model>` (required) |

Google Gemini adapter `langchain-google-genai` is included in `pyproject.toml`. xAI, DeepSeek, Mistral, and OpenRouter use compatible chat endpoints through `langchain-openai`. An individual model must support the structured output mechanism the runner uses; these integrations are not integration-tested against live APIs here. Set `--model` to an actual model your account can access.

```bash
uv run python -m detroit_benchmark play story.json --provider xai --model grok-4 --run-dir runs/grok-4 --allow-unverified
uv run python -m detroit_benchmark play story.json --provider openai --model gpt-4.1-mini --run-dir runs/gpt-mini --allow-unverified
uv run python -m detroit_benchmark play story.json --provider anthropic --model claude-sonnet-4-5 --run-dir runs/claude --allow-unverified
uv run python -m detroit_benchmark dashboard --runs-dir runs
```

**Demo honesty:** The `demo_runs` directory contains ten **synthetic deterministic mock runs** with sample model-family branding so you can examine multi-run selection and route overlays. None of those examples were generated by GPT, Claude, Grok, Gemini, DeepSeek, or Mistral. `experiment.json` retains `provider: mock`; `display_provider` changes only the preview icon, and the reasoning drawer explicitly says synthetic preview.

## Why the full story graph matters

The run's `events.jsonl` records only what happened. It is impossible to know **all untaken paths** from the event stream alone. **New benchmark runs write `story-graph.json` into their run folder**, a snapshot of the exact graph used by the model. The UI renders the *whole* chapter graph from that file and overlays the observed routes from the events.

For existing runs created before this change, the backend tries to match the run's `graph_sha256` to the bundled `examples/*.json` or an optionally supplied graph folder:

```bash
uv run python -m detroit_benchmark dashboard --runs-dir runs --graphs-dir ./data
```

If it cannot find a matching graph, the backend can provide an event-only reconstruction for the legacy UI, but the **flowchart refuses to present it as complete** and instead asks for the original graph. Unrecorded destinations are *not invented*.

## API additions

| Route                                  | Purpose                                                                                                          |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `GET /api/runs`                        | Discover available recorded experiments                                                                          |
| `GET /api/runs/{id}`                   | Events, timeline, and compact decision records                                                                   |
| `GET /api/runs/{id}/story?chapter=X`   | One chapter's dialogue, inspected details, decisions and assumed outcomes, in order                              |
| `GET /api/runs/{id}/flowchart`         | Full chapter graph, scene script, branch labels, and fidelity/completeness status                                |
| `GET /api/runs/{id}/events/{index}`    | Full stored model input, output, justification, and state transition                                             |
| `GET /api/compare?run_ids=A&run_ids=B` | Existing pairwise structured comparison API (legacy; the multi-run frontend fetches multiple logs independently) |
| `GET /legacy`                          | Previous full benchmark dashboard                                                                                |
| `GET /api/docs`                        | OpenAPI docs                                                                                                     |

The flowchart API includes each scene's dialogue and inspected details, but not source keys. The Story view fetches a run's text one chapter at a time. Event logs, graph snapshot, checkpoint, and metadata stay entirely local.

## Visual previews

These are from two **synthetic mock runs**, not genuine LLM responses or the actual game:

![Chapter flowchart](docs/flowchart_overview.png)

![Model justification panel](docs/flowchart_reasoning.png)

![Two-run overlay](docs/flowchart_comparison.png)

## Development and security

```bash
uv run pytest -q
```

API, graph-snapshot, incomplete-history, and interaction tests are included. The optional browser test runs with Playwright + Chromium when installed. All other tests run without the browser.

The service binds to `127.0.0.1` by default and has **no authentication**. Do not expose it publicly without authentication. Source-derived story graphs and model prompts may contain copyrighted material. The importer records chapter-by-chapter coverage counts for supported source `app-choice-group` and `app-condition-group` elements, and rejects mismatches instead of silently omitting branches. This does **not** certify that the transcript documents every hidden or gameplay-only path. A transcript-derived graph still lacks independently verified Detroit game consequences; rendering an unverified route does not make its outcomes ground truth.

OpenAI logo asset source: [Lobe Icons](https://github.com/lobehub/lobe-icons). Claude logo asset source: [Simple Icons](https://github.com/simple-icons/simple-icons). Original icons and names are trademarks of their respective owners.

Additional sample-provider mark assets are from [Lobe Icons](https://github.com/lobehub/lobe-icons).

## Multi-run previews

Captured in Chromium against the local synthetic fixture API (no external models or remote assets involved):

![Ten simultaneously overlaid runs](docs/multirun_flowchart.png)

![Searchable run selection grouped by provider](docs/multirun_selector.png)

![Run-specific model justification](docs/multirun_reasoning.png)
