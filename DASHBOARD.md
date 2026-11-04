# Decision Atlas — Detroit-style end-of-chapter flowcharts

A **local, read-only** flowchart viewer for the full-playthrough narrative LLM benchmark. The frontend is a self-contained HTML/CSS/JavaScript application served by the existing FastAPI backend, with no Node toolchain, external frontend dependencies, or third-party CDN requests.

The visual language follows the white end-of-chapter flowchart design of *Detroit: Become Human*: compact rectangular story nodes, fine branch connectors, model paths in color, and every untaken script branch remaining visible in pale gray. A small model-family icon is attached to each visited node for **each selected run**, including multiple versions of the same provider. Click a logo on a choice to inspect that model's **recorded justification**, its exact offered actions, earlier choice explanations, and resulting state changes. Visited scene nodes show their observations and the last preceding model choice when available. This is a *stated justification*, not private internal chain-of-thought.

## Start the frontend

```bash
pip install -r requirements.txt
python -m detroit_benchmark dashboard --runs-dir demo_runs
```

Open **http://127.0.0.1:8000**. The included two playthroughs are **synthetic, deterministic mock-agent runs** of the fictional *Aurora Station* story. They are not actual Detroit gameplay or model API responses.

To visualize real benchmark experiments:

```bash
python -m detroit_benchmark play story.json --provider openai \
  --model gpt-4.1-mini --run-dir runs/chatgpt --allow-unverified
python -m detroit_benchmark play story.json --provider anthropic \
  --model claude-sonnet-4-5 --run-dir runs/claude --allow-unverified
python -m detroit_benchmark dashboard --runs-dir runs
```

Supply appropriate API keys to run the models. The dashboard itself uses **no** API keys or model calls. `--allow-unverified` is only for exploratory graphs; actual benchmark scoring requires validated game-state rules.

## Multi-run flowchart controls

- **Choose runs:** The new `VISIBLE PLAYTHROUGHS` button opens a searchable panel grouped by provider. Check any number of playthroughs, use **Select all compatible**, or remove individual colored chips. Six runs are selected automatically for the first available graph, and you can select all others.
- **Graph compatibility:** Only runs with the **same story graph SHA-256** can be overlaid. Incompatible runs are disabled; clear the selection to select a different story graph. This avoids aligning unrelated decisions.
- **All script paths remain on screen:** The full saved chapter graph provides the unchanging gray background. Each selected run traces **its own route** in a separate color; shared edges are rendered as parallel, narrow colored lines. No available source branch is removed.
- **Individual model markers:** Every node visited by a selected run gets a compact, clickable model-family mark, with colors distinguishing runs of the same model family. Nodes expand vertically to fit all marks rather than hiding extra visits. Click the specific mark to inspect only that playthrough's logged choice.
- **Complete provenance:** The reasoning drawer includes the chosen action, other options, recorded public justification, prior decision history, world-state delta, full model input/output, and inference telemetry. It also identifies *which run* the record came from.
- **Scrollable legend:** All visible runs are shown by color, model logo, and model ID. The top strip shows removable run chips.
- **Pan / zoom:** Drag the canvas, scroll to zoom, or choose Fit View. All chapters, even unvisited ones, are reachable from the chapter rail. Cross-chapter portals navigate without losing run selections.
- **Live updates:** The dashboard polls for new events and refreshes active runs without discarding your run selection or canvas position. The service is read-only and uses no model API keys.
- **Legacy dashboard:** The previous experiment summary remains available at `/legacy`.

### Additional providers

Run metadata is provider-agnostic: the viewer recognizes OpenAI, Anthropic, xAI/Grok, Google/Gemini, DeepSeek and Mistral marks, with a labeled generic mark for other providers. You can display multiple models **and repeated runs of the same model** at once.

The benchmark runner now supports these `--provider` values:

| Provider | Key variable | Example model flag |
| --- | --- | --- |
| `openai` | `OPENAI_API_KEY` | `--model gpt-4.1-mini` |
| `anthropic` | `ANTHROPIC_API_KEY` | `--model claude-sonnet-4-5` |
| `xai` | `XAI_API_KEY` | `--model grok-4` |
| `google` | `GOOGLE_API_KEY` | `--model gemini-2.5-flash` |
| `deepseek` | `DEEPSEEK_API_KEY` | `--model deepseek-chat` |
| `mistral` | `MISTRAL_API_KEY` | `--model mistral-large-latest` |
| `openrouter` | `OPENROUTER_API_KEY` | `--model <provider/model>` (required) |

Google Gemini adapter `langchain-google-genai` is included in `requirements.txt`. xAI, DeepSeek, Mistral, and OpenRouter use compatible chat endpoints through `langchain-openai`. An individual model must support the structured output mechanism the runner uses; these integrations are not integration-tested against live APIs here. Set `--model` to an actual model your account can access.

```bash
python -m detroit_benchmark play story.json --provider xai --model grok-4 --run-dir runs/grok-4 --allow-unverified
python -m detroit_benchmark play story.json --provider openai --model gpt-4.1-mini --run-dir runs/gpt-mini --allow-unverified
python -m detroit_benchmark play story.json --provider anthropic --model claude-sonnet-4-5 --run-dir runs/claude --allow-unverified
python -m detroit_benchmark dashboard --runs-dir runs
```

**Demo honesty:** The `demo_runs` directory contains ten **synthetic deterministic mock runs** with sample model-family branding so you can examine multi-run selection and route overlays. None of those examples were generated by GPT, Claude, Grok, Gemini, DeepSeek, or Mistral. `experiment.json` retains `provider: mock`; `display_provider` changes only the preview icon, and the reasoning drawer explicitly says synthetic preview.

## Why the full story graph matters

The run's `events.jsonl` records only what happened. It is impossible to know **all untaken paths** from the event stream alone. **New benchmark runs write `story-graph.json` into their run folder**, a snapshot of the exact graph used by the model. The UI renders the *whole* chapter graph from that file and overlays the observed routes from the events.

For existing runs created before this change, the backend tries to match the run's `graph_sha256` to the bundled `examples/*.json` or an optionally supplied graph folder:

```bash
python -m detroit_benchmark dashboard --runs-dir runs --graphs-dir ./data
```

If it cannot find a matching graph, the backend can provide an event-only reconstruction for the legacy UI, but the **flowchart refuses to present it as complete** and instead asks for the original graph. Unrecorded destinations are *not invented*.

## API additions

| Route | Purpose |
| --- | --- |
| `GET /api/runs` | Discover available recorded experiments |
| `GET /api/runs/{id}` | Events, timeline, and compact decision records |
| `GET /api/runs/{id}/flowchart` | Full chapter graph, branch labels, and fidelity/completeness status |
| `GET /api/runs/{id}/events/{index}` | Full stored model input, output, justification, and state transition |
| `GET /api/compare?run_ids=A&run_ids=B` | Existing pairwise structured comparison API (legacy; the multi-run frontend fetches multiple logs independently) |
| `GET /legacy` | Previous full benchmark dashboard |
| `GET /api/docs` | OpenAPI docs |

The flowchart API excludes full dialogue to keep rendering lightweight. Dialogue/context is fetched only from a selected recorded event. Event logs, graph snapshot, checkpoint, and metadata stay entirely local.

## Visual previews

These are from two **synthetic mock runs**, not genuine LLM responses or the actual game:

![Chapter flowchart](docs/flowchart_overview.png)

![Model justification panel](docs/flowchart_reasoning.png)

![Two-run overlay](docs/flowchart_comparison.png)

## Development and security

```bash
pytest -q
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
