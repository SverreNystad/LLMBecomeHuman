/* Story view: reads one run's chapter as a script, and shows what the other selected
 * runs did at each decision. Loaded before app.js, whose helpers it uses at call time.
 */
'use strict';
const KEY_MOMENTS_LEAD_OUT = 2, KEY_MOMENTS_LEAD_IN = 3;
const storyCache = new Map();
let storyVersion = 0;

function storyRun() {
  const runs = activeRuns();
  return runs.find(run => run.id === state.storyRunId) || runs.find(run => run.choices > 0) || runs[0] || null;
}
function chapterTitle(chapter) {return state.graph?.chapter_info?.[chapter]?.title || chapter;}
function chapterCharacter(chapter) {return state.graph?.chapter_info?.[chapter]?.character || null;}

/* The same node can be visited twice, so a decision is identified by node and visit number. */
function decisionsByVisit(view) {
  const seen = new Map(), result = new Map();
  for (const decision of view.detail?.decisions || []) {
    const visit = (seen.get(decision.node_id) || 0) + 1;
    seen.set(decision.node_id, visit);
    result.set(`${decision.node_id}#${visit}`, decision);
  }
  return result;
}
function compareDecision(key, tables) {
  const byChoice = new Map(), missing = [];
  for (const {run, table} of tables) {
    const decision = table.get(key);
    if (!decision) {missing.push(run); continue;}
    if (!byChoice.has(decision.choice_id)) byChoice.set(decision.choice_id, []);
    byChoice.get(decision.choice_id).push({run, decision});
  }
  return {byChoice, missing};
}

function buildStoryItems(records) {
  const items = [];
  let heading = null;
  const startSection = (text, index, moment, art = null) => {
    if (text && text !== heading) items.push({kind: 'heading', text, index, moment, art});
    if (text) heading = text;
  };
  for (const record of records) {
    const moment = record.moment ?? record.node_id ?? record.id;
    if (record.type === 'scene') {
      startSection(record.heading, record.index, moment, record.art);
      const description = record.description && record.description !== record.heading ? record.description : '';
      if (record.observations?.length) {
        items.push({kind: 'clue', index: record.index, moment, title: description.replace(/^Inspect:\s*/i, ''), lines: record.observations});
      } else if (description) {
        items.push({kind: 'narration', index: record.index, moment, text: description});
      }
      for (const line of record.dialogue || []) items.push({kind: 'line', index: record.index, moment, speaker: line.speaker, text: line.text});
    } else if (record.type === 'decision') {
      startSection(record.heading, record.index, moment);
      items.push({kind: 'decision', index: record.index, moment, record});
    } else if (record.type === 'condition' || record.type === 'route') {
      items.push({kind: 'rule', index: record.index, moment, record});
    } else if (record.type === 'ending') {
      items.push({kind: 'ending', index: record.index, moment, text: record.description});
    } else if (record.type === 'memory') {
      items.push({kind: 'memory', index: record.index, moment, ...record});
    }
  }
  return items;
}

/* Every story element names its event and its Moment, so the Flowchart can open it. */
const graphNode = id => state.graph?.nodes?.[id] || null;
const MAGNIFIER = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="6.5" cy="6.5" r="4.5"/><path d="M10 10l4 4"/></svg>';
const momentAttrs = item => `data-index="${item.index}"${item.moment != null ? ` data-moment="${esc(item.moment)}"` : ''}`;
function renderLine(item, character) {
  const lead = character && item.speaker === character;
  return `<p class="story-line ${lead ? 'is-character' : ''}" ${momentAttrs(item)}><span class="story-speaker">${esc(item.speaker || 'Unknown')}</span><span class="story-text">${esc(item.text)}</span></p>`;
}
function renderClue(item) {
  const key = graphNode(item.moment)?.key;
  return `<div class="story-clue ${key ? 'is-key' : ''}" ${momentAttrs(item)}><div class="story-clue-title">Inspected${item.title ? `: ${esc(item.title)}` : ''}${key ? '<span class="story-key" title="Key area"></span>' : ''}</div>${item.lines.map(line => {
    const [first, ...rest] = String(line).split(' | ');
    return `<p><b>${esc(first)}</b>${rest.length ? `<span>${esc(rest.join(' · '))}</span>` : ''}</p>`;
  }).join('')}</div>`;
}
function renderRule(item) {
  const record = item.record;
  if (record.type === 'route') {
    if (!record.assumed) return '';
    return `<p class="story-rule" ${momentAttrs(item)}>Assumed: ${esc(record.flag)} = ${esc(String(record.value))}</p>`;
  }
  const branches = state.graph?.nodes?.[record.node_id]?.branches || [];
  const taken = branches[record.branch_index]?.condition_text;
  if (!record.used_unverified_default || !taken) return '';
  return `<p class="story-rule" ${momentAttrs(item)}>Assumed: ${esc(taken)}</p>`;
}
/* A model's logo beside the option it chose. Hovering names the model; clicking shows its
 * justification in the card. The logo whose justification is shown is pressed. */
function modelMark(run, decision, label, shown) {
  return `<button type="button" class="story-mark" data-why-run="${esc(run.id)}" data-why-text="${esc(decision.rationale || '—')}" data-why-label="${esc(label)}" aria-pressed="${shown}" style="--run-color:${routeColor(run)}" aria-label="${esc(run.model)} chose ${esc(label)}. Show its reason.">${modelIcon(providerOf(run))}<span class="story-mark-name" aria-hidden="true">${esc(run.model)}</span></button>`;
}
function agreementLabel(byChoice) {
  const counts = [...byChoice.values()].map(group => group.length).sort((a, b) => b - a);
  const total = counts.reduce((sum, count) => sum + count, 0);
  if (total < 2) return '';
  return counts.length === 1
    ? `<span class="story-agreement agrees">All ${total} models agree</span>`
    : `<span class="story-agreement splits">Models split ${counts.join(' / ')}</span>`;
}
function renderDecision(item, number, total, key, tables, run) {
  const record = item.record, {byChoice} = compareDecision(key, tables);
  const who = record.character && record.character !== 'multiple' ? record.character : null;
  const exploration = Boolean(graphNode(record.node_id)?.exploration);
  const options = (record.available_choices || []).map(option => {
    const chosen = option.id === record.choice_id, group = byChoice.get(option.id) || [];
    // The followed model's logo comes first, so its place in the row never moves.
    const ordered = [...group.filter(entry => entry.run.id === run.id), ...group.filter(entry => entry.run.id !== run.id)];
    return `<li class="${chosen ? 'is-chosen' : ''}"><span class="story-option-tick" aria-hidden="true">${chosen ? '✓' : ''}</span><span class="story-option-label">${esc(option.label || option.id)}</span><span class="story-option-models">${ordered.map(entry => modelMark(entry.run, entry.decision, option.label || option.id, entry.run.id === run.id)).join('')}</span></li>`;
  }).join('');
  const count = exploration
    ? `<span class="story-decision-count story-exploration" title="Exploration Choice: how thoroughly to search">${MAGNIFIER}Decision ${number} of ${total}</span>`
    : `<span class="story-decision-count">Decision ${number} of ${total}</span>`;
  return `<article class="story-decision ${exploration ? 'is-exploration' : ''}" id="story-decision-${number}" ${momentAttrs(item)} style="--run-color:${routeColor(run)}">
    <header>${count}${agreementLabel(byChoice)}</header>
    <h3>${who ? `What does ${esc(who)} do?` : 'What happens next?'}</h3>
    <ul class="story-options">${options}</ul>
    <div class="story-why" aria-live="polite"><div class="story-why-label">${esc(run.model)}</div><p>${esc(record.rationale || '—')}</p></div>
  </article>`;
}
function renderItem(item, context) {
  switch (item.kind) {
    case 'heading': return `<h2 class="story-section" ${momentAttrs(item)}${item.art ? ` data-art="${esc(item.art)}"` : ''}>${esc(item.text)}</h2>`;
    case 'line': return renderLine(item, context.character);
    case 'clue': return renderClue(item);
    case 'narration': return `<p class="story-narration" ${momentAttrs(item)}>${esc(item.text)}</p>`;
    case 'rule': return renderRule(item);
    case 'ending': return `<p class="story-ending" ${momentAttrs(item)}>${esc(item.text)}</p>`;
    case 'memory': return typeof renderMemoryCard === 'function' ? renderMemoryCard(item) : '';
    case 'decision': return renderDecision(item, context.numbers.get(item), context.total, context.keys.get(item), context.tables, context.run);
    default: return '';
  }
}
/* Decisions-only mode keeps the outcome of the last decision and the lead-in to the next. */
function renderCondensed(items, context) {
  const output = [];
  let segment = [];
  const flush = () => {
    const spoken = segment.filter(item => item.kind !== 'heading');
    const cutFrom = KEY_MOMENTS_LEAD_OUT, cutTo = spoken.length - KEY_MOMENTS_LEAD_IN;
    if (cutTo - cutFrom < 3) {
      output.push(...segment.map(item => renderItem(item, context)));
    } else {
      const hidden = new Set(spoken.slice(cutFrom, cutTo));
      const firstHidden = segment.findIndex(item => hidden.has(item));
      const lastHidden = segment.length - 1 - [...segment].reverse().findIndex(item => hidden.has(item));
      output.push(...segment.slice(0, firstHidden).map(item => renderItem(item, context)));
      output.push(`<details class="story-gap"><summary>Show more</summary>${segment.slice(firstHidden, lastHidden + 1).map(item => renderItem(item, context)).join('')}</details>`);
      output.push(...segment.slice(lastHidden + 1).map(item => renderItem(item, context)));
    }
    segment = [];
  };
  for (const item of items) {
    if (item.kind === 'decision') {flush(); output.push(renderItem(item, context));}
    else segment.push(item);
  }
  flush();
  return output.join('');
}

function runChapterSequence(run) {
  const order = (state.details.get(run.id)?.decisions_by_chapter || []).map(entry => entry.chapter);
  return order.length ? order : chapters();
}
function adjacentChapter(run, chapter, step) {
  const sequence = runChapterSequence(run);
  const position = sequence.indexOf(chapter);
  if (position >= 0) return sequence[position + step] || null;
  const all = chapters();
  return all[all.indexOf(chapter) + step] || null;
}
function chapterNavigation(run, chapter) {
  const link = (target, label) => target
    ? `<button type="button" class="story-nav-button" data-go-chapter="${esc(target)}"><small>${label}</small><span>${esc(chapterTitle(target))}</span></button>`
    : '<span></span>';
  return `<nav class="story-nav" aria-label="Chapter navigation">${link(adjacentChapter(run, chapter, -1), 'Previous chapter')}${link(adjacentChapter(run, chapter, 1), 'Next chapter')}</nav>`;
}
/* The Chapter Briefing opens the chapter; graphs recorded before briefings have none. */
function briefingOpener(briefing) {
  return briefing ? `<p class="story-briefing">${esc(briefing)}</p>` : '';
}
function caveatBanner(run) {
  return run.synthetic ? '<p class="story-caveat">Synthetic preview</p>' : '';
}
function runLabelHtml(run) {
  return `${esc(run.model)}${runStatusLabel(run) ? ` <small>(${esc(runStatusLabel(run))})</small>` : ''}`;
}
function renderStoryToolbar(run) {
  $('storyRun').innerHTML = run
    ? `<span class="story-run-logo" style="--run-color:${routeColor(run)}">${modelIcon(providerOf(run))}</span><span class="story-run-name">${runLabelHtml(run)}</span>`
    : '';
  $('storyRun').disabled = !run;
  if (!run) setFollowingMenu(false);
  $('storyRunMenu').innerHTML = activeRuns().map(item => `<button type="button" role="menuitemradio" class="story-run-option" data-run-id="${esc(item.id)}" aria-checked="${item.id === run?.id}" style="--run-color:${routeColor(item)}"><span class="story-run-logo">${modelIcon(providerOf(item))}</span><span class="story-run-name">${runLabelHtml(item)}</span></button>`).join('');
  $('storyMode').setAttribute('aria-pressed', String(state.storyMode === 'key'));
  document.querySelectorAll('.run-chip').forEach(chip => chip.classList.toggle('is-followed', state.view === 'story' && chip.dataset.focusId === run?.id));
  fitModelBar();
}
function renderDecisionStrip(decisions) {
  $('decisionStrip').innerHTML = decisions.length
    ? decisions.map(({number, split, label}) => `<button type="button" class="${split ? 'is-split' : ''}" data-jump-decision="${number}" title="Decision ${number}: ${esc(label)}${split ? ' (models split)' : ''}" aria-label="Go to decision ${number}${split ? ', models split' : ''}">${number}</button>`).join('')
    : '';
}
function renderChapterSubtitle(chapter) {
  $('chapterSubtitle').textContent = chapterCharacter(chapter) || '';
}
function renderUnvisitedChapter(run, chapter) {
  const visitors = activeRuns().filter(item => (item.chapters_visited || []).includes(chapter));
  const message = visitors.length ? `Reached by ${visitors.map(item => esc(item.model)).join(', ')}` : '';
  $('storyContent').innerHTML = `<div class="story-empty"><strong>${esc(run.model)} never got here</strong>${message ? `<p>${message}</p>` : ''}</div>${chapterNavigation(run, chapter)}`;
  renderDecisionStrip([]);
  renderChapterSubtitle(chapter);
}
/* `position` is a reading position to return to once the chapter is drawn (see readingPosition). */
async function renderStory({keepScroll = false, position = null} = {}) {
  const run = storyRun(), chapter = state.chapter;
  renderStoryToolbar(run);
  if (!run || !chapter || state.view !== 'story') return;
  const version = ++storyVersion, detail = state.details.get(run.id);
  // One entry per Run and chapter, replaced when the Run has played on.
  const cacheKey = `${run.id}\u0000${chapter}`, events = detail?.events?.length || 0;
  let response = storyCache.get(cacheKey)?.events === events ? storyCache.get(cacheKey).response : null;
  if (!response) {
    if (!keepScroll && !position) $('storyContent').innerHTML = '';
    try {
      response = await api(`/api/runs/${encodeURIComponent(run.id)}/story?chapter=${encodeURIComponent(chapter)}`);
    } catch (error) {
      if (version === storyVersion) $('storyContent').innerHTML = `<div class="story-empty"><strong>${esc(error.message)}</strong></div>`;
      return;
    }
    storyCache.set(cacheKey, {events, response});
  }
  if (version !== storyVersion) return;
  const records = response.moments || [];
  // portraits.js slides the chapter's Character in at the edge of the Story.
  document.dispatchEvent(new CustomEvent('storychapter', {detail: {chapter, character: chapterCharacter(chapter), run: run.id}}));
  if (!records.length) {renderUnvisitedChapter(run, chapter); if (!keepScroll) scrollStoryToTop(); return;}

  const items = buildStoryItems(records);
  const tables = activeViews().map(view => ({run: view.run, table: decisionsByVisit(view)}));
  const visits = new Map(), numbers = new Map(), keys = new Map();
  // Visit numbers count from the run's start, because a node can recur across chapters.
  for (const decision of detail?.decisions || []) {
    if (decision.index < records[0].index) visits.set(decision.node_id, (visits.get(decision.node_id) || 0) + 1);
  }
  const summaries = [];
  for (const item of items) {
    if (item.kind !== 'decision') continue;
    const visit = (visits.get(item.record.node_id) || 0) + 1;
    visits.set(item.record.node_id, visit);
    const key = `${item.record.node_id}#${visit}`, number = summaries.length + 1;
    numbers.set(item, number); keys.set(item, key);
    const chosen = (item.record.available_choices || []).find(option => option.id === item.record.choice_id);
    summaries.push({number, label: chosen?.label || item.record.choice_id, split: compareDecision(key, tables).byChoice.size > 1});
  }
  const context = {character: chapterCharacter(chapter), numbers, keys, tables, run, total: summaries.length};
  const body = state.storyMode === 'key' ? renderCondensed(items, context) : items.map(item => renderItem(item, context)).join('');
  $('storyContent').innerHTML = caveatBanner(run) + briefingOpener(response.briefing) + body + chapterNavigation(run, chapter);
  renderDecisionStrip(summaries);
  renderChapterSubtitle(chapter);
  if (state.pendingMoment) scrollToMoment(state.pendingMoment);
  else if (position) returnToReadingPosition(position);
  else if (!keepScroll) scrollStoryToTop();
  trackStoryScene();
}
function scrollStoryToTop() {
  // Phones scroll the whole panel rather than the story pane.
  $('storyScroll').scrollTop = 0;
  document.querySelector('.main-panel').scrollTop = 0;
}
/* Moves the Story by `delta` pixels. Phones scroll the whole panel rather than the story pane,
 * so whatever the story pane cannot take is passed on to the panel. */
function scrollStoryBy(delta) {
  for (const scroller of [$('storyScroll'), document.querySelector('.main-panel')]) {
    if (Math.abs(delta) < 1) return;
    const before = scroller.scrollTop;
    scroller.scrollTop = before + delta;
    delta -= scroller.scrollTop - before;
  }
}
/* What is being read is judged at the upper third of the pane. */
function readingLine() {
  const box = $('storyScroll').getBoundingClientRect();
  return Math.max(box.top, 0) + Math.min(box.height, innerHeight) / 3;
}
/* Scene headings and decisions, each named so the same one can be found in another Run's
 * text: headings by their text, decisions by their node, counting repeats within the chapter. */
function storyAnchors() {
  const seen = new Map();
  return [...document.querySelectorAll('#storyContent .story-section, #storyContent .story-decision')].map(el => {
    const name = el.classList.contains('story-decision') ? `decision ${el.dataset.moment}` : `heading ${el.textContent}`;
    const repeat = (seen.get(name) || 0) + 1;
    seen.set(name, repeat);
    return {el, key: `${name}#${repeat}`};
  });
}
/* The reading position: the heading or decision being read, the ones before it (newest first,
 * to fall back on), and where it sits on screen. Null when the chapter has none. */
function readingPosition() {
  const line = readingLine(), anchors = storyAnchors();
  let current = -1;
  for (const [at, {el}] of anchors.entries()) {
    if (!el.getClientRects().length) continue;  // inside a collapsed gap
    if (current >= 0 && el.getBoundingClientRect().top > line) break;
    current = at;
  }
  if (current < 0) return null;
  return {
    keys: anchors.slice(0, current + 1).map(anchor => anchor.key).reverse(),
    top: anchors[current].el.getBoundingClientRect().top,
  };
}
/* Puts the same heading or decision back where it was, or else the nearest earlier one this
 * Run reached; the chapter's top when it reached none of them. */
function returnToReadingPosition(position) {
  const found = new Map(storyAnchors().map(anchor => [anchor.key, anchor.el]));
  const target = position.keys.map(key => found.get(key)).find(Boolean);
  if (!target) return scrollStoryToTop();
  const collapsed = target.closest('details');
  if (collapsed) collapsed.open = true;
  scrollStoryBy(target.getBoundingClientRect().top - position.top);
}
/* The scene being read: the last section heading above the upper third of the pane. */
function emitStoryScene() {
  if (state.view !== 'story') return;
  const line = readingLine();
  let heading = null, art = null;
  for (const el of document.querySelectorAll('#storyContent .story-section')) {
    if (!el.getClientRects().length) continue;  // inside a collapsed gap
    if (heading !== null && el.getBoundingClientRect().top > line) break;
    heading = el.textContent;
    art = el.dataset.art || null;
  }
  // The Story names the scene's image itself; the backdrop only matches headings as a fallback.
  emitScene(heading ? [heading] : [], art);
}
let storySceneFrame = 0;
function trackStoryScene() {
  if (!storySceneFrame) storySceneFrame = requestAnimationFrame(() => {storySceneFrame = 0; emitStoryScene();});
}
/* Opens the Story at a Moment: the first element of any of `moments`, else the first record at
 * or after event `index`. Chapter exits have no text, so they land on the chapter's last record. */
function scrollToMoment({moments = [], index = Infinity} = {}) {
  state.pendingMoment = null;
  const wanted = new Set(moments.map(String));
  const records = [...document.querySelectorAll('#storyContent [data-index]')];
  const target = records.find(el => wanted.has(el.dataset.moment))
    || records.find(el => Number(el.dataset.index) >= index) || records.at(-1);
  if (!target) return;
  const collapsed = target.closest('details');
  if (collapsed) collapsed.open = true;
  target.scrollIntoView({block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth'});
  target.classList.add('story-flash');
  setTimeout(() => target.classList.remove('story-flash'), 1800);
}
function showMomentOnFlowchart(moment) {
  const run = storyRun();
  setView('flow').then(() => inspect(moment, run?.id, {glide: true}));
}
/* Following another Run keeps the reader where they were in the chapter. */
function setStoryRun(id) {
  if (id === storyRun()?.id) return;
  const position = readingPosition();
  state.storyRunId = id;
  renderChapterList();
  renderStory({position});
}
/* Shows one model's justification in a decision card. Says what it chose when that differs
 * from the followed model's choice. Only this card changes; the Story keeps its model. */
function showJustification(button) {
  if (button.getAttribute('aria-pressed') === 'true') return;
  const card = button.closest('.story-decision'), why = card.querySelector('.story-why');
  card.querySelectorAll('.story-mark').forEach(mark => mark.setAttribute('aria-pressed', String(mark === button)));
  const run = runById(button.dataset.whyRun), followed = run?.id === storyRun()?.id;
  const sameChoice = button.closest('li')?.classList.contains('is-chosen');
  const label = followed || sameChoice ? esc(run?.model) : `${esc(run?.model)} chose ${esc(button.dataset.whyLabel)}`;
  why.style.setProperty('--why-color', followed ? '' : routeColor(run));
  why.classList.toggle('is-other', !followed);
  why.innerHTML = `<div class="story-why-label">${label}</div><p>${esc(button.dataset.whyText)}</p>`;
  if (!reducedMotion()) playClass(why, 'why-swap', 300);
}
/* The Following menu: opens and closes with the model picker's glitch. */
function setFollowingMenu(open) {
  if (open && $('storyRun').disabled) return;
  if (open && state.pickerOpen) {state.pickerOpen = false; updateSelectors();}
  $('storyRun').setAttribute('aria-expanded', String(open));
  setDropdown($('storyRunMenu'), open);
  if (open) ($('storyRunMenu').querySelector('[aria-checked="true"]') || $('storyRunMenu').firstElementChild)?.focus();
}
function setupFollowingMenu() {
  const menu = $('storyRunMenu'), isOpen = () => $('storyRun').getAttribute('aria-expanded') === 'true';
  $('storyRun').addEventListener('click', event => {event.stopPropagation(); setFollowingMenu(!isOpen());});
  menu.addEventListener('click', event => {
    const option = event.target.closest('[data-run-id]');
    if (!option) return;
    setFollowingMenu(false);
    $('storyRun').focus();
    if (option.dataset.runId !== storyRun()?.id) setStoryRun(option.dataset.runId);
  });
  menu.addEventListener('keydown', event => {
    const options = [...menu.querySelectorAll('[data-run-id]')], at = options.indexOf(document.activeElement);
    const to = {ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: options.length - 1}[event.key];
    if (to === undefined) return;
    event.preventDefault();
    options[(to + options.length) % options.length]?.focus();
  });
  // Tabbing out of the menu closes it.
  $('storyRunPicker').addEventListener('focusout', event => {
    if (isOpen() && !$('storyRunPicker').contains(event.relatedTarget)) setFollowingMenu(false);
  });
  document.addEventListener('click', event => {if (isOpen() && !event.target.closest('#storyRunPicker')) setFollowingMenu(false);});
  document.addEventListener('keydown', event => {if (event.key === 'Escape' && isOpen()) {setFollowingMenu(false); $('storyRun').focus();}});
}
function setupStoryInteractions() {
  $('storyContent').addEventListener('click', event => {
    const mark = event.target.closest('[data-why-run]');
    if (mark) return showJustification(mark);
    const chapter = event.target.closest('[data-go-chapter]');
    if (chapter) return changeChapter(chapter.dataset.goChapter);
    if (event.target.closest('button, a, summary, select, input')) return;
    if (String(window.getSelection?.() || '')) return;  // selecting text is not a click on a Moment
    const moment = event.target.closest('[data-moment]');
    if (moment) showMomentOnFlowchart(moment.dataset.moment);
  });
  $('decisionStrip').addEventListener('click', event => {
    const button = event.target.closest('[data-jump-decision]');
    if (button) $(`story-decision-${button.dataset.jumpDecision}`)?.scrollIntoView({block: 'start', behavior: 'smooth'});
  });
  setupFollowingMenu();
  $('storyScroll').addEventListener('scroll', trackStoryScene, {passive: true});
  document.querySelector('.main-panel').addEventListener('scroll', trackStoryScene, {passive: true});
  $('storyMode').addEventListener('click', () => {
    state.storyMode = state.storyMode === 'key' ? 'full' : 'key';
    renderStory();
  });
  document.querySelectorAll('[data-view]').forEach(tab => tab.addEventListener('click', () => setView(tab.dataset.view)));
}
