/* Visitor Runs: "Play your own Run", a form opened from the model picker. Only present when the
 * dashboard runs with --allow-own-runs (the config endpoint answers 404 otherwise).
 *
 * A Visitor Run is private: this browser keeps the ids of the Runs it started in local storage
 * and sends them with the Run listing (window.visitorRunsQuery), so they stay listed after a
 * reload. Start hands the new Run to app.js (window.showStartedRun) to join the Shown Runs.
 * The key is sent with Start only; it is never kept in the page.
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
        <label>Model id<input id="ownRunModel" type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="e.g. gpt-4.1-mini" required></label>
        <p class="own-run-error" id="ownRunError" role="alert"></p>
        <div class="own-run-actions"><button type="submit" id="ownRunStart">Start</button></div>
      </form>`;
    document.body.append(panel);
    panel.querySelector('.own-run-close').addEventListener('click', close);
    panel.querySelector('form').addEventListener('submit', e => { e.preventDefault(); start(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
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
    button.disabled = true;
    try {
      const res = await fetch('/api/visitor-runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      let reply = {};
      try { reply = await res.json(); } catch (_) { /* not JSON */ }
      if (!res.ok) throw new Error(typeof reply.detail === 'string' ? reply.detail : `${res.status} ${res.statusText}`);
      remember(reply.id);
      close();
      await window.showStartedRun?.(reply.id);
    } catch (err) {
      error.textContent = err.message;
    } finally {
      button.disabled = false;
    }
  }

  fetch('/api/visitor-runs/config', { cache: 'no-store' })
    .then(res => (res.ok ? res.json() : null))
    .then(config => { if (config) build(config.providers || []); })
    .catch(() => { /* Visitor Runs off or unreachable: no form */ });
})();
