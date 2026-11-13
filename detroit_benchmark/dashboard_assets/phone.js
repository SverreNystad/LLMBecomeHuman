/* Phone layout (width up to 760 px): three levels stacked above the Story or Flowchart.
 *
 *   Level 3  the brand and sound toggle, only at the very top of the Story
 *   Level 2  the chapter heading and (Story only) the Following menu and decision strip;
 *            hides while scrolling down, comes back on a small scroll up
 *   Level 1  the chapter row (swiped sideways), Story/Flowchart and +; always on screen
 *
 * The existing controls move into these levels and back again, so their listeners stay put.
 * Wider screens, tablets and landscape phones keep the normal layout.
 */
(() => {
  'use strict';
  const query = matchMedia('(max-width: 760px)');
  const SCROLL_HIDE_PX = 8, SCROLL_SHOW_PX = 6, TOP_PX = 4, SWIPE_PX = 24;
  window.isPhoneLayout = () => query.matches;

  let bar = null, levels = null, homes = [], lastY = 0;

  function ensureBar() {
    if (bar) return bar;
    bar = document.createElement('header');
    bar.className = 'phone-bar';
    bar.id = 'phoneBar';
    bar.innerHTML = '<div class="phone-level phone-l3"></div><div class="phone-level phone-l2"></div>'
      + '<div class="phone-level phone-l1"><div class="phone-chapters"></div><div class="phone-controls"></div></div>';
    levels = {
      l3: bar.querySelector('.phone-l3'),
      l2: bar.querySelector('.phone-l2'),
      chapters: bar.querySelector('.phone-chapters'),
      controls: bar.querySelector('.phone-controls'),
    };
    document.querySelector('.main-panel').prepend(bar);
    setupSwipe();
    return bar;
  }

  /* Moves an element into a level, leaving a marker where it lived. */
  function move(el, into) {
    if (!el) return;
    const home = document.createComment('phone-home');
    el.before(home);
    homes.push([home, el]);
    into.appendChild(el);
  }

  function enter() {
    ensureBar();
    move(document.querySelector('.brand'), levels.l3);
    move(document.querySelector('.chapter-heading-text'), levels.l2);
    move(document.querySelector('.story-toolbar'), levels.l2);
    move(document.getElementById('chapterList'), levels.chapters);
    move(document.querySelector('.view-tabs'), levels.controls);
    move(document.getElementById('pickerContainer'), levels.controls);
    document.body.classList.add('is-phone');
    lastY = 0;
    setLevel2(true);
    document.body.classList.remove('phone-scrolled');
    showActiveChapter();
  }

  function leave() {
    for (const [home, el] of homes.reverse()) home.replaceWith(el);
    homes = [];
    document.body.classList.remove('is-phone', 'phone-scrolled', 'phone-l2-hidden');
  }

  function setLevel2(shown) {
    document.body.classList.toggle('phone-l2-hidden', !shown);
  }

  /* Level 3 only at the top; level 2 hides scrolling down and returns on a small scroll up. */
  function onStoryScroll(event) {
    if (!query.matches) return;
    const y = event.currentTarget.scrollTop;
    document.body.classList.toggle('phone-scrolled', y > TOP_PX);
    if (y <= TOP_PX) setLevel2(true);
    else if (y - lastY > SCROLL_HIDE_PX) setLevel2(false);
    else if (lastY - y > SCROLL_SHOW_PX) setLevel2(true);
    if (Math.abs(y - lastY) > Math.min(SCROLL_HIDE_PX, SCROLL_SHOW_PX)) lastY = y;
  }

  /* Swiping up or down on the bars (not the chart) hides or shows level 2. */
  function setupSwipe() {
    let start = null;
    bar.addEventListener('touchstart', event => {
      const t = event.touches[0];
      start = event.touches.length === 1 ? {x: t.clientX, y: t.clientY} : null;
    }, {passive: true});
    bar.addEventListener('touchend', event => {
      if (!start) return;
      const t = event.changedTouches[0], dx = t.clientX - start.x, dy = t.clientY - start.y;
      start = null;
      if (Math.abs(dy) < SWIPE_PX || Math.abs(dy) < Math.abs(dx)) return;
      setLevel2(dy > 0);
    }, {passive: true});
  }

  /* The current chapter is always scrolled into the chapter row. */
  function showActiveChapter() {
    if (!query.matches) return;
    const active = document.querySelector('#chapterList .chapter-entry.active');
    const row = document.getElementById('chapterList');
    if (!active || !row) return;
    const left = active.offsetLeft - (row.clientWidth - active.offsetWidth) / 2;
    row.scrollTo({left: Math.max(0, left), behavior: 'auto'});
  }

  function sync() { if (query.matches) { if (!homes.length) enter(); } else if (homes.length) leave(); }

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('storyScroll')?.addEventListener('scroll', onStoryScroll, {passive: true});
    new MutationObserver(showActiveChapter).observe(document.getElementById('chapterList'), {childList: true, subtree: true, attributes: true, attributeFilter: ['class']});
    sync();
  });
  query.addEventListener('change', sync);
})();
