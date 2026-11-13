/* Decision marker card: hovering or focusing a model's marker on the Flowchart unfolds a
 * card with what it chose and why. The card stays open while the pointer is on it, and
 * clicking the card (or the marker) opens the full record in the drawer.
 *
 * Reads the Run events app.js already holds (state.rendered paths), so it adds no requests.
 */
(() => {
  'use strict';
  const GAP = 14;
  const HIDE_DELAY_MS = 220; // long enough to cross the gap from the marker to the card
  let card = null, current = null, hideTimer = null;


  function ensureCard() {
    if (card) return card;
    card = document.createElement('div');
    card.className = 'unfold-card';
    card.id = 'unfoldCard';
    card.setAttribute('role', 'button');
    card.tabIndex = -1;
    card.innerHTML = '<span class="unfold-card-line" aria-hidden="true"></span><div class="unfold-card-body"></div>'
      + '<span class="unfold-card-corner tl" aria-hidden="true"></span><span class="unfold-card-corner br" aria-hidden="true"></span>';
    card.addEventListener('pointerenter', () => clearTimeout(hideTimer));
    card.addEventListener('pointerleave', () => hide());
    card.addEventListener('click', () => {
      const button = current;
      if (!button) return;
      const nodeId = button.closest('.flow-node')?.dataset.nodeId, runId = button.dataset.runId;
      hide(true);
      window.uiSound?.play('click');
      if (nodeId && runId && typeof inspect === 'function') inspect(nodeId, runId);
    });
    document.body.appendChild(card);
    return card;
  }

  /* What a marker stands for: one Run's latest event at one Flowchart node. */
  function markerMoment(button) {
    const nodeId = button.closest('.flow-node')?.dataset.nodeId, runId = button.dataset.runId;
    if (!nodeId || !runId || typeof state === 'undefined') return null;
    const entry = state.rendered?.paths?.find(p => p.run.id === runId);
    const events = entry?.path?.byId?.get(nodeId) || [];
    const decision = events.findLast?.(e => e.type === 'decision');
    return {run: entry?.run, decision, color: button.style.getPropertyValue('--badge-color')};
  }

  function cardMarkup({run, decision}) {
    const logo = run && typeof modelIcon === 'function' ? `<span class="unfold-card-logo">${modelIcon(providerOf(run))}</span>` : '';
    const head = `<p class="unfold-card-model">${logo}<span>${esc(run?.model || 'Unknown model')}</span></p>`;
    if (!decision) return `${head}<p class="unfold-card-why">Passed through this moment.</p>`;
    const chosen = decision.label || decision.available_choices?.find(o => o.id === decision.choice_id)?.label || decision.choice_id || 'Not recorded';
    return `${head}<p class="unfold-card-choice"><small>Chose</small>${esc(chosen)}</p>
      <p class="unfold-card-why">${esc(decision.rationale || 'No reason recorded.')}</p>`;
  }

  function place(button) {
    const box = button.getBoundingClientRect(), width = card.offsetWidth, height = card.offsetHeight;
    const roomRight = window.innerWidth - box.right - GAP;
    const side = roomRight >= width + 8 || box.left - GAP < width ? 'right' : 'left';
    const left = side === 'right' ? box.right + GAP : box.left - GAP - width;
    const top = Math.min(Math.max(8, box.top + box.height / 2 - 18), window.innerHeight - height - 8);
    card.dataset.side = side;
    card.style.left = `${Math.max(8, left)}px`;
    card.style.top = `${top}px`;
  }

  function open(button) {
    clearTimeout(hideTimer);
    if (current === button) return;
    const moment = markerMoment(button);
    if (!moment) return;
    hide(true);
    ensureCard();
    // The card replaces the native tooltip; the aria-label still names the marker.
    if (button.title) { button.dataset.unfoldTitle = button.title; button.removeAttribute('title'); }
    card.querySelector('.unfold-card-body').innerHTML = cardMarkup(moment);
    card.style.setProperty('--card-color', moment.color || 'var(--accent)');
    card.classList.remove('is-open');
    place(button);
    button.setAttribute('aria-describedby', card.id);
    current = button;
    void card.offsetWidth; // restart the unfold
    card.classList.add('is-open');
    window.uiSound?.play('hover');
  }

  function hide(now = false) {
    clearTimeout(hideTimer);
    const close = () => {
      card?.classList.remove('is-open');
      current?.removeAttribute('aria-describedby');
      current = null;
    };
    if (now) close(); else hideTimer = setTimeout(close, HIDE_DELAY_MS);
  }

  const marker = event => event.target.closest?.('.node-model-button');
  document.addEventListener('pointerover', event => {
    const button = marker(event);
    if (button && event.pointerType !== 'touch') open(button);
  });
  document.addEventListener('pointerout', event => {
    const button = marker(event);
    if (button && !button.contains(event.relatedTarget)) hide();
  });
  document.addEventListener('focusin', event => {
    const button = marker(event);
    // A tap also focuses the marker; on touch the click decides (app.js), not the focus.
    if (button && window.lastPointerWasTouch?.()) return;
    if (button) open(button); else if (current) hide();
  });
  document.addEventListener('focusout', event => { if (marker(event)) hide(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && current) hide(true); });
  // Panning, zooming or clicking elsewhere moves the marker out from under the card.
  for (const type of ['pointerdown', 'wheel']) {
    document.addEventListener(type, event => {
      if (current && !card?.contains(event.target) && !current.contains(event.target)) hide(true);
    }, {capture: true, passive: true});
  }
  // Touch screens open the card with a first tap (app.js); a second tap opens the details.
  window.unfoldCard = {open, isOpenFor: button => current === button && card?.classList.contains('is-open')};

})();
