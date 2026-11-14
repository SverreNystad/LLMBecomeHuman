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
  const STORAGE_KEY = 'llmbh.visitorRuns';
  const PROVIDER_NAMES = {
    openai: 'OpenAI', anthropic: 'Anthropic', google: 'Google', xai: 'xAI',
    deepseek: 'DeepSeek', mistral: 'Mistral', openrouter: 'OpenRouter',
  };

  function storedIds() {
    try {
      const ids = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      return Array.isArray(ids) ? ids.filter(id => typeof id === 'string') : [];
    } catch (_) { return []; }
  }
  function remember(id) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...new Set([...storedIds(), id])])); } catch (_) { /* private mode */ }
  }
  window.visitorRunsQuery = () => {
    const ids = storedIds();
    return ids.length ? '?' + ids.map(id => 'visitor_runs=' + encodeURIComponent(id)).join('&') : '';
  };

  let panel = null;

  function build(providers) {
    const entry = document.createElement('div');
    entry.className = 'own-run-entry';
    entry.innerHTML = '<button type="button" id="ownRunOpen">Play your own Run</button>';
    document.getElementById('pickerPanel').append(entry);
    entry.querySelector('button').addEventListener('click', open);
    buildPlaying(entry);

    panel = document.createElement('div');
    panel.className = 'own-run-panel is-hidden';
    panel.id = 'ownRunPanel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-labelledby', 'ownRunTitle');
    panel.innerHTML = `
      <form class="own-run-form" novalidate>
        <div class="own-run-head"><h2 id="ownRunTitle">Play your own Run</h2>
          <button type="button" class="own-run-close" aria-label="Close" title="Close">×</button></div>
        <p class="own-run-note">Your model plays the whole story under the default goal, on this server.
          Your API key is sent to the server for this Run only and never stored.</p>
        <label>Provider<select id="ownRunProvider" required>${providers.map(p =>
          `<option value="${p}">${PROVIDER_NAMES[p] || p}</option>`).join('')}</select></label>
        <label>API key<input id="ownRunKey" type="password" autocomplete="off" spellcheck="false" required></label>
        <label>Model id<input id="ownRunModel" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="e.g. gpt-4.1-mini" required
          role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="ownRunModels"></label>
        <p class="own-run-models-status" id="ownRunModelsStatus" aria-live="polite"></p>
        <ul class="own-run-models is-hidden" id="ownRunModels" role="listbox" aria-label="Models"></ul>
        <div class="own-run-estimate is-hidden" id="ownRunEstimate" aria-live="polite"></div>
        <p class="own-run-error" id="ownRunError" role="alert"></p>
        <div class="own-run-actions"><button type="submit" id="ownRunStart">Start</button></div>
      </form>`;
    document.body.append(panel);
    panel.querySelector('.own-run-close').addEventListener('click', close);
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
    panel.querySelector('#ownRunError').textContent = '';
    // On a phone no field focuses by itself, so the keyboard stays down until asked for.
    if (!window.isPhoneLayout?.()) panel.querySelector('#ownRunProvider').focus();
  }
  function close() {
    if (!panel || panel.classList.contains('is-hidden')) return;
    panel.classList.add('is-hidden');
    panel.querySelector('#ownRunKey').value = '';
  }

  async function start() {
    const field = id => panel.querySelector(id);
    const error = field('#ownRunError'), button = field('#ownRunStart');
    const body = { provider: field('#ownRunProvider').value, key: field('#ownRunKey').value.trim(), model: field('#ownRunModel').value.trim() };
    if (!body.key || !body.model) { error.textContent = 'Enter your API key and a model id.'; return; }
    error.textContent = '';
    error.classList.remove('is-notice');
    button.disabled = true;
    try {
      const res = await fetch('/api/visitor-runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      let reply = {};
      try { reply = await res.json(); } catch (_) { /* not JSON */ }
      if (!res.ok) {
        // Busy and already playing are refusals to read, not failures.
        error.classList.toggle('is-notice', res.status === 409 || res.status === 503);
        throw new Error(typeof reply.detail === 'string' ? reply.detail : `${res.status} ${res.statusText}`);
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

  /* ---- The model list (#72) ------------------------------------------------------------
   * Once a key is entered, the server lists the provider's models for it. The model field
   * then filters that list as you type; it stays a free-text field, so a listing that fails
   * (a rejected key, an unreachable provider) never stops you typing a model id. */
  const MAX_LISTED = 60;
  let listedModels = [], listRequest = 0, highlighted = -1;
  const field = id => panel.querySelector(id);

  function setUpModelList() {
    const key = field('#ownRunKey'), model = field('#ownRunModel'), list = field('#ownRunModels');
    let timer = null;
    const soon = delay => { clearTimeout(timer); timer = setTimeout(fetchModels, delay); };
    key.addEventListener('input', () => soon(600));
    key.addEventListener('change', () => soon(0));
    field('#ownRunProvider').addEventListener('change', () => soon(0));
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
    const status = field('#ownRunModelsStatus'), key = field('#ownRunKey').value.trim();
    const request = ++listRequest;
    listedModels = [];
    hideList();
    const say = (state, text) => { status.dataset.state = state; status.textContent = text; };
    if (!key) { say('', ''); return; }
    say('loading', 'Listing models…');
    try {
      const res = await fetch('/api/visitor-runs/models', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: field('#ownRunProvider').value, key }),
      });
      let reply = {};
      try { reply = await res.json(); } catch (_) { /* not JSON */ }
      if (request !== listRequest) return;
      if (!res.ok) {
        const detail = typeof reply.detail === 'string' ? reply.detail : `${res.status} ${res.statusText}`;
        say(res.status === 401 ? 'rejected' : 'failed', detail);
        return;
      }
      listedModels = Array.isArray(reply.models) ? reply.models : [];
      say('listed', listedModels.length
        ? `${listedModels.length} models listed: type to search, or enter any model id.`
        : 'The provider listed no models. Type a model id.');
      if (document.activeElement === field('#ownRunModel')) showList();
    } catch (_) {
      if (request === listRequest) say('failed', 'Could not list the models. You can still type a model id.');
    }
  }

  function matches() {
    const query = field('#ownRunModel').value.trim().toLowerCase();
    return listedModels.filter(id => id.toLowerCase().includes(query)).slice(0, MAX_LISTED);
  }
  function showList() {
    const list = field('#ownRunModels'), found = matches();
    if (!found.length) { hideList(); return; }
    list.replaceChildren(...found.map((id, i) => {
      const item = document.createElement('li');
      item.id = `ownRunModelOption${i}`;
      item.setAttribute('role', 'option');
      item.setAttribute('aria-selected', String(i === highlighted));
      item.dataset.model = id;
      item.textContent = id;
      return item;
    }));
    list.classList.remove('is-hidden');
    field('#ownRunModel').setAttribute('aria-expanded', 'true');
  }
  function hideList() {
    if (!panel) return;
    field('#ownRunModels').classList.add('is-hidden');
    field('#ownRunModel').setAttribute('aria-expanded', 'false');
    field('#ownRunModel').removeAttribute('aria-activedescendant');
  }
  function choose(id) {
    field('#ownRunModel').value = id;
    hideList();
    updateEstimate();
  }
  function moveInList(e) {
    const open = !field('#ownRunModels').classList.contains('is-hidden');
    const items = open ? [...field('#ownRunModels').children] : [];
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
    field('#ownRunModel').setAttribute('aria-activedescendant', items[highlighted].id);
  }

  /* ---- The token estimate (#73) ---------------------------------------------------------
   * Shown once a model id is entered: about how many tokens a Run of the story takes, as an
   * approximation and never a price. (The public-Run warning is watchPublicRun's, below.) */
  let estimateRequest = 0;

  function setUpEstimate() {
    let timer = null;
    const soon = () => { clearTimeout(timer); timer = setTimeout(updateEstimate, 300); };
    field('#ownRunModel').addEventListener('input', soon);
    field('#ownRunProvider').addEventListener('change', soon);
  }

  const estimateFor = (provider, model) =>
    fetch(`/api/visitor-runs/estimate?provider=${encodeURIComponent(provider)}&model=${encodeURIComponent(model)}`, { cache: 'no-store' })
      .then(res => (res.ok ? res.json() : Promise.reject(new Error(res.statusText))));

  const tokenCount = n => (n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${Math.round(n / 1e3)}k` : String(n));
  const tokenRange = range => `${tokenCount(range.low)}–${tokenCount(range.high)}`;

  async function updateEstimate() {
    const box = field('#ownRunEstimate'), model = field('#ownRunModel').value.trim();
    const request = ++estimateRequest;
    if (!model) { box.classList.add('is-hidden'); box.replaceChildren(); return; }
    try {
      const found = await estimateFor(field('#ownRunProvider').value, model);
      if (request !== estimateRequest) return;
      box.innerHTML = `
        <p class="own-run-estimate-range">About <strong>${tokenRange(found.input_tokens)}</strong> input tokens
          and <strong>${tokenRange(found.output_tokens)}</strong> output tokens.</p>
        <p class="own-run-estimate-note">An approximation from the story's shortest and longest routes, not a quote:
          your provider counts the real tokens.</p>`;
      box.classList.remove('is-hidden');
    } catch (_) {
      if (request === estimateRequest) box.classList.add('is-hidden');
    }
  }

  /* Publication (#76): a model's first complete Visitor Run is public; any later one is private.
   * Before Start, the form warns when a public Run of the chosen provider and model id exists. */
  function watchPublicRun() {
    const warning = document.createElement('p');
    warning.className = 'own-run-warning';
    warning.id = 'ownRunWarning';
    warning.hidden = true;
    warning.textContent = 'A public Run of this model already exists. Yours will be saved but only you will see it.';
    panel.querySelector('#ownRunError').before(warning);
    let timer = 0, asked = 0;
    const check = async () => {
      const provider = panel.querySelector('#ownRunProvider').value;
      const model = panel.querySelector('#ownRunModel').value.trim();
      const ask = ++asked;
      if (!model) { warning.hidden = true; return; }
      try {
        const res = await fetch('/api/visitor-runs/public?' + new URLSearchParams({ provider, model }), { cache: 'no-store' });
        const reply = res.ok ? await res.json() : {};
        if (ask === asked) warning.hidden = !reply.public_run_exists;
      } catch (_) { if (ask === asked) warning.hidden = true; }
    };
    const soon = () => { clearTimeout(timer); timer = setTimeout(check, 250); };
    const form = panel.querySelector('form');
    form.addEventListener('input', e => { if (e.target.id !== 'ownRunKey') soon(); });
    form.addEventListener('change', e => { if (e.target.id !== 'ownRunKey') soon(); });
    document.getElementById('ownRunOpen').addEventListener('click', soon);
  }

  /* Stop (#74): this browser's playing Visitor Runs, above the entry. */
  const POLL_MS = 4000;
  let playingList = null;

  function buildPlaying(entry) {
    playingList = document.createElement('div');
    playingList.className = 'own-run-playing';
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
        const res = await fetch('/api/runs' + window.visitorRunsQuery(), { cache: 'no-store' });
        if (!res.ok) return;
        runs = ((await res.json()).runs || []).filter(r => ids.has(r.id) && r.status === 'running');
      } catch (_) { return; }
    }
    // Each playing Run's estimate, fetched once, sits next to its live token counts (#73).
    await Promise.all(runs.map(async run => {
      if (playingEstimates.has(run.id)) return;
      try { playingEstimates.set(run.id, await estimateFor(run.provider, run.model)); } catch (_) { /* shown without */ }
    }));
    renderPlaying(runs);
  }

  const playingEstimates = new Map();
  const tokensSoFar = n => Number(n || 0).toLocaleString('en-US');
  function liveTokens(run) {
    const found = playingEstimates.get(run.id);
    return `<p class="own-run-live-run">
      <span class="own-run-live-count" data-kind="input">${tokensSoFar(run.total_input_tokens)}</span> input and
      <span class="own-run-live-count" data-kind="output">${tokensSoFar(run.total_output_tokens)}</span> output tokens so far${found
        ? `<small>Estimate: about ${tokenRange(found.input_tokens)} input and ${tokenRange(found.output_tokens)} output</small>` : ''}</p>`;
  }

  const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  function renderPlaying(runs) {
    const stopping = new Set([...playingList.querySelectorAll('[data-stop-run]:disabled')].map(b => b.dataset.stopRun));
    playingList.innerHTML = runs.map(run => `<div class="own-run-playing-run">
      <span><strong>${escapeHtml(run.model)}</strong> <small>your Run, playing</small></span>
      <button type="button" data-stop-run="${escapeHtml(run.id)}" ${stopping.has(run.id) ? 'disabled' : ''}
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
    .then(config => { if (config) { build(config.providers || []); watchPublicRun(); } })
    .catch(() => { /* Visitor Runs off or unreachable: no form */ });
})();
