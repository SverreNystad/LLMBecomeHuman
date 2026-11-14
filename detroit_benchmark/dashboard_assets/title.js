/* Title screen: "LLM Become Human", shown on every load until any key, click or tap.
 *
 * Loaded in <head> (not deferred) so the dashboard is hidden before its first paint.
 * Dismissing it is the user gesture that unlocks sound (see sound.js).
 * Uses the local title art when installed, otherwise the LED ring over a dark ground.
 */
(() => {
  'use strict';
  const root = document.documentElement;
  root.classList.add('title-on');
  const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  // Long enough that a key held from the previous page doesn't dismiss the screen at once.
  const ARMED_AFTER_MS = 250;
  const FADE_MS = 1100;
  const MODIFIERS = new Set(['Shift', 'Control', 'Alt', 'Meta', 'AltGraph', 'CapsLock', 'Fn']);

  function build() {
    const screen = document.createElement('div');
    screen.className = 'title-screen';
    screen.id = 'titleScreen';
    screen.setAttribute('role', 'dialog');
    screen.setAttribute('aria-modal', 'true');
    screen.setAttribute('aria-label', 'LLM Become Human. Press any key to start.');
    screen.tabIndex = -1;
    screen.innerHTML = `
      <div class="title-art" aria-hidden="true"></div>
      <div class="title-veil" aria-hidden="true"></div>
      <div class="title-lockup">
        <svg class="led-ring title-ring" viewBox="0 0 40 40" aria-hidden="true">
          <circle class="led-ring-glow" cx="20" cy="20" r="13"/>
          <circle class="led-ring-light" cx="20" cy="20" r="13"/>
          <circle class="led-ring-core" cx="20" cy="20" r="7.5"/>
        </svg>
        <h1 class="title-name"><span class="title-llm" data-text="LLM">LLM</span><span class="title-become">Become Human</span></h1>
      </div>
      <p class="title-prompt">Press any key</p>`;
    return screen;
  }

  function loadArt(screen) {
    const art = new Image();
    art.onload = () => {
      screen.querySelector('.title-art').style.backgroundImage = `url("${art.src}")`;
      screen.classList.add('has-art');
    };
    art.src = '/api/art/title';
  }

  function show() {
    const screen = build();
    const shell = document.getElementById('appShell');
    document.body.appendChild(screen);
    shell?.setAttribute('inert', '');
    loadArt(screen);
    requestAnimationFrame(() => screen.classList.add('is-shown'));
    screen.focus({preventScroll: true});
    const shownAt = performance.now();

    function dismiss(event) {
      if (performance.now() - shownAt < ARMED_AFTER_MS) return;
      // Any key dismisses, a lone Shift or Ctrl included; only browser shortcuts
      // (Ctrl+R, Alt+Tab, …) pass through to the browser instead.
      if (event.type === 'keydown' && !MODIFIERS.has(event.key) && (event.ctrlKey || event.metaKey || event.altKey)) return;
      // The dismissing gesture belongs to the title screen; the dashboard must not also act on it.
      event.preventDefault();
      event.stopImmediatePropagation();
      window.removeEventListener('keydown', dismiss, true);
      screen.removeEventListener('pointerdown', dismiss);
      window.uiSound?.unlock();
      window.uiSound?.play('switch');
      shell?.removeAttribute('inert');
      root.classList.remove('title-on');
      screen.classList.add('is-leaving');
      document.dispatchEvent(new CustomEvent('titledismissed'));
      setTimeout(() => screen.remove(), reducedMotion() ? 0 : FADE_MS);
    }
    window.addEventListener('keydown', dismiss, true);
    screen.addEventListener('pointerdown', dismiss);
    // Swallow the click that follows the dismissing press, so it can't land on the dashboard.
    screen.addEventListener('click', event => event.stopPropagation());
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', show);
  else show();
})();
