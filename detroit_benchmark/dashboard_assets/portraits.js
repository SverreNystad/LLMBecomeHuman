/* Character portraits: a small LED-ringed face beside each chapter in the chapter list,
 * and a large cut-out that slides in at the edge of the Story when a chapter starts.
 * Loaded before app.js and story.js, which call portraitThumb() and listen for nothing:
 * story.js announces each chapter it opens with a 'storychapter' event on document.
 */
'use strict';
const PORTRAITS = ['connor', 'kara', 'markus'];
const portraitKey = character => {
  const key = String(character || '').toLowerCase();
  return PORTRAITS.includes(key) ? key : null;
};

function portraitThumb(character) {
  const key = portraitKey(character);
  return `<span class="chapter-portrait" data-character="${key || 'none'}" aria-hidden="true">${key ? `<img src="/assets/portraits/${key}.webp" alt="" decoding="async">` : ''}</span>`;
}

(() => {
  let shown = null;
  function stage() {
    const view = document.getElementById('storyView');
    if (!view) return null;
    let img = view.querySelector('.story-portrait');
    if (!img) {
      img = document.createElement('img');
      img.className = 'story-portrait';
      img.alt = '';
      img.setAttribute('aria-hidden', 'true');
      img.decoding = 'async';
      view.prepend(img);
    }
    return img;
  }
  document.addEventListener('storychapter', event => {
    const {chapter, character, run} = event.detail || {};
    const key = portraitKey(character), img = stage();
    if (!img) return;
    const id = `${run}\u0000${chapter}`;
    if (id === shown) return;  // a live refresh of the same chapter keeps the portrait still
    shown = id;
    img.classList.remove('is-in');
    if (!key) {img.removeAttribute('src'); img.dataset.character = 'none'; return;}
    img.dataset.character = key;
    img.src = `/assets/portraits/${key}.webp`;
    void img.offsetWidth;  // restart the slide for every new chapter
    img.classList.add('is-in');
  });
})();
