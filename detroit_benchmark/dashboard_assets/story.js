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
function modelMark(run, decision, label) {
  return `<button type="button" class="story-mark" data-why-run="${esc(run.id)}" data-why-text="${esc(decision.rationale || '—')}" data-why-label="${esc(label)}" style="--run-color:${routeColor(run)}" title="${esc(run.model)}" aria-label="${esc(run.model)} chose ${esc(label)}. Show its reason.">${modelIcon(providerOf(run))}</button>`;
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
    const others = group.filter(entry => entry.run.id !== run.id);
    return `<li class="${chosen ? 'is-chosen' : ''}"><span class="story-option-tick" aria-hidden="true">${chosen ? '✓' : ''}</span><span class="story-option-label">${esc(option.label || option.id)}</span><span class="story-option-models">${others.map(entry => modelMark(entry.run, entry.decision, option.label || option.id)).join('')}</span></li>`;
  }).join('');
  const count = exploration
    ? `<span class="story-decision-count story-exploration" title="Exploration Choice: how thoroughly to search">${MAGNIFIER}Decision ${number} of ${total}</span>`
    : `<span class="story-decision-count">Decision ${number} of ${total}</span>`;
  return `<article class="story-decision ${exploration ? 'is-exploration' : ''}" id="story-decision-${number}" ${momentAttrs(item)} style="--run-color:${routeColor(run)}">
    <header>${count}${agreementLabel(byChoice)}</header>
    <h3>${who ? `What does ${esc(who)} do?` : 'What happens next?'}</h3>
    <ul class="story-options">${options}</ul>
    <div class="story-why"><div class="story-why-label">${esc(run.model)}</div><p>${esc(record.rationale || '—')}</p></div>
    <div class="story-other-why is-hidden" aria-live="polite"></div>
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
function renderStoryToolbar(run) {
  $('storyRun').innerHTML = activeRuns().map(item => `<option value="${esc(item.id)}" ${item.id === run?.id ? 'selected' : ''}>${esc(item.model)}${runStatusLabel(item) ? ` (${esc(runStatusLabel(item))})` : ''}</option>`).join('');
  $('storyRun').disabled = !run;
  $('storyMode').setAttribute('aria-pressed', String(state.storyMode === 'key'));
  document.querySelectorAll('.run-chip').forEach(chip => chip.classList.toggle('is-followed', state.view === 'story' && chip.dataset.focusId === run?.id));
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
async function renderStory({keepScroll = false} = {}) {
  const run = storyRun(), chapter = state.chapter;
  renderStoryToolbar(run);
  if (!run || !chapter || state.view !== 'story') return;
  const version = ++storyVersion, detail = state.details.get(run.id);
  const cacheKey = `${run.id}\u0000${chapter}\u0000${detail?.events?.length || 0}`;
  let response = storyCache.get(cacheKey);
  if (!response) {
    if (!keepScroll) $('storyContent').innerHTML = '';
    try {
      response = await api(`/api/runs/${encodeURIComponent(run.id)}/story?chapter=${encodeURIComponent(chapter)}`);
    } catch (error) {
      if (version === storyVersion) $('storyContent').innerHTML = `<div class="story-empty"><strong>${esc(error.message)}</strong></div>`;
      return;
    }
    storyCache.set(cacheKey, response);
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
  else if (!keepScroll) scrollStoryToTop();
  trackStoryScene();
}
function scrollStoryToTop() {
  // Phones scroll the whole panel rather than the story pane.
  $('storyScroll').scrollTop = 0;
  document.querySelector('.main-panel').scrollTop = 0;
}
/* The scene being read: the last section heading above the upper third of the pane. */
function emitStoryScene() {
  if (state.view !== 'story') return;
  const box = $('storyScroll').getBoundingClientRect();
  const line = Math.max(box.top, 0) + Math.min(box.height, innerHeight) / 3;
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
  target.scrollIntoView({block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
  target.classList.add('story-flash');
  setTimeout(() => target.classList.remove('story-flash'), 1800);
}
function showMomentOnFlowchart(moment) {
  const run = storyRun();
  setView('flow').then(() => inspect(moment, run?.id, {glide: true}));
}
function setStoryRun(id) {
  state.storyRunId = id;
  renderChapterList();
  renderStory();
}
function showOtherReason(button) {
  const card = button.closest('.story-decision'), panel = card.querySelector('.story-other-why');
  const wasOpen = button.getAttribute('aria-pressed') === 'true';
  card.querySelectorAll('.story-mark').forEach(mark => mark.setAttribute('aria-pressed', 'false'));
  panel.classList.toggle('is-hidden', wasOpen);
  if (wasOpen) return;
  const run = runById(button.dataset.whyRun);
  button.setAttribute('aria-pressed', 'true');
  panel.style.setProperty('--run-color', routeColor(run));
  panel.innerHTML = `<div class="story-why-label">${esc(run?.model)} chose ${esc(button.dataset.whyLabel)}</div><p>${esc(button.dataset.whyText)}</p>`;
}
function setupStoryInteractions() {
  $('storyContent').addEventListener('click', event => {
    const mark = event.target.closest('[data-why-run]');
    if (mark) return showOtherReason(mark);
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
  $('storyRun').addEventListener('change', event => setStoryRun(event.target.value));
  $('storyScroll').addEventListener('scroll', trackStoryScene, {passive: true});
  document.querySelector('.main-panel').addEventListener('scroll', trackStoryScene, {passive: true});
  $('storyMode').addEventListener('click', () => {
    state.storyMode = state.storyMode === 'key' ? 'full' : 'key';
    renderStory();
  });
  document.querySelectorAll('[data-view]').forEach(tab => tab.addEventListener('click', () => setView(tab.dataset.view)));
}
