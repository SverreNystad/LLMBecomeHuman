"""Optional end-to-end UI contract, using in-process API responses, no network.

Install Playwright and Chromium separately to run this test in local development.
Other tests remain runnable without a browser.
"""

from __future__ import annotations

import shutil
import socket
import threading
import time
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from detroit_benchmark.dashboard import create_app

PROJECT = Path(__file__).resolve().parents[1]
ASSETS = PROJECT / "detroit_benchmark" / "dashboard_assets"


def test_chapter_flowchart_browser_interactions():
    playwright = pytest.importorskip("playwright.sync_api")
    binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        pytest.skip("Chromium executable unavailable")
    c = TestClient(create_app(PROJECT / "demo_runs" / "aurora"))
    runs = c.get("/api/runs").json()["runs"]
    mock_responses = {"/api/runs": {"runs": runs}}
    for r in runs:
        run_id = r["id"]
        detail = c.get(f"/api/runs/{run_id}").json()
        mock_responses[f"/api/runs/{run_id}"] = detail
        flowchart = c.get(f"/api/runs/{run_id}/flowchart").json()
        mock_responses[f"/api/runs/{run_id}/flowchart"] = flowchart
        for chapter in flowchart["chapters"]:
            path = f"/api/runs/{run_id}/story?chapter={quote(chapter, safe='')}"
            mock_responses[path] = c.get(path).json()
        for ev in detail["events"]:
            mock_responses[f"/api/runs/{run_id}/events/{ev['index']}"] = c.get(
                f"/api/runs/{run_id}/events/{ev['index']}"
            ).json()

    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    css = (ASSETS / "styles.css").read_text(encoding="utf-8")
    js = (ASSETS / "app.js").read_text(encoding="utf-8")
    story_js = (ASSETS / "story.js").read_text(encoding="utf-8")
    characters_js = (ASSETS / "characters.js").read_text(encoding="utf-8")
    html = html.replace(
        '<link rel="stylesheet" href="/assets/styles.css">', f"<style>{css}</style>"
    )
    html = html.replace('<script src="/assets/app.js" defer></script>', "")
    html = html.replace('<script src="/assets/story.js" defer></script>', "")
    html = html.replace('<script src="/assets/characters.js" defer></script>', "")

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=binary, args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(4500)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("about:blank")
            page.set_content(html)
            page.evaluate(
                """data => {
              window.__responses = data;
              window.fetch = async url => ({
                ok: !!window.__responses[url], status: window.__responses[url] ? 200 : 404,
                json: async () => window.__responses[url] ?? {detail:'Mock API route missing'}
              });
            }""",
                mock_responses,
            )
            page.add_script_tag(content=characters_js)
            page.add_script_tag(content=story_js)
            page.add_script_tag(content=js)

            # The story opens first: readable text, and each decision compared across runs.
            page.locator(".story-decision").first.wait_for()
            assert page.locator("#chapterTitle").inner_text().startswith("01")
            # At most six Runs are shown; each holds a distinct shade slot.
            assert page.locator(".run-chip").count() == 6
            assert "LLM: Become Human" in page.title()
            assert page.evaluate("document.body.dataset.character") == "none"
            shades = page.locator(".run-chip").evaluate_all(
                "els => els.map(e => e.style.getPropertyValue('--run-color'))"
            )
            assert len(set(shades)) == 6 and all("--shade-" in s for s in shades)
            first_card = page.locator(".story-decision").first
            assert "Decision 1 of" in first_card.text_content()
            assert page.locator(".story-why").first.inner_text().strip()
            assert (
                page.locator(".story-line, .story-narration, .story-clue").count() > 0
            )
            assert (
                page.locator("#decisionStrip button").count()
                == page.locator(".story-decision").count()
            )
            mark = page.locator(".story-mark").first
            mark.click()
            assert (
                not page.locator(".story-other-why:not(.is-hidden)").first.inner_text()
                == ""
            )
            assert page.locator("#storyMode").get_attribute("aria-label")
            page.locator("#storyMode").click()
            page.wait_for_function(
                "document.querySelector('#storyMode').getAttribute('aria-pressed') === 'true'"
            )
            assert page.locator(".story-decision").count() > 0

            # Clicking a Moment in the Story opens it on the Flowchart, and back.
            assert "Show on flowchart" not in page.locator("#storyContent").inner_text()
            card = page.locator(".story-decision").first
            moment = card.get_attribute("data-moment")
            card.locator("h3").click()
            page.locator(".flow-node.selected").wait_for()
            assert (
                page.locator(".flow-node.selected").get_attribute("data-moment")
                == moment
            )
            assert page.locator("#storyView").is_hidden()
            assert "Read this moment" not in page.locator("#drawerContent").inner_text()
            scene = page.locator(".flow-node.kind-scene.visited").nth(1)
            scene_moment = scene.get_attribute("data-moment")
            scene.locator(".node-label").click()
            page.locator(".story-flash").wait_for()
            assert page.locator("#viewerWrap").is_hidden()
            assert (
                page.locator(".story-flash").first.get_attribute("data-moment")
                == scene_moment
            )
            page.evaluate(
                "scrollToMoment({index: Number.MAX_SAFE_INTEGER})"
            )  # a chapter exit has no text
            assert page.locator(".story-flash").count() >= 1
            page.locator("#viewFlow").click()
            page.locator(".flow-node").first.wait_for()
            # A seventh Run is refused with a notice.
            page.locator("#pickerToggle").click()
            page.locator(".picker-run:not(:has(input:checked))").first.click()
            page.wait_for_function(
                "document.querySelector('#toast').classList.contains('visible')"
            )
            assert page.locator(".run-chip").count() == 6
            page.locator("#pickerToggle").click()
            kept_shade = page.locator(".run-chip").first.evaluate(
                "e => e.style.getPropertyValue('--run-color')"
            )
            page.locator(".run-chip-remove").last.click()
            page.locator(".run-chip-remove").last.click()
            page.locator(".run-chip-remove").last.click()
            page.locator(".run-chip-remove").last.click()
            page.wait_for_function(
                "document.querySelectorAll('.run-chip').length === 2"
            )
            assert (
                page.locator(".run-chip").first.evaluate(
                    "e => e.style.getPropertyValue('--run-color')"
                )
                == kept_shade
            )
            page.locator(".flow-node").first.wait_for()
            assert page.locator(".flow-node.kind-option").count() == 4
            # Merging must keep every script step, branch and route on the chart.
            coverage = page.evaluate("""() => {
              const chapter = buildChapterGraph(state.chapter);
              const originals = Object.values(state.graph.nodes).filter(n => n.chapter === state.chapter);
              const shown = [...chapter.nodes.values()].flatMap(n => n.members ? n.members.map(m => m.id) : [n.id]);
              return {missing: originals.filter(n => !shown.includes(n.id)).map(n => n.id),
                      duplicated: shown.length - new Set(shown).size,
                      nodes: chapter.nodes.size, steps: chapter.sourceSteps,
                      selfLoops: chapter.edges.filter(e => e.from === e.to).length};
            }""")
            assert (
                coverage["missing"] == []
                and coverage["duplicated"] == 0
                and coverage["selfLoops"] == 0
            )

            # Only straight runs merge: a branch or a second entrance ends a run.
            merged = page.evaluate("""() => {
              const saved = state.graph;
              const scene = (id, next, chapter = 'M') => ({id, type: 'scene', chapter, heading: id, next,
                dialogue: [{speaker: 'S', text: id}], observations: []});
              state.graph = {chapters: ['M', 'N'], nodes: {
                a: scene('a', 'b'), b: scene('b', 'c'), c: scene('c', 'pick'),
                pick: {id: 'pick', type: 'choice', chapter: 'M', options: [{id: 'x', label: 'X', next: 'd'}, {id: 'y', label: 'Y', next: 'e'}]},
                d: scene('d', 'join'), e: scene('e', 'join'), join: scene('join', 'g'), g: scene('g', 'other'),
                other: scene('other', null, 'N'),
                loop1: scene('loop1', 'loop2'), loop2: scene('loop2', 'loop1'),
              }};
              const chapter = buildChapterGraph('M');
              const view = {detail: {events: ['a', 'b', 'c', 'pick', 'd', 'join', 'g', 'other'].map((node_id, index) => ({
                index, node_id, chapter: node_id === 'other' ? 'N' : 'M',
                type: node_id === 'pick' ? 'decision' : 'scene', choice_id: 'x'}))}};
              const path = computePath(view, 'M', chapter);
              state.graph = saved;
              return {runs: [...chapter.nodes.values()].filter(n => n.members).map(n => n.members.map(m => m.id)),
                      edges: chapter.edges.map(e => e.from + '>' + e.to).sort(),
                      headEvents: path.byId.get('a').length,
                      traversed: [...path.traversed].map(t => t.replace('\\u0000', '>')).sort()};
            }""")
            assert sorted(merged["runs"]) == [
                ["a", "b", "c"],
                ["d"],
                ["e"],
                ["join", "g"],
                ["loop1"],
                ["loop2"],
            ]
            assert (
                "a>pick" in merged["edges"]
                and "d>join" in merged["edges"]
                and "e>join" in merged["edges"]
            )
            assert "join>PORTAL::other" in merged["edges"]
            assert "loop1>loop2" in merged["edges"] and "loop2>loop1" in merged["edges"]
            assert (
                merged["headEvents"] == 3
            )  # all three scenes' events belong to the merged node
            assert "a>pick" in merged["traversed"] and "d>join" in merged["traversed"]
            assert "e>join" not in merged["traversed"]
            assert "a>a" not in merged["traversed"]

            node_count = page.locator(".flow-node").count()
            assert node_count == coverage["nodes"]
            assert page.locator(".node-dialogue").count() > 0
            assert page.locator(".flow-node.kind-portal").count() == 1
            assert page.locator(".edge-path.route-overlay").count() > 5
            assert page.locator(".flow-node:not(.visited)").count() >= 0

            # Clicking the selected model's own mark returns ONLY that run's log.
            page.locator(
                ".flow-node.kind-option.visited .node-model-button"
            ).first.click(force=True)
            page.locator(".rationale").wait_for()
            assert "Mock policy" in page.locator(".rationale").first.inner_text()
            assert "Synthetic preview" in page.locator("#drawerContent").text_content()
            page.locator("#closeDrawer").click()

            # "Select" fills up to six compatible runs; swap one for the Grok preview.
            page.locator("#pickerToggle").click()
            page.locator("#selectAllRuns").click()
            page.wait_for_function(
                "document.querySelectorAll('.run-chip').length === 6"
            )
            page.locator("#pickerToggle").click()
            page.locator(".run-chip-remove").last.click()
            page.wait_for_function(
                "document.querySelectorAll('.run-chip').length === 5"
            )
            page.locator("#pickerToggle").click()
            page.locator("#searchRuns").fill("grok")
            page.locator(".picker-run").first.click()
            page.wait_for_function(
                "document.querySelectorAll('.run-chip').length === 6"
            )
            assert page.locator(".legend-runs .legend-line").count() == 6
            assert page.locator(".flow-node").count() == node_count
            assert page.locator(".edge-path.route-overlay").count() > 6
            assert page.locator(".flow-node.visited .node-model-button").count() >= 6
            # Same-hue routes differ by provider line style.
            assert page.locator(".route-overlay.provider-xai").count() > 0
            # Multi-run badges must wrap within the node; labels remain visible.
            assert (
                page.locator(".flow-node.visited .node-label").first.bounding_box()[
                    "height"
                ]
                > 0
            )
            assert (
                page.locator(".flow-node.visited .node-logos").first.evaluate(
                    "el => getComputedStyle(el).flexDirection"
                )
                == "row"
            )
            colors = page.locator(".route-overlay").evaluate_all(
                "els => [...new Set(els.map(e => e.style.stroke))]"
            )
            assert len(colors) >= 6
            assert page.locator(".node-model-button.provider-xai").count() > 0
            page.locator("#searchRuns").fill("")
            page.locator("#pickerToggle").click()  # close the selection panel
            page.locator(
                ".flow-node.kind-option .node-model-button.provider-xai"
            ).first.click(force=True)
            page.locator(".rationale").wait_for()
            assert "Grok preview" in page.locator("#drawerContent").inner_text()
            page.locator("#closeDrawer").click()
            # Removing only one run doesn't change complete graph.
            page.locator(".run-chip-remove").first.click()
            page.wait_for_function(
                "document.querySelectorAll('.run-chip').length === 5"
            )
            assert page.locator(".flow-node").count() == node_count
            page.locator(".chapter-entry").nth(1).click()
            assert "The Search" in page.locator("#chapterTitle").inner_text()
            assert not errors
        finally:
            browser.close()


def test_backdrop_network_without_art(live_dashboard):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = _launch_chromium(p)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.set_default_timeout(4500)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(live_dashboard)
            page.locator(".story-decision").first.wait_for(state="attached")
            canvas = page.locator("#backdropNetwork canvas")
            assert canvas.count() == 1
            # The network is drawn: some pixels are not transparent.
            page.wait_for_function("""() => {
              const c = document.querySelector('#backdropNetwork canvas');
              const data = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
              for (let i = 3; i < data.length; i += 4) if (data[i]) return true;
              return false;
            }""")
            box = canvas.bounding_box()
            assert box["width"] == 1280 and box["height"] == 800
            # No art installed: the manifest is empty and no scene image is shown.
            manifest = page.evaluate("fetch('/api/art/manifest').then(r => r.json())")
            assert manifest == {"scenes": []}
            assert page.locator(".backdrop-art-layer.is-shown").count() == 0
            assert not page.evaluate(
                "document.getElementById('backdrop').classList.contains('has-art')"
            )
            assert not errors
        finally:
            browser.close()


@pytest.fixture
def live_dashboard(tmp_path):
    """The real dashboard on a local port, so pages have an origin (browser storage) and assets load."""
    uvicorn = pytest.importorskip("uvicorn")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # An empty images folder: the title screen must work without any art installed.
    app = create_app(PROJECT / "demo_runs" / "aurora", images_dir=tmp_path)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=5)


def _launch_chromium(p):
    binary = shutil.which("chromium") or shutil.which("chromium-browser")
    if not binary:
        pytest.skip("Chromium executable unavailable")
    return p.chromium.launch(executable_path=binary, args=["--no-sandbox"])


def test_title_screen_sound_and_marker_card(live_dashboard):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = _launch_chromium(p)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.set_default_timeout(4500)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(live_dashboard)

            # The title screen shows on load, without art, and any key dismisses it.
            title = page.locator("#titleScreen")
            title.wait_for()
            assert (
                "LLM" in title.inner_text()
                and "BECOME HUMAN" in title.inner_text().upper()
            )
            assert "PRESS ANY KEY" in title.inner_text().upper()
            assert page.evaluate("document.getElementById('appShell').inert")
            page.wait_for_timeout(400)
            page.keyboard.press("Enter")
            title.wait_for(state="detached")
            assert not page.evaluate("document.getElementById('appShell').inert")
            # That key press unlocked sound.
            assert page.evaluate("uiSound.isUnlocked()")
            assert page.evaluate("uiSound.play('click')") is True

            # Mute persists across a reload.
            toggle = page.locator(".sound-toggle")
            assert toggle.get_attribute("aria-pressed") == "false"
            toggle.click()
            assert toggle.get_attribute("aria-label") == "Unmute sound"
            page.reload()
            page.locator("#titleScreen").wait_for()
            assert page.locator(".sound-toggle").get_attribute("aria-pressed") == "true"
            assert page.evaluate("uiSound.isMuted()")
            page.wait_for_timeout(400)
            page.mouse.click(700, 450)
            page.locator("#titleScreen").wait_for(state="detached")
            assert page.evaluate("uiSound.play('hover')") is False

            # Focusing a decision marker unfolds its rationale; the drawer stays for click.
            page.locator("#viewFlow").click()
            marker = page.locator(
                ".flow-node.kind-option.visited .node-model-button"
            ).first
            marker.wait_for()
            marker.focus()
            card = page.locator("#unfoldCard.is-open")
            card.wait_for()
            assert "CHOSE" in card.inner_text().upper()
            assert page.locator(".unfold-card-why").inner_text().strip()
            assert marker.get_attribute("aria-describedby") == "unfoldCard"
            page.keyboard.press("Escape")
            page.wait_for_function("!document.querySelector('#unfoldCard.is-open')")
            assert not errors
        finally:
            browser.close()
