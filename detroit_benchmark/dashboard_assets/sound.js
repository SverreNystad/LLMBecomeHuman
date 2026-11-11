/* UI sound: short, quiet cues synthesized with WebAudio (no audio files).
 *
 * Browsers only allow audio after a user gesture, so nothing sounds until unlock() runs
 * inside one (the title screen's dismissal, or any first key/pointer press).
 * Others can call window.uiSound.play('hover' | 'click' | 'switch').
 */
(() => {
  'use strict';
  const MUTE_KEY = 'llmbh.muted';
  const MASTER_VOLUME = 0.5;
  // Hover ticks follow the pointer, so they are rate-limited to stay a texture, not a rattle.
  const HOVER_GAP_MS = 70;
  // Elements whose hover gives a tick and whose press gives a confirm.
  const TICK_TARGETS = 'button:not(:disabled), [role="button"]:not(.flow-node), .flow-node.kind-option, .story-options li, select';
  const CLICK_TARGETS = 'button:not(:disabled), [role="button"], .story-options li, summary';

  let ctx = null, master = null, lastHover = 0, pointerHeld = false;

  function readMuted() {
    try { return localStorage.getItem(MUTE_KEY) === '1'; } catch (_) { return false; }
  }
  function writeMuted(value) {
    try { localStorage.setItem(MUTE_KEY, value ? '1' : '0'); } catch (_) { /* storage blocked: mute lasts this visit */ }
  }
  let muted = readMuted();

  function unlock() {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) return false;
    try {
      if (!ctx) {
        ctx = new Ctor();
        master = ctx.createGain();
        master.gain.value = MASTER_VOLUME;
        master.connect(ctx.destination);
      }
      if (ctx.state === 'suspended') ctx.resume();
    } catch (_) { ctx = null; return false; }
    return true;
  }

  function envelope(gain, at, peak, attack, release) {
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(peak, at + attack);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + attack + release);
  }
  function tone(type, from, to, at, peak, attack, release) {
    const osc = ctx.createOscillator(), gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(from, at);
    osc.frequency.exponentialRampToValueAtTime(to, at + attack + release);
    envelope(gain, at, peak, attack, release);
    osc.connect(gain).connect(master);
    osc.start(at);
    osc.stop(at + attack + release + 0.02);
  }
  function noise(seconds) {
    const buffer = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * seconds), ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    return source;
  }

  const SOUNDS = {
    // A soft glassy tick.
    hover(at) { tone('sine', 2600, 1900, at, 0.035, 0.004, 0.035); },
    // Two rising notes: the menu's confirm.
    click(at) {
      tone('triangle', 660, 650, at, 0.07, 0.006, 0.09);
      tone('sine', 990, 985, at + 0.055, 0.05, 0.006, 0.14);
    },
    // Filtered air sweeping upward, with a faint low tone under it.
    switch(at) {
      const air = noise(0.45), band = ctx.createBiquadFilter(), gain = ctx.createGain();
      band.type = 'bandpass';
      band.Q.value = 1.4;
      band.frequency.setValueAtTime(380, at);
      band.frequency.exponentialRampToValueAtTime(2800, at + 0.38);
      envelope(gain, at, 0.09, 0.12, 0.3);
      air.connect(band).connect(gain).connect(master);
      air.start(at);
      air.stop(at + 0.45);
      tone('sine', 180, 260, at, 0.03, 0.08, 0.28);
    },
  };

  function play(name) {
    if (muted || !ctx || ctx.state === 'closed' || !SOUNDS[name]) return false;
    try { SOUNDS[name](ctx.currentTime + 0.005); } catch (_) { return false; }
    return true;
  }

  function setMuted(value) {
    muted = Boolean(value);
    writeMuted(muted);
    document.querySelectorAll('.sound-toggle').forEach(syncToggle);
    return muted;
  }
  function syncToggle(button) {
    button.setAttribute('aria-pressed', String(muted));
    button.setAttribute('aria-label', muted ? 'Unmute sound' : 'Mute sound');
    button.title = muted ? 'Sound off' : 'Sound on';
  }

  const SPEAKER = '<path class="sound-cone" d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/>';
  function mountToggle() {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'sound-toggle';
    button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${SPEAKER}<path class="sound-waves" d="M15.5 9.2a4 4 0 0 1 0 5.6M18 6.8a7.4 7.4 0 0 1 0 10.4"/><path class="sound-cross" d="M15.5 9.5l5 5M20.5 9.5l-5 5"/></svg>`;
    syncToggle(button);
    button.addEventListener('click', () => {
      setMuted(!muted);
      if (!muted) play('click');
    });
    (document.querySelector('.brand') || document.body).appendChild(button);
  }

  // Any first gesture also unlocks audio, so sound works even if the title screen is absent.
  const firstGesture = () => unlock();
  window.addEventListener('pointerdown', firstGesture, {capture: true, once: true});
  window.addEventListener('keydown', firstGesture, {capture: true, once: true});

  document.addEventListener('pointerdown', () => { pointerHeld = true; }, true);
  document.addEventListener('pointerup', () => { pointerHeld = false; }, true);
  document.addEventListener('pointerover', event => {
    if (pointerHeld || event.pointerType === 'touch') return;
    const target = event.target.closest?.(TICK_TARGETS);
    if (!target || target.contains(event.relatedTarget)) return;
    const now = performance.now();
    if (now - lastHover < HOVER_GAP_MS) return;
    lastHover = now;
    play('hover');
  });
  document.addEventListener('focusin', event => {
    // Keyboard focus ticks like hover; pointer focus already ticked on hover.
    if (event.target.matches?.(':focus-visible') && event.target.closest(TICK_TARGETS)) play('hover');
  });
  document.addEventListener('click', event => {
    const target = event.target.closest?.(CLICK_TARGETS);
    // The view tabs get the whoosh from the view change itself (below), and the mute button sounds on its own.
    if (!target || target.closest('.view-tabs, .sound-toggle')) return;
    play('click');
  });

  function watchViewSwitch() {
    const story = document.getElementById('viewStory');
    if (!story) return;
    new MutationObserver(records => {
      if (records.some(r => r.oldValue !== story.getAttribute('aria-pressed'))) play('switch');
    }).observe(story, {attributes: true, attributeFilter: ['aria-pressed'], attributeOldValue: true});
  }

  window.uiSound = {
    play,
    unlock,
    setMuted,
    isMuted: () => muted,
    isUnlocked: () => Boolean(ctx) && ctx.state !== 'closed',
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { mountToggle(); watchViewSwitch(); });
  } else { mountToggle(); watchViewSwitch(); }
})();
