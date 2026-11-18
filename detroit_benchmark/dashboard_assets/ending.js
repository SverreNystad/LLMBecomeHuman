/* Ending Summary: the card that opens the Final Routes chapter in the Story. Each Run's
 * summary is written on the server (ending.py); this only lays it out, one column per
 * Shown Run, or the Followed Run alone on a phone. Uses app.js helpers at call time.
 */
'use strict';
const ENDING_CHAPTER = 'final';

function endingRuns() {
  if (document.body.classList.contains('is-phone')) return [storyRun()].filter(Boolean);
  return activeRuns();
}
function endingColumn(run) {
  const summary = state.details.get(run.id)?.ending_summary;
  const head = `<h3 class="ending-run-name"><span class="ending-run-logo">${modelIcon(providerOf(run))}</span><span>${esc(run.model)}</span></h3>`;
  if (!summary?.finished) {
    return `<article class="ending-run is-unfinished" data-run-id="${esc(run.id)}" style="--run-color:${routeColor(run)}">${head}<p class="ending-unfinished">Story not finished</p></article>`;
  }
  if (summary.recorded === false) {
    return `<article class="ending-run is-unrecorded" data-run-id="${esc(run.id)}" style="--run-color:${routeColor(run)}">${head}<p class="ending-unfinished">This Run was played before the story tracked who lives and how each story ends, so it has no ending to show.</p></article>`;
  }
  const characters = summary.characters.map(entry =>
    `<div class="ending-character" data-character="${esc(entry.name.toLowerCase())}"><dt>${esc(entry.name)}</dt><dd>${esc(entry.sentence)}</dd></div>`).join('');
  const fates = summary.fates.map(fate =>
    `<li class="is-${esc(fate.fate)}"><span>${esc(fate.name)}</span><b>${esc(fate.text)}</b></li>`).join('');
  const news = summary.world.headlines.map(line => `<li>${esc(line)}</li>`).join('');
  return `<article class="ending-run" data-run-id="${esc(run.id)}" style="--run-color:${routeColor(run)}">${head}
    <dl class="ending-characters">${characters}</dl>
    <ul class="ending-fates" aria-label="Fates">${fates}</ul>
    <div class="ending-world"><h4>Detroit</h4><p>${esc(summary.world.sentence)}</p>${news ? `<ul class="ending-news" aria-label="Public News">${news}</ul>` : ''}</div>
  </article>`;
}
/* The card's markup, or '' outside Final Routes. */
function endingSummaryCard(chapter) {
  const runs = chapter === ENDING_CHAPTER ? endingRuns() : [];
  if (!runs.length) return '';
  const note = runs.map(run => state.details.get(run.id)?.ending_summary?.note).find(Boolean) || '';
  return `<section class="ending-summary" aria-label="Ending" style="--ending-columns:${runs.length}">
    <header class="ending-head"><span class="ending-title">Ending</span></header>
    <div class="ending-columns">${runs.map(endingColumn).join('')}</div>
    <p class="ending-note">${esc(note)}</p>
  </section>`;
}
