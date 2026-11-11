/* Story view: reads one run's chapter as a script, and shows what the other selected
 * runs did at each decision. Loaded before app.js, whose helpers it uses at call time.
 */
'use strict';
const KEY_MOMENTS_LEAD_OUT = 2, KEY_MOMENTS_LEAD_IN = 3;
const storyCache = new Map();
let storyVersion = 0;

function readerRun() {
  const runs = activeRuns();
  return runs.find(run => run.id === state.readerRunId) || runs.find(run => run.choices > 0) || runs[0] || null;
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

function buildStoryItems(beats) {
  const items = [];
  let heading = null;
  const startSection = (text, index, moment) => {
    if (text && text !== heading) items.push({kind: 'heading', text, index, moment});
    if (text) heading = text;
  };
  for (const beat of beats) {
    const moment = beat.moment ?? beat.node_id ?? beat.id;
    if (beat.type === 'scene') {
      startSection(beat.heading, beat.index, moment);
      const description = beat.description && beat.description !== beat.heading ? beat.description : '';
      if (beat.observations?.length) {
        items.push({kind: 'clue', index: beat.index, moment, title: description.replace(/^Inspect:\s*/i, ''), lines: beat.observations});
      } else if (description) {
        items.push({kind: 'narration', index: beat.index, moment, text: description});
      }
      for (const line of beat.dialogue || []) items.push({kind: 'line', index: beat.index, moment, speaker: line.speaker, text: line.text});
    } else if (beat.type === 'decision') {
      startSection(beat.heading, beat.index, moment);
      items.push({kind: 'decision', index: beat.index, moment, beat});
    } else if (beat.type === 'condition' || beat.type === 'route') {
      items.push({kind: 'rule', index: beat.index, moment, beat});
    } else if (beat.type === 'ending') {
      items.push({kind: 'ending', index: beat.index, moment, text: beat.description});
    } else if (beat.type === 'memory') {
      items.push({kind: 'memory', index: beat.index, moment, ...beat});
    }
  }
  return items;
}

/* Every story element names its event and its Moment, so the Flowchart can open it. */
const graphNode = id => state.graph?.nodes?.[id] || null;
const MAGNIFIER = '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="6.5" cy="6.5" r="4.5"/><path d="M10 10l4 4"/></svg>';
const momentAttrs = item => `data-index="${item.index}"${item.moment != null ? ` data-moment="${esc(item.moment)}"` : ''}`;
function renderLine(item, protagonist) {
  const lead = protagonist && item.speaker === protagonist;
  return `<p class="story-line ${lead ? 'is-protagonist' : ''}" ${momentAttrs(item)}><span class="story-speaker">${esc(item.speaker || 'Unknown')}</span><span class="story-text">${esc(item.text)}</span></p>`;
}
function renderClue(item) {
  const key = graphNode(item.moment)?.key;
  return `<div class="story-clue ${key ? 'is-key' : ''}" ${momentAttrs(item)}><div class="story-clue-title">Inspected${item.title ? `: ${esc(item.title)}` : ''}${key ? '<span class="story-key" title="Key area"></span>' : ''}</div>${item.lines.map(line => {
    const [first, ...rest] = String(line).split(' | ');
    return `<p><b>${esc(first)}</b>${rest.length ? `<span>${esc(rest.join(' · '))}</span>` : ''}</p>`;
  }).join('')}</div>`;
}
function renderRule(item) {
  const beat = item.beat;
  if (beat.type === 'route') {
    if (!beat.assumed) return '';
    return `<p class="story-rule" ${momentAttrs(item)}>Assumed: ${esc(beat.flag)} = ${esc(String(beat.value))}</p>`;
  }
  const branches = state.graph?.nodes?.[beat.node_id]?.branches || [];
  const taken = branches[beat.branch_index]?.condition_text;
  if (!beat.used_unverified_default || !taken) return '';
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
  const beat = item.beat, {byChoice} = compareDecision(key, tables);
  const who = beat.character && beat.character !== 'multiple' ? beat.character : null;
  const exploration = Boolean(graphNode(beat.node_id)?.exploration);
  const options = (beat.available_choices || []).map(option => {
    const chosen = option.id === beat.choice_id, group = byChoice.get(option.id) || [];
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
    <div class="story-why"><div class="story-why-label">${esc(run.model)}</div><p>${esc(beat.rationale || '—')}</p></div>
    <div class="story-other-why is-hidden" aria-live="polite"></div>
  </article>`;
}
function renderItem(item, context) {
  switch (item.kind) {
    case 'heading': return `<h2 class="story-section" ${momentAttrs(item)}>${esc(item.text)}</h2>`;
    case 'line': return renderLine(item, context.protagonist);
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
  $('readerRun').innerHTML = activeRuns().map(item => `<option value="${esc(item.id)}" ${item.id === run?.id ? 'selected' : ''}>${esc(item.model)}${runStatusLabel(item) ? ` (${esc(runStatusLabel(item))})` : ''}</option>`).join('');
  $('readerRun').disabled = !run;
  $('storyMode').setAttribute('aria-pressed', String(state.storyMode === 'key'));
  document.querySelectorAll('.run-chip').forEach(chip => chip.classList.toggle('is-reader', state.view === 'story' && chip.dataset.focusId === run?.id));
}
function renderDecisionStrip(decisions) {
  $('decisionStrip').innerHTML = decisions.length
    ? decisions.map(({number, split, label}) => `<button type="button" class="${split ? 'is-split' : ''}" data-jump-decision="${number}" title="Decision ${number}: ${esc(label)}${split ? ' (models split)' : ''}" aria-label="Go to decision ${number}${split ? ', models split' : ''}">${number}</button>`).join('')
    : '';
}
function renderChapterSummary(chapter) {
  $('chapterSubtitle').textContent = chapterCharacter(chapter) || '';
}
function renderUnvisitedChapter(run, chapter) {
  const visitors = activeRuns().filter(item => (item.chapters_visited || []).includes(chapter));
  const message = visitors.length ? `Reached by ${visitors.map(item => esc(item.model)).join(', ')}` : '';
  $('storyContent').innerHTML = `<div class="story-empty"><strong>${esc(run.model)} never got here</strong>${message ? `<p>${message}</p>` : ''}</div>${chapterNavigation(run, chapter)}`;
  renderDecisionStrip([]);
  renderChapterSummary(chapter);
}
async function renderStory({keepScroll = false} = {}) {
  const run = readerRun(), chapter = state.chapter;
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
  const beats = response.beats || [];
  // portraits.js slides the chapter's Character in at the edge of the Story.
  document.dispatchEvent(new CustomEvent('storychapter', {detail: {chapter, character: chapterCharacter(chapter), run: run.id}}));
  if (!beats.length) {renderUnvisitedChapter(run, chapter); if (!keepScroll) scrollStoryToTop(); return;}

  const items = buildStoryItems(beats);
  const tables = activeViews().map(view => ({run: view.run, table: decisionsByVisit(view)}));
  const visits = new Map(), numbers = new Map(), keys = new Map();
  // Visit numbers count from the run's start, because a node can recur across chapters.
  for (const decision of detail?.decisions || []) {
    if (decision.index < beats[0].index) visits.set(decision.node_id, (visits.get(decision.node_id) || 0) + 1);
  }
  const summaries = [];
  for (const item of items) {
    if (item.kind !== 'decision') continue;
    const visit = (visits.get(item.beat.node_id) || 0) + 1;
    visits.set(item.beat.node_id, visit);
    const key = `${item.beat.node_id}#${visit}`, number = summaries.length + 1;
    numbers.set(item, number); keys.set(item, key);
    const chosen = (item.beat.available_choices || []).find(option => option.id === item.beat.choice_id);
    summaries.push({number, label: chosen?.label || item.beat.choice_id, split: compareDecision(key, tables).byChoice.size > 1});
  }
  const context = {protagonist: chapterCharacter(chapter), numbers, keys, tables, run, total: summaries.length};
  const body = state.storyMode === 'key' ? renderCondensed(items, context) : items.map(item => renderItem(item, context)).join('');
  $('storyContent').innerHTML = caveatBanner(run) + briefingOpener(response.briefing) + body + chapterNavigation(run, chapter);
  renderDecisionStrip(summaries);
  renderChapterSummary(chapter);
  if (state.pendingMoment) scrollToMoment(state.pendingMoment);
  else if (!keepScroll) scrollStoryToTop();
}
function scrollStoryToTop() {
  // Phones scroll the whole panel rather than the story pane.
  $('storyScroll').scrollTop = 0;
  document.querySelector('.main-panel').scrollTop = 0;
}
/* Opens the Story at a Moment: the first element of any of `moments`, else the first beat at
 * or after event `index`. Chapter exits have no text, so they land on the chapter's last beat. */
function scrollToMoment({moments = [], index = Infinity} = {}) {
  state.pendingMoment = null;
  const wanted = new Set(moments.map(String));
  const beats = [...document.querySelectorAll('#storyContent [data-index]')];
  const target = beats.find(el => wanted.has(el.dataset.moment))
    || beats.find(el => Number(el.dataset.index) >= index) || beats.at(-1);
  if (!target) return;
  const collapsed = target.closest('details');
  if (collapsed) collapsed.open = true;
  target.scrollIntoView({block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
  target.classList.add('story-flash');
  setTimeout(() => target.classList.remove('story-flash'), 1800);
}
function showMomentOnFlowchart(moment) {
  const run = readerRun();
  setView('flow');
  inspect(moment, run?.id, {glide: true});
}
function setReaderRun(id) {
  state.readerRunId = id;
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
  $('readerRun').addEventListener('change', event => setReaderRun(event.target.value));
  $('storyMode').addEventListener('click', () => {
    state.storyMode = state.storyMode === 'key' ? 'full' : 'key';
    renderStory();
  });
  document.querySelectorAll('[data-view]').forEach(tab => tab.addEventListener('click', () => setView(tab.dataset.view)));
}
