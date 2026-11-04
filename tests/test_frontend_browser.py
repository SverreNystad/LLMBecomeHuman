"""Optional end-to-end UI contract, using in-process API responses, no network.

Install Playwright and Chromium separately to run this test in local development.
Other tests remain runnable without a browser.
"""
from __future__ import annotations

import shutil
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from detroit_benchmark.dashboard import create_app

PROJECT = Path(__file__).resolve().parents[1]
ASSETS = PROJECT / 'detroit_benchmark' / 'dashboard_assets'


def test_chapter_flowchart_browser_interactions():
    playwright = pytest.importorskip('playwright.sync_api')
    binary = shutil.which('chromium') or shutil.which('chromium-browser')
    if not binary:
        pytest.skip('Chromium executable unavailable')
    c = TestClient(create_app(PROJECT / 'demo_runs'))
    runs = c.get('/api/runs').json()['runs']
    mock_responses = {'/api/runs': {'runs': runs}}
    for r in runs:
        run_id = r['id']
        detail = c.get(f'/api/runs/{run_id}').json()
        mock_responses[f'/api/runs/{run_id}'] = detail
        mock_responses[f'/api/runs/{run_id}/flowchart'] = c.get(f'/api/runs/{run_id}/flowchart').json()
        for ev in detail['events']:
            mock_responses[f'/api/runs/{run_id}/events/{ev["index"]}'] = c.get(
                f'/api/runs/{run_id}/events/{ev["index"]}'
            ).json()

    html = (ASSETS / 'index.html').read_text(encoding='utf-8')
    css = (ASSETS / 'styles.css').read_text(encoding='utf-8')
    js = (ASSETS / 'app.js').read_text(encoding='utf-8')
    html = html.replace('<link rel="stylesheet" href="/assets/styles.css">', f'<style>{css}</style>')
    html = html.replace('<script src="/assets/app.js" defer></script>', '')

    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=binary, args=['--no-sandbox'])
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 900})
            page.set_default_timeout(4500)
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto('about:blank')
            page.set_content(html)
            page.evaluate('''data => {
              window.__responses = data;
              window.fetch = async url => ({
                ok: !!window.__responses[url], status: window.__responses[url] ? 200 : 404,
                json: async () => window.__responses[url] ?? {detail:'Mock API route missing'}
              });
            }''', mock_responses)
            page.add_script_tag(content=js)
            page.locator('.flow-node').first.wait_for()
            assert page.locator('#chapterTitle').inner_text().startswith('01')
            assert page.locator('#selectedRunCount').inner_text() == '6'
            assert page.locator('.flow-node.kind-option').count() == 4
            assert page.locator('.flow-node').count() == 12  # complete chapter graph + portal
            assert page.locator('.flow-node.kind-portal').count() == 1
            assert 'ALWAYS ON' in page.locator('.full-paths-indicator').inner_text()
            assert page.locator('.edge-path.route-overlay').count() > 10
            assert page.locator('.flow-node:not(.visited)').count() >= 0

            # Clicking the selected model's own mark returns ONLY that run's log.
            page.locator('.flow-node.kind-option.visited .node-model-button').first.click(force=True)
            page.locator('.rationale').wait_for()
            assert 'Mock policy' in page.locator('.rationale').first.inner_text()
            assert 'ACTION SELECTED' in page.locator('#drawerContent').inner_text()
            assert 'SYNTHETIC PREVIEW' in page.locator('#drawerContent').inner_text()
            page.locator('#closeDrawer').click()

            # Select all 10 recorded experiments in the same graph, including
            # multiple mock identities from OpenAI/Claude/Grok/other groups.
            page.locator('#pickerToggle').click()
            page.locator('#selectAllRuns').click()
            page.wait_for_function("document.querySelector('#selectedRunCount')?.textContent === '10'")
            assert page.locator('.run-chip').count() == 10
            assert page.locator('.legend-runs .legend-line').count() == 10
            assert page.locator('.flow-node').count() == 12
            assert page.locator('.edge-path.route-overlay').count() > 20
            assert page.locator('.flow-node.visited .node-model-button').count() >= 10
            # Multi-run badges must wrap within the node; labels remain visible.
            assert page.locator('.flow-node.visited .node-label').first.bounding_box()['height'] > 0
            assert page.locator('.flow-node.visited .node-logos').first.evaluate('el => getComputedStyle(el).flexDirection') == 'row'
            colors = page.locator('.route-overlay').evaluate_all('els => [...new Set(els.map(e => e.style.stroke))]')
            assert len(colors) >= 6
            assert page.locator('.node-model-button.provider-xai').count() > 0
            page.locator('#pickerToggle').click()  # close the selection panel
            page.locator('.flow-node.kind-option .node-model-button.provider-xai').first.click(force=True)
            page.locator('.rationale').wait_for()
            assert 'Grok preview' in page.locator('#drawerContent').inner_text()
            page.locator('#closeDrawer').click()
            # Removing only one run doesn't change complete graph.
            page.locator('.run-chip-remove').first.click()
            page.wait_for_function("document.querySelector('#selectedRunCount')?.textContent === '9'")
            assert page.locator('.flow-node').count() == 12
            page.locator('.chapter-entry').nth(1).click()
            assert 'The Search' in page.locator('#chapterTitle').inner_text()
            assert not errors
        finally:
            browser.close()
