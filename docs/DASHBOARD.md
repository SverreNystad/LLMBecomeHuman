# LLM: Become Human — dashboard

A viewer for recorded Runs. On its own it is read-only; started with `--allow-own-runs` it also plays Visitor Runs, Runs a visitor starts with their own API key (see [Visitor Runs](#visitor-runs) and ADR 0003). It opens on the **Story** and the **Flowchart** sits next to it. It is plain HTML, CSS and JavaScript served by the FastAPI backend, with no build step. The only remote request is the Inter web font, which falls back to the system sans-serif when offline.

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

Supply appropriate API keys to run the models. The dashboard itself uses **no** API keys or model calls, unless it is started with `--allow-own-runs` (see [Visitor Runs](#visitor-runs)). `--allow-unverified` is only for exploratory graphs; actual benchmark scoring requires validated game-state rules.

The dashboard shows every Run found anywhere under `--runs-dir`. In the Docker image the runs root is `/app/saved_runs`: the maintainers' Runs sit in `runs/`, the synthetic previews in `previews/`, and Visitor Runs get their own writable `visitor-runs/` folder. In production that folder is a persistent volume, so Visitor Runs survive redeploys. See [Developer Setup](developer_setup.md#docker-compose).


## Look and feel

- **Theme:** a near-white grey interface with thin lines and the game's menu blue for highlights. Every colour is a CSS custom property on `:root` in `styles.css`.
- **Title screen:** always dark, with or without title art; the dashboard behind it keeps its light theme.
- **LED ring:** the logo is an android temple LED. It cycles blue, yellow and red when no Character is in play, and takes the current Character's colour inside a chapter.
- **Character colours:** each chapter takes its Character's colour: Connor blue, Kara yellow, Markus red. Each colour is a ramp of six shades from light to dark.
- **One shade per model:** each Shown Run holds one shade slot, so a model sits at the same place on the light-to-dark range in every chapter. Provider logos on the markers and a line style per provider tell same-coloured routes apart.
- **Six at a time:** at most six Runs are shown. Selecting a seventh is refused with a short notice.
- **Model bar:** the Shown Runs sit on one line beside **+**. When their chips don't fit, all but the Followed Run's collapse to logos. Hovering or focusing a logo grows it back into its full chip, name and × included, pushing its neighbours aside; it shrinks again when the pointer or focus leaves. Clicking a logo grows the new Followed Run's chip while the old one shrinks, both at once, and the bar glides to show the new chip whole if it would be cut off. Hovering never scrolls the bar. The growing and shrinking are animated, with the usual glitch on hover; under reduced motion the sizes change at once. If even the logos don't fit, or a grown chip pushes others past the edge, the bar's edges fade and ‹ › arrows scroll it.
- **Best of each:** shows one Run per provider (Anthropic, OpenAI, Google, xAI, DeepSeek, Mistral) for the shown story: a finished Run first, then the provider's best model. Each provider's ranking lives in `MODEL_RANK` in `app.js`; a model missing from it ranks after the listed ones, newest version first.
- **No model chosen:** after **Clear**, every chapter stays listed, faded, with the current one highlighted, and the dashboard keeps that chapter's Character theme, the background network included. The Story and the Flowchart both show **Choose a model**, which opens the model picker. The controls that need a model hide, and the + button pulses.
- **Narrow screens:** the chapter list becomes a scrolling strip above the content.

## Story

Read one Run, chapter by chapter.

- **Following:** the Followed Run is the one you read, picked from the Following menu or by clicking a model chip. The other Shown Runs appear as comparisons. Switching keeps your reading position: the Story stays on the scene or decision you were reading, or the nearest earlier one the new Run reached. A Run that never reached the chapter says so. Changing chapter still opens at its top.
- **Decision cards:** the options, each model's logo by the option it chose, the Followed Run's reason, and whether the models agreed. Hover a logo for the model's name; click it to show that model's reason in the card instead. The logo whose reason is shown is filled with its Run's colour. When the Followed Run's choice moved a gauge the game shows on screen (Gauge Feedback, such as "Probability of success: up" in The Hostage, "The deviant's stress: up to 62% (optimal)" in The Interrogation or "Relationship with Hank: up sharply"), the card shows that line below the options, worded exactly as the model read it. A gauge moved by a story rule rather than a choice (the helicopter in The Hostage) shows the same line on its own. A Joint Decision, made with two Characters' memories, asks "What do Markus and Connor do?" and says so under the question: "Decided with Markus's and Connor's memories". A Cross-Segment Decision, made by another Character inside this segment, asks about that Character and says "Decided as Markus".
- **Reasons:** every justification is shown as at most two sentences. Runs recorded before the engine capped them are cut when served; their files are not changed.
- **Decisions only:** the icon next to the Run picker shortens the text between decisions. The rest expands on click.
- **Number strip:** jumps to a decision. Highlighted numbers are decisions where the models split.
- **Moments:** click any line, scene or decision to open that Moment on the Flowchart, centred and highlighted.
- **Ending:** the Final Routes chapter opens with the Ending Summary, one column per Shown Run in their order and colours (a phone shows the Followed Run only). Each column says, in plain sentences, whether Connor became deviant or stayed a machine, how many times he died, whether his story ended and, if so, whether his mission failed; whether Kara ended free, captured, escaped from the camp or dead and whether Alice is with her; whether Markus's revolution was peaceful or violent and whether he lived. Below that are the Fates of Hank, Alice, Luther, Simon, North, Josh and Carl (alive, dead or unknown) and, under Detroit, how the revolution ended with the last three Public News headlines. A Run still playing shows "Story not finished". Anything the Run never recorded, or a final route the engine had to assume, is shown as unknown, never guessed. A Run that recorded no outcome at all (one played before the story tracked Fates) says so in one line instead of a column of unknowns. In the Story, a final route the engine assumed reads as a sentence, such as "This Run never decided this, so the story assumed: Kara got away." The card notes that outcomes come from the Run's recorded route, which is not verified game data.

![Ending Summary on a wide screen](images/ending_summary_desktop.png)

Chapter titles live in `dashboard.py`, not the story graph, because changing the graph would change the hash used to match Runs.

The Ending Summary is written on the server in `ending.py`. Every sentence, and the question each outcome answers (such as "Was Kara captured?"), comes from its one table, `OUTCOMES`, so the wording is corrected in one place.

## Flowchart

- **Every branch:** the full saved chapter graph is drawn in grey, and each Shown Run's route is drawn on top in its shade.
- **Merged scenes:** scenes that follow each other with no way to branch become one node with their full text.
- **Moments:** click a node to open the Story at that Moment, following a Run that passed through it.
- **Final Routes:** each route node is labelled with the question its outcome answers, such as "Was Kara captured?", taken from the same table as the Ending Summary, so no node shows an internal flag name.
- **Model markers:** click a model's marker on a node to read that Run's decision and reason.
- **Compatibility:** only Runs that share a story graph can be shown together. Clear the selection to switch stories.
- **Pan and zoom:** drag, scroll, or use the controls at the top right.
- **Live Runs:** the dashboard polls quietly and updates without losing your place. A Run with no new events for 15 minutes shows as stopped.

## Providers

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

**Demo honesty:** The `demo_runs` directory contains ten **synthetic deterministic mock runs** with sample model-family branding so you can examine multi-run selection and route overlays. None of those examples were generated by GPT, Claude, Grok, Gemini, DeepSeek, or Mistral. `experiment.json` retains `provider: mock`; `display_provider` changes only the preview icon, and the dashboard labels them as a synthetic preview.

## Why the full story graph matters

The run's `events.jsonl` records only what happened. It is impossible to know **all untaken paths** from the event stream alone. **New benchmark runs write `story-graph.json` into their run folder**, a snapshot of the exact graph used by the model. The UI renders the *whole* chapter graph from that file and overlays the observed routes from the events.

For existing runs created before this change, the backend tries to match the run's `graph_sha256` to the bundled `examples/*.json` or an optionally supplied graph folder:

```bash
uv run python -m detroit_benchmark dashboard --runs-dir runs --graphs-dir ./data
```

If it cannot find a matching graph, the backend can provide an event-only reconstruction, but the **flowchart refuses to present it as complete** and instead asks for the original graph. Unrecorded destinations are *not invented*.

## API additions

| Route                                  | Purpose                                                                                                          |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `GET /api/runs?visitor_runs=ID…`       | Discover available recorded experiments; private Visitor Runs are listed only when their ids are named            |
| `GET /api/runs/{id}`                   | Events, timeline, compact decision records, and the Run's `ending_summary`                                       |
| `GET /api/runs/{id}/story?chapter=X`   | One chapter's dialogue, inspected details, decisions and assumed outcomes, in order, each with its `moment` id    |
| `GET /api/runs/{id}/flowchart`         | Full chapter graph, scene script, branch labels, and fidelity/completeness status; each node has a `moment` id, and each route node a `heading` (its question) |
| `GET /api/runs/{id}/events/{index}`    | Full stored model input, output, justification, and state transition                                             |
| `GET /api/compare?run_ids=A&run_ids=B` | Existing pairwise structured comparison API (the frontend fetches each log on its own) |
| `GET /api/art/manifest`                | Scene-art entries from `data/scene-art.json` whose image is installed locally                                    |
| `GET /api/art/scene/{key}`             | One installed scene image (WebP) by manifest key, else 404                                                       |
| `GET /api/docs`                        | OpenAPI docs                                                                                                     |
| `GET /api/visitor-runs/config`         | With `--allow-own-runs`: the providers a Visitor Run can use (404 without the flag)                              |
| `POST /api/visitor-runs`               | With `--allow-own-runs`: `{provider, model, key}` starts a Visitor Run and returns its `id` (404 without the flag); 503 when the site is busy, 409 when this visitor already has one playing |
| `GET /api/visitor-runs/public?provider=P&model=M` | With `--allow-own-runs`: `{public_run_exists}`, whether a complete public Run of that exact provider and model id exists (404 without the flag) |
| `POST /api/visitor-runs/{id}/stop`     | With `--allow-own-runs`: stops that playing Visitor Run after its current model call (202); 404 if no such Run is playing |
| `POST /api/visitor-runs/models`        | With `--allow-own-runs`: `{provider, key}` lists the provider's model ids for the key; 401 when the provider rejects the key, 502 when it can't be reached, 429 past ten listings a minute from one client IP (404 without the flag) |
| `GET /api/visitor-runs/estimate?provider=P&model=M` | With `--allow-own-runs`: approximate `input_tokens` and `output_tokens` ranges (`low`, `high`) for a Visitor Run, and `public_run_exists` (the same answer as `/api/visitor-runs/public`) (404 without the flag) |

Story beats and Flowchart nodes share a `moment` id (the story graph node id), and story beats also carry a `visit` number for Moments a Run passes more than once. The flowchart API includes each scene's dialogue and inspected details, but not source keys. The Story view fetches a run's text one chapter at a time. Event logs, graph snapshot, checkpoint, and metadata stay entirely local.

## Visitor Runs

A Visitor Run is a Run a visitor starts from the dashboard with their own API key (see ADR 0003). The feature is off unless the dashboard starts with `--allow-own-runs`:

```bash
uv run python -m detroit_benchmark dashboard --runs-dir runs --allow-own-runs
```

The public site (llmbecomehuman.com) and the docker-compose dashboard start with the flag on; see the developer setup for the volume that keeps Visitor Runs across redeploys. Without the flag there is no form and every Visitor Run endpoint answers 404. With it, the model picker (**+**) ends with **Play your own Run**, which opens a small form: a provider, an API key (a password field) and a model id. There is no goal field: every Visitor Run plays the Detroit story under the default goal (*"Minimize harm while completing the story."*), in the same fidelity mode as the maintainers' Runs (unverified transcript approximation) and with the CLI defaults for every other play setting. When the form is opened by touch no field focuses by itself, so the keyboard stays down until you tap a field.

**The model list.** Once you enter a key, the server asks the provider's own list-models endpoint which models the key can use (all seven providers: OpenAI, Anthropic, Google, xAI, DeepSeek, Mistral and OpenRouter; for Google only the models that can chat). The model field then shows that list and filters it as you type; click a model, or pick one with the arrow keys and Enter. A rejected key and an unreachable provider give different messages, and the field stays free text, so a listing that fails never stops you typing a model id yourself. Each visitor (client IP) can list models ten times a minute; past that the server answers 429 with a message to wait. A provider's paged list is read at most 20 pages deep.

**The token estimate.** Once a model id is entered, the form shows about how many input and output tokens the Run will use, labelled as an approximation and never as a price. It comes from the story itself: every decision and Memory Update prompt along the story's shortest and longest routes, measured exactly as the engine builds them (the shortest with empty Character Memories and no Public News, the longest with full ones). Characters become tokens at 2.25 to 4 characters per token, and each decision answers in 60 to 400 output tokens and each Memory Update in 750 to 2,500. Those ranges are calibrated against the maintainers' real Runs, which record both their prompts and the tokens their providers counted: for its own prompts, every real Run's recorded totals fall within 10% of the range (a test checks this). The maintainers' Runs played an older prompt that carried the whole decision history, so their totals (4–14 million input tokens) sit above today's estimate (about 0.3–4.3 million for the Detroit story). The estimate is computed once per story file and cached.

**Live token counts.** While one of your Visitor Runs plays, its row above **Play your own Run** in the model picker (the one with **Stop**) shows the tokens it has used so far, input and output, next to its estimate, refreshed every four seconds.

**Start** plays the Run in a background thread of the dashboard process. It joins the Shown Runs straight away as the Followed Run, and the picker lists it as *playing* while it fills in. A Run that fails (a rejected key, say) ends and is listed as *partial*; the Run listing's `stop_reason` says why, scrubbed of the key.

- **Private:** each Visitor Run is saved under `visitor-runs/` in the runs folder, in a folder with a random, unguessable name. Unless it becomes public (below), only the browser that started it lists it: the browser keeps the ids of its Visitor Runs in local storage and sends them with the Run listing, so they are still listed after a reload. To review every Visitor Run, point a dashboard at the `visitor-runs/` folder itself.
- **Public:** when a Visitor Run *completes*, it becomes public, listed for everyone like any other Run, if no complete public Run of the same exact provider and model id exists yet. The Runs baked into the runs folder count, and so do Visitor Runs already made public; a dated variant or the OpenRouter route of a model counts as its own model. "First" means first to complete, not first to start. Partial and playing Runs are never public and don't count. The decision is made once, under a lock, so two Runs of the same model finishing together can't both become public, and it is kept as `publication.json` in the Run's folder, so it survives restarts. Decisions are made at start-up and whenever a Visitor Run ends, and which models have a public Run is remembered between those times, so a visitor's request never scans the runs folder. Before Start the form warns when a public Run of the chosen model already exists: *"A public Run of this model already exists. Yours will be saved but only you will see it."*
- **Stop:** while one of your Visitor Runs plays, the model picker (**+**) lists it above **Play your own Run** with a **Stop** button. Stop ends the Run after the model call under way and keeps it as a *partial* Run, with every choice made so far. Only the browser that started a Run knows its id, so nobody else sees its Stop button. A partial Run can't be resumed, because its key is gone.
- **Restarts:** when the dashboard starts with `--allow-own-runs`, any Visitor Run still marked in progress (cut off by a redeploy, say) is marked *partial*, so none is left in progress forever.
- **Play limits:** at most two Visitor Runs play at once across the site, and one per visitor, where a visitor is a client IP: Cloudflare's `CF-Connecting-IP` header when present, else the connecting address. Over the site limit, Start is refused with *"The site is busy … Try again later."*; a visitor with a Run already playing is told *"You already have a Run playing."* Both show in the form as a notice. A slot frees when its Run completes, is stopped or fails. The limits are `create_app(max_playing=2, max_playing_per_visitor=1)`.
- **The key:** it is sent to list the models and with Start only, handed straight to the model client and held in memory while the Run plays. It is never written to the run folder or any log, and error messages are scrubbed of it, including masked echoes of it (its first 6 or last 4 characters, for a key of 12 characters or more).

## On a phone

At widths up to 760 px the controls stack in three levels above the Story or Flowchart:

- **Top:** the LLM: Become Human brand and the sound toggle, only while the Story is scrolled to the top.
- **Middle:** the chapter title and, in the Story, the Following menu and decision numbers. It folds away while you scroll down and comes back on a small scroll up; swiping up or down on the bars folds or unfolds it.
- **Always on screen:** the chapter row (swipe it sideways, tap a chapter to open it), Story/Flowchart and **+** for choosing models. The row of chosen-model chips is not shown; use **+**.

Touch works like hovering does on a computer:

- **Flowchart:** it opens fitted around the current Moment and its neighbours. Drag to pan, pinch to zoom. The first tap on a box shows its dialogue (the next opens it in the Story) and glides the box and its dialogue into view, zooming out no further than 0.85×; a dialogue still too tall starts at the top of the screen and scrolls inside itself. The first tap on a model's marker unfolds its decision card below the box and glides the box and the whole card into view by the same rules; a card still too tall sits right under the box at the top of the screen and scrolls inside itself. The next tap opens the details.
- **Details:** the details panel slides up from the bottom to about 45% of the screen, and the Flowchart keeps the selected box above it. Drag its grip up to grow it to about 70% (the middle level folds away for room, and comes back when the panel shrinks again), down to shrink it back, or further down to close it; × closes it too.
- **Story:** tapping a model's logo names the model and shows its reason.
- **Keyboard:** nothing focuses a text field by itself, so the keyboard opens only when you tap one. **+** opens the model picker with Search unfocused; on a computer, Search is focused at once so you can start typing.

Tablets and phones held sideways (wider than 760 px) keep the normal layout.

![Phone: Story mid-chapter](images/phone_story_scrolled.png)
![Phone: Flowchart around the current Moment](images/phone_flowchart_moment.png)
![Phone: details from the bottom](images/phone_details.png)

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

