/* Visitor Runs: "Play your own Run", a form opened from the model picker. Only present when the
 * dashboard runs with --allow-own-runs (the config endpoint answers 404 otherwise).
 *
 * A Visitor Run is private: this browser keeps the ids of the Runs it started in local storage
 * and sends them with the Run listing (window.visitorRunsQuery), so they stay listed after a
 * reload. Start hands the new Run to app.js (window.showStartedRun) to join the Shown Runs.
 * The key is sent to list the provider's models and with Start only; it is never kept in the page.
 *
 * This browser's playing Visitor Runs are listed above the entry, each with its live token counts,
 * its estimate and a Stop button; it knows their ids, so the button shows on no one else's Run.
 * A refused Start (the site is busy, or a Run of this visitor's is already playing) is shown in
 * the form as a notice.
 */
(() => {
  'use strict';
  // The form is built once the config answers, after app.js has run, so app.js's globals
  // (esc, modelName, autoFocus, niceNum, api, runsPath) are there to use.
  const STORAGE_KEY = 'llmbh.visitorRuns';

  function storedIds() {
    try {
      const ids = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      return Array.isArray(ids) ? ids.filter(id => typeof id === 'string') : [];
    } catch (_) { return []; }
  }
  function remember(id) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...new Set([...storedIds(), id])])); } catch (_) { /* private mode */ }
  }
  /* POSTs JSON; the reply, and its error detail should the server refuse. */
  async function postJson(path, body) {
    const res = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    let reply = {};
    try { reply = await res.json(); } catch (_) { /* not JSON */ }
    const detail = typeof reply.detail === 'string' ? reply.detail : `${res.status} ${res.statusText}`;
    return { res, reply, detail };
  }
  window.visitorRunsQuery = () => {
    const ids = storedIds();
    return ids.length ? '?' + ids.map(id => 'visitor_runs=' + encodeURIComponent(id)).join('&') : '';
  };

  let panel = null;

  function build(providers) {
    const entry = document.createElement('div');
    entry.className = 'visitor-run-entry';
    entry.innerHTML = '<button type="button" id="visitorRunOpen">Play your own Run</button>';
    document.getElementById('pickerPanel').append(entry);
    entry.querySelector('button').addEventListener('click', open);
    buildPlaying(entry);

    panel = document.createElement('div');
    panel.className = 'visitor-run-panel is-hidden';
    panel.id = 'visitorRunPanel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-labelledby', 'visitorRunTitle');
    panel.innerHTML = `
      <form class="visitor-run-form" novalidate>
        <div class="visitor-run-head"><h2 id="visitorRunTitle">Play your own Run</h2>
          <button type="button" class="visitor-run-close" aria-label="Close" title="Close">×</button></div>
        <p class="visitor-run-note">Your model plays the whole story under the default goal, on this server.
          Your API key is sent to the server for this Run only and never stored.</p>
        <label>Provider<select id="visitorRunProvider" required>${providers.map(p =>
          `<option value="${esc(p)}">${esc(modelName(p))}</option>`).join('')}</select></label>
        <label>API key<input id="visitorRunKey" type="password" autocomplete="off" spellcheck="false" required></label>
        <label>Model id<input id="visitorRunModel" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="e.g. gpt-4.1-mini" required
          role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="visitorRunModels"></label>
        <p class="visitor-run-models-status" id="visitorRunModelsStatus" aria-live="polite"></p>
        <ul class="visitor-run-models is-hidden" id="visitorRunModels" role="listbox" aria-label="Models"></ul>
        <div class="visitor-run-estimate is-hidden" id="visitorRunEstimate" aria-live="polite"></div>
        <p class="visitor-run-warning" id="visitorRunWarning" hidden>A public Run of this model already exists. Yours will be saved but only you will see it.</p>
        <p class="visitor-run-error" id="visitorRunError" role="alert"></p>
        <div class="visitor-run-actions"><button type="submit" id="visitorRunStart">Start</button></div>
      </form>`;
    document.body.append(panel);
    panel.querySelector('.visitor-run-close').addEventListener('click', close);
    panel.querySelector('form').addEventListener('submit', e => { e.preventDefault(); start(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
    setUpModelList();
    setUpEstimate();
  }

  function open() {
    // The model picker closes; the form takes its place.
    document.getElementById('pickerToggle').getAttribute('aria-expanded') === 'true'
      && document.getElementById('pickerToggle').click();
    panel.classList.remove('is-hidden');
    panel.querySelector('#visitorRunError').textContent = '';
    // After a touch no field focuses by itself, so the keyboard stays down until asked for.
    autoFocus(panel.querySelector('#visitorRunProvider'));
    // A Run of the chosen model may have become public since the form was last open.
    updateEstimate();
  }
  function close() {
    if (!panel || panel.classList.contains('is-hidden')) return;
    panel.classList.add('is-hidden');
    panel.querySelector('#visitorRunKey').value = '';
  }

  async function start() {
    const field = id => panel.querySelector(id);
    const error = field('#visitorRunError'), button = field('#visitorRunStart');
    const body = { provider: field('#visitorRunProvider').value, key: field('#visitorRunKey').value.trim(), model: field('#visitorRunModel').value.trim() };
    if (!body.key || !body.model) { error.textContent = 'Enter your API key and a model id.'; return; }
    error.textContent = '';
    error.classList.remove('is-notice');
    button.disabled = true;
    try {
      const { res, reply, detail } = await postJson('/api/visitor-runs', body);
      if (!res.ok) {
        // Busy and already playing are refusals to read, not failures.
        error.classList.toggle('is-notice', res.status === 409 || res.status === 503);
        throw new Error(detail);
      }
      remember(reply.id);
      close();
      refreshPlaying();
      await window.showStartedRun?.(reply.id);
    } catch (err) {
      error.textContent = err.message;
    } finally {
      button.disabled = false;
    }
  }

  /* ---- The model list ------------------------------------------------------------------
   * Once a key is entered, the server lists the provider's models for it. The model field
   * then filters that list as you type; it stays a free-text field, so a listing that fails
   * (a rejected key, an unreachable provider) never stops you typing a model id. */
  const MAX_LISTED = 60;
  let listedModels = [], listRequest = 0, highlighted = -1;
  const field = id => panel.querySelector(id);

  function setUpModelList() {
    const key = field('#visitorRunKey'), model = field('#visitorRunModel'), list = field('#visitorRunModels');
    let timer = null;
    const soon = delay => { clearTimeout(timer); timer = setTimeout(fetchModels, delay); };
    key.addEventListener('input', () => soon(600));
    key.addEventListener('change', () => soon(0));
    field('#visitorRunProvider').addEventListener('change', () => soon(0));
    model.addEventListener('input', () => { highlighted = -1; showList(); });
    model.addEventListener('focus', showList);
    model.addEventListener('blur', () => setTimeout(hideList, 150));
    model.addEventListener('keydown', moveInList);
    // Keeps the field focused while a model is picked from the list.
    list.addEventListener('pointerdown', e => e.preventDefault());
    list.addEventListener('click', e => {
      const item = e.target.closest('[data-model]');
      if (item) choose(item.dataset.model);
    });
  }

  async function fetchModels() {
    const status = field('#visitorRunModelsStatus'), key = field('#visitorRunKey').value.trim();
    const request = ++listRequest;
    listedModels = [];
    hideList();
    const say = (state, text) => { status.dataset.state = state; status.textContent = text; };
    if (!key) { say('', ''); return; }
    say('loading', 'Listing models…');
    try {
      const { res, reply, detail } = await postJson('/api/visitor-runs/models', { provider: field('#visitorRunProvider').value, key });
      if (request !== listRequest) return;
      if (!res.ok) {
        say(res.status === 401 ? 'rejected' : 'failed', detail);
        return;
      }
      listedModels = Array.isArray(reply.models) ? reply.models : [];
      say('listed', listedModels.length
        ? `${listedModels.length} models listed: type to search, or enter any model id.`
        : 'The provider listed no models. Type a model id.');
      if (document.activeElement === field('#visitorRunModel')) showList();
    } catch (_) {
      if (request === listRequest) say('failed', 'Could not list the models. You can still type a model id.');
    }
  }

  function matches() {
    const query = field('#visitorRunModel').value.trim().toLowerCase();
    return listedModels.filter(id => id.toLowerCase().includes(query)).slice(0, MAX_LISTED);
  }
  function showList() {
    const list = field('#visitorRunModels'), found = matches();
    if (!found.length) { hideList(); return; }
    list.replaceChildren(...found.map((id, i) => {
      const item = document.createElement('li');
      item.id = `visitorRunModelOption${i}`;
      item.setAttribute('role', 'option');
      item.setAttribute('aria-selected', String(i === highlighted));
      item.dataset.model = id;
      item.textContent = id;
      return item;
    }));
    list.classList.remove('is-hidden');
    field('#visitorRunModel').setAttribute('aria-expanded', 'true');
  }
  function hideList() {
    if (!panel) return;
    field('#visitorRunModels').classList.add('is-hidden');
    field('#visitorRunModel').setAttribute('aria-expanded', 'false');
    field('#visitorRunModel').removeAttribute('aria-activedescendant');
  }
  function choose(id) {
    field('#visitorRunModel').value = id;
    hideList();
    updateEstimate();
  }
  function moveInList(e) {
    const open = !field('#visitorRunModels').classList.contains('is-hidden');
    const items = open ? [...field('#visitorRunModels').children] : [];
    if (e.key === 'Escape' && open) { e.stopPropagation(); hideList(); return; }
    if (e.key === 'Enter' && open && items[highlighted]) {
      e.preventDefault();
      choose(items[highlighted].dataset.model);
      return;
    }
    if ((e.key !== 'ArrowDown' && e.key !== 'ArrowUp') || !items.length) return;
    e.preventDefault();
    highlighted = (highlighted + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length;
    items.forEach((item, i) => item.setAttribute('aria-selected', String(i === highlighted)));
    items[highlighted].scrollIntoView({ block: 'nearest' });
    field('#visitorRunModel').setAttribute('aria-activedescendant', items[highlighted].id);
  }

  /* ---- The token estimate and the public-Run warning --------------------------------------
   * Shown once a model id is entered: about how many tokens a Run of the story takes, as an
   * approximation and never a price. A model's first complete Visitor Run is public and any
   * later one private, so the same answer also says whether a public Run of the chosen
   * provider and model id exists; if so, the form warns before Start. */
  let estimateRequest = 0;

  function setUpEstimate() {
    let timer = null;
    const soon = () => { clearTimeout(timer); timer = setTimeout(updateEstimate, 300); };
    field('#visitorRunModel').addEventListener('input', soon);
    field('#visitorRunProvider').addEventListener('change', soon);
  }

  const estimateFor = (provider, model) =>
    fetch(`/api/visitor-runs/estimate?provider=${encodeURIComponent(provider)}&model=${encodeURIComponent(model)}`, { cache: 'no-store' })
      .then(res => (res.ok ? res.json() : Promise.reject(new Error(res.statusText))));

  const tokenCount = n => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n));
  const tokenRange = range => `${tokenCount(range.low)}–${tokenCount(range.high)}`;

  async function updateEstimate() {
    const box = field('#visitorRunEstimate'), model = field('#visitorRunModel').value.trim();
    const warning = field('#visitorRunWarning');
    const request = ++estimateRequest;
    if (!model) { box.classList.add('is-hidden'); box.replaceChildren(); warning.hidden = true; return; }
    try {
      const found = await estimateFor(field('#visitorRunProvider').value, model);
      if (request !== estimateRequest) return;
      warning.hidden = !found.public_run_exists;
      box.innerHTML = `
        <p class="visitor-run-estimate-range">About <strong>${tokenRange(found.input_tokens)}</strong> input tokens
          and <strong>${tokenRange(found.output_tokens)}</strong> output tokens.</p>
        <p class="visitor-run-estimate-note">An approximation from the story's shortest and longest routes, not a quote:
          your provider counts the real tokens.</p>`;
      box.classList.remove('is-hidden');
    } catch (_) {
      if (request === estimateRequest) { box.classList.add('is-hidden'); warning.hidden = true; }
    }
  }

  /* Stop: this browser's playing Visitor Runs, above the entry. */
  const POLL_MS = 4000;
  let playingList = null;

  function buildPlaying(entry) {
    playingList = document.createElement('div');
    playingList.className = 'visitor-run-playing';
    playingList.setAttribute('aria-live', 'polite');
    entry.prepend(playingList);
    playingList.addEventListener('click', e => {
      const button = e.target.closest('[data-stop-run]');
      if (button) stopRun(button);
    });
    document.getElementById('pickerToggle').addEventListener('click', refreshPlaying);
    refreshPlaying();
    setInterval(() => { if (storedIds().length && !document.hidden) refreshPlaying(); }, POLL_MS);
  }

  async function refreshPlaying() {
    if (!playingList) return;
    const ids = new Set(storedIds());
    let runs = [];
    if (ids.size) {
      try {
        runs = ((await api(runsPath())).runs || []).filter(r => ids.has(r.id) && r.status === 'running');
      } catch (_) { return; }
    }
    // Each playing Run's estimate, fetched once, sits next to its live token counts.
    await Promise.all(runs.map(async run => {
      if (playingEstimates.has(run.id)) return;
      try { playingEstimates.set(run.id, await estimateFor(run.provider, run.model)); } catch (_) { /* shown without */ }
    }));
    renderPlaying(runs);
  }

  const playingEstimates = new Map();
  function liveTokens(run) {
    const found = playingEstimates.get(run.id);
    return `<p class="visitor-run-live-run">
      <span class="visitor-run-live-count" data-kind="input">${niceNum(run.total_input_tokens)}</span> input and
      <span class="visitor-run-live-count" data-kind="output">${niceNum(run.total_output_tokens)}</span> output tokens so far${found
        ? `<small>Estimate: about ${tokenRange(found.input_tokens)} input and ${tokenRange(found.output_tokens)} output</small>` : ''}</p>`;
  }

  function renderPlaying(runs) {
    const stopping = new Set([...playingList.querySelectorAll('[data-stop-run]:disabled')].map(b => b.dataset.stopRun));
    playingList.innerHTML = runs.map(run => `<div class="visitor-run-playing-run">
      <span><strong>${esc(run.model)}</strong> <small>your Run, playing</small></span>
      <button type="button" data-stop-run="${esc(run.id)}" ${stopping.has(run.id) ? 'disabled' : ''}
        title="Stop after the current model call; the Run is kept as partial">${stopping.has(run.id) ? 'Stopping…' : 'Stop'}</button></div>
      ${liveTokens(run)}`).join('');
  }

  async function stopRun(button) {
    button.disabled = true;
    button.textContent = 'Stopping…';
    try {
      await fetch(`/api/visitor-runs/${encodeURIComponent(button.dataset.stopRun)}/stop`, { method: 'POST' });
    } catch (_) { /* the next refresh shows where it stands */ }
    refreshPlaying();
  }

  fetch('/api/visitor-runs/config', { cache: 'no-store' })
    .then(res => (res.ok ? res.json() : null))
    .then(config => { if (config) build(config.providers || []); })
    .catch(() => { /* Visitor Runs off or unreachable: no form */ });
})();
