/* Chapter Flowchart: every branch of a chapter, with each selected Run's route drawn on top. */
'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const svgNS = 'http://www.w3.org/2000/svg';
const MIN_READABLE_FIT = 0.5, OPENING_ZOOM = 0.85;
const SCENE_NODE_WIDTH = 240, NODE_LOGO_STEP = 22, NODE_LOGO_PADDING = 12;
// A chapter shows at most six Runs, one per shade of its Character's colour.
const MAX_VISIBLE_RUNS = 6;
// Shade positions (1 = lightest … 6 = darkest) in the order slots are handed out,
// so the first few models get well-separated shades.
const SHADE_ORDER = [3, 5, 1, 4, 6, 2];
const PROVIDER_STYLES = new Set(['openai', 'anthropic', 'google', 'gemini', 'xai', 'grok', 'deepseek', 'mistral']);
const state = {
  runs: [], selectedIds: [], details: new Map(), graph: null, chapter: null,
  rendered: null, selected: null, scale: 1, panX: 0, panY: 0,
  requestVersion: 0, busyRefresh: false, pickerOpen: false, search: '',
  toastTimer: null, selectionHydrated: false, shadeSlots: new Map(), focusedId: null, viewTouched: false,
  view: 'story', storyRunId: null, storyMode: 'full', pendingMoment: null
};
const providerOf = run => String(run?.display_provider || run?.provider || 'unknown').toLowerCase();
const modelName = provider => ({openai:'OpenAI',anthropic:'Anthropic',xai:'xAI',grok:'xAI',google:'Google',gemini:'Google',deepseek:'DeepSeek',mistral:'Mistral',openrouter:'OpenRouter',mock:'Mock agent'})[provider] || provider || 'Other';
const modelLabel = run => `${run?.model || 'Unknown model'} · ${run?.name || 'run'}`;
const niceNum = n => Number(n || 0).toLocaleString('en-US');
const runStatusLabel = run => ({running: 'playing', stopped: 'stopped'})[run?.status] || '';
const shortTitle = (s, n=44) => String(s||'').length>n ? String(s).slice(0,n-1)+'…' : String(s||'');
const providerStyle = run => PROVIDER_STYLES.has(providerOf(run)) ? providerOf(run) : 'other';
const runSortKey = run => `${providerOf(run)}\u0000${run?.model || ''}\u0000${run?.name || ''}`;
const byRunOrder = (a, b) => runSortKey(a).localeCompare(runSortKey(b));
function runById(id) {return state.runs.find(r=>r.id===id) || null;}
function activeRuns(){return state.selectedIds.map(runById).filter(Boolean);}
function activeViews(){return activeRuns().map(run=>({run,detail:state.details.get(run.id)})).filter(x=>x.detail);}
function anchorRun(){return activeRuns()[0]||null;}
/* What "Select all" adds: every Run of the shown story, the ones already shown first. With
 * nothing shown, the story most Runs played. Capped later at MAX_VISIBLE_RUNS. */
function selectAllCandidates(){
  let hash=anchorRun()?.graph_sha256;
  if(!hash){
    const counts=new Map();
    for(const r of state.runs)if(r.graph_sha256)counts.set(r.graph_sha256,(counts.get(r.graph_sha256)||0)+1);
    hash=[...counts.entries()].sort((a,b)=>b[1]-a[1])[0]?.[0];
  }
  if(!hash)return [];
  const kept=state.selectedIds.filter(id=>runById(id)?.graph_sha256===hash);
  return [...kept,...state.runs.filter(r=>r.graph_sha256===hash&&!kept.includes(r.id)).sort(byRunOrder).map(r=>r.id)];
}
function compatible(run,anchor=anchorRun()) {return !anchor || Boolean(run.graph_sha256 && run.graph_sha256===anchor.graph_sha256);}
/* Each selected Run keeps one shade slot while it stays selected, so it sits at the same
 * place on the light-to-dark range in every chapter. A Run prefers the slot given by its
 * position among all Runs (sorted by provider and model) and falls back to the next free one. */
function assignShadeSlots(){
 for(const id of [...state.shadeSlots.keys()]) if(!state.selectedIds.includes(id)) state.shadeSlots.delete(id);
 const taken=new Set(state.shadeSlots.values()), order=[...state.runs].sort(byRunOrder).map(run=>run.id);
 for(const run of activeRuns().filter(run=>!state.shadeSlots.has(run.id)).sort(byRunOrder)){
  let slot=Math.max(0,order.indexOf(run.id))%MAX_VISIBLE_RUNS;
  while(taken.has(slot)) slot=(slot+1)%MAX_VISIBLE_RUNS;
  state.shadeSlots.set(run.id,slot);taken.add(slot);
 }
}
function shadeOf(run){const slot=state.shadeSlots.get(run?.id);return slot==null?null:SHADE_ORDER[slot];}
/* A CSS colour that follows the current chapter's Character ramp. */
function routeColor(run){const shade=shadeOf(run);return shade?`var(--shade-${shade})`:'var(--ink-faint)';}
function applyRunFocus(runId){
 const active=runId||state.focusedId;
 document.querySelectorAll('.route-overlay').forEach(edge=>{
   const match=!active||edge.dataset.runId===active;
   edge.style.opacity=match?'1':'0.15';
   edge.style.strokeWidth=match&&active?'3.2':'';
 });
 document.querySelectorAll('.node-model-button').forEach(mark=>{
   mark.style.opacity=!active||mark.dataset.runId===active?'1':'0.28';
 });
 document.querySelectorAll('[data-focus-id]').forEach(el=>el.classList.toggle('run-focused',Boolean(active)&&el.dataset.focusId===active));
}
function setupRunFocus(){
 document.querySelectorAll('[data-focus-id]').forEach(el=>{
   el.addEventListener('mouseenter',()=>applyRunFocus(el.dataset.focusId));
   el.addEventListener('mouseleave',()=>applyRunFocus());
   el.addEventListener('click',e=>{
     if(e.target.closest('.run-chip-remove'))return;
     if(state.view==='story'&&el.classList.contains('run-chip')){setStoryRun(el.dataset.focusId);return;}
     state.focusedId=state.focusedId===el.dataset.focusId?null:el.dataset.focusId;
     applyRunFocus();
   });
   el.addEventListener('keydown',e=>{
     if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click();}
   });
 });
}
function modelIcon(provider, extraClass='') {
  const kind=String(provider||'').toLowerCase();
  const assets={openai:'openai',anthropic:'claude',xai:'grok',grok:'grok',google:'gemini',gemini:'gemini',deepseek:'deepseek',mistral:'mistral'};
  if(assets[kind]) return `<img src="/assets/${assets[kind]}-mark.svg" alt="" aria-hidden="true" class="${esc(extraClass)}">`;
  return `<span class="mock-icon" aria-hidden="true">${kind==='mock'?'◇':(kind.slice(0,1).toUpperCase()||'•')}</span>`;
}
function setCharacterTheme(character){
  // Hook for per-Character theming: CSS swaps the --shade ramp on body[data-character].
  const key=CHARACTERS.includes(String(character||'').toLowerCase())?String(character).toLowerCase():'none';
  if(document.body.dataset.character===key)return;
  document.body.dataset.character=key;
  document.dispatchEvent(new CustomEvent('characterchange',{detail:{character:key,chapter:state.chapter}}));
}
/* Tells the background which scene is in view, so it can show that scene's art. */
let lastScene='';
function emitScene(headings=[],art=null){
  const key=JSON.stringify([state.chapter,headings,art]);
  if(key===lastScene)return;
  lastScene=key;
  document.dispatchEvent(new CustomEvent('scenechange',{detail:{chapter:state.chapter,heading:headings[0]||null,headings,art}}));
}
function emitFlowScene(nodeId){
  const node=nodeId&&state.rendered?.graph.nodes.get(nodeId);
  emitScene(node?[...new Set((node.members||[node.node]).map(n=>n?.heading).filter(Boolean))]:[]);
}
function toast(msg) {
  const box=$('toast');box.textContent=msg;box.classList.add('visible');
  clearTimeout(state.toastTimer);state.toastTimer=setTimeout(()=>box.classList.remove('visible'),3400);
}
async function api(path){
 const res=await fetch(path,{cache:'no-store'});
 if(!res.ok){let reason=`${res.status} ${res.statusText}`;try{reason=(await res.json()).detail||reason;}catch(_){}throw new Error(reason);}
 return res.json();
}
function updateSelectors() {
  assignShadeSlots();
  $('pickerToggle').setAttribute('aria-expanded',String(state.pickerOpen));
  $('pickerPanel').classList.toggle('is-hidden',!state.pickerOpen);
  $('pickerToggle').classList.toggle('on',state.pickerOpen);
  const fill=selectAllCandidates();
  $('selectAllRuns').disabled=!fill.length||fill.every(id=>state.selectedIds.includes(id));
  $('selectAllRuns').textContent=fill.length>MAX_VISIBLE_RUNS?'Select six':'Select all';
  const chips=$('selectedRunChips');
  chips.innerHTML=activeRuns().length ? activeRuns().map(run=>`<span class="run-chip" data-focus-id="${esc(run.id)}" role="button" tabindex="0" title="${esc(modelLabel(run))}" style="--run-color:${routeColor(run)}"><span class="run-chip-mark">${modelIcon(providerOf(run))}</span><span class="run-chip-label" title="${esc(modelLabel(run))}">${esc(shortTitle(run.model,24))}</span><button type="button" class="run-chip-remove" data-remove-id="${esc(run.id)}" aria-label="Remove ${esc(modelLabel(run))} from view" title="Remove from view">×</button></span>`).join('') : '';
  chips.querySelectorAll('[data-remove-id]').forEach(btn=>btn.addEventListener('click',()=>toggleRun(btn.dataset.removeId,false)));
  setupRunFocus();
  $('searchRuns').value=state.search;
  renderPickerList();
}
function renderPickerList(){
  const list=$('pickerList');
  const q=state.search.trim().toLowerCase();
  const available=state.runs.filter(r=>`${r.model} ${r.provider} ${r.display_provider||''} ${r.name}`.toLowerCase().includes(q));
  const groups=new Map();
  for(const run of available){const name=modelName(providerOf(run));if(!groups.has(name))groups.set(name,[]);groups.get(name).push(run);}
  list.innerHTML=[...groups.entries()].map(([group,runs])=>`<div class="picker-group"><div class="picker-group-heading">${esc(group)}</div>${runs.map(run=>{
    const checked=state.selectedIds.includes(run.id),allowed=compatible(run)||checked;
    return `<label class="picker-run ${allowed?'':'incompatible'}" style="--run-color:${routeColor(run)}"><input type="checkbox" data-run-id="${esc(run.id)}" ${checked?'checked':''} ${allowed?'':'disabled'}><span class="picker-check"></span><span class="picker-run-logo">${modelIcon(providerOf(run))}</span><span class="picker-run-text"><strong>${esc(run.model)}</strong>${runStatusLabel(run)?`<small>${esc(runStatusLabel(run))}</small>`:''}</span></label>`;
  }).join('')}</div>`).join('')||'<div class="picker-no-runs">No matches</div>';
  list.querySelectorAll('[data-run-id]').forEach(input=>input.addEventListener('change',()=>toggleRun(input.dataset.runId,input.checked)));
}
async function toggleRun(id,enabled){
  const run=runById(id);if(!run)return;
  const selected=state.selectedIds.includes(id);
  if(enabled&&!selected&&!compatible(run)){toast('That model played a different story. Clear the selection first.');renderPickerList();return;}
  if(enabled&&!selected&&state.selectedIds.length>=MAX_VISIBLE_RUNS){toast('Six models at a time. Remove one to add another.');renderPickerList();return;}
  if(enabled&&!selected)state.selectedIds.push(id);
  if(!enabled&&selected)state.selectedIds=state.selectedIds.filter(x=>x!==id);
  if(state.focusedId===id)state.focusedId=null;
  state.selected=null;closeDrawer();
  const changedAnchor=!state.selectedIds.length || !state.graph || !state.graphHash || state.graphHash!==anchorRun()?.graph_sha256;
  updateSelectors();
  if(!state.selectedIds.length){state.graph=null;state.details.clear();renderChapterList();displayNoRuns();return;}
  await loadCurrent(changedAnchor);
}
function displayNoRuns(){
 $('graphEmpty').classList.remove('is-hidden');
 $('graphEmpty').innerHTML='<strong>Choose a model</strong>';
 $('graphEdges').replaceChildren();$('graphNodes').replaceChildren();$('canvasLegend').innerHTML='<summary class="legend-title">Models</summary>';
 $('storyContent').innerHTML='<div class="story-empty"><strong>Choose a model</strong></div>';$('decisionStrip').replaceChildren();renderStoryToolbar(null);
 $('chapterList').replaceChildren();
 state.rendered=null;state.chapter=null;setCharacterTheme(null);
}
async function refreshRuns({reselect=false}={}){
 if(state.busyRefresh)return;
 state.busyRefresh=true;
 try{
   const results=(await api('/api/runs')).runs||[];
   state.runs=results;
   state.selectedIds=state.selectedIds.filter(id=>runById(id));
   if(!state.selectionHydrated && results.length){
     // Open on real runs that recorded decisions, not synthetic previews or runs that never started.
     const played=results.filter(r=>r.choices>0);
     const base=played.find(r=>!r.synthetic)||played[0]||results[0];
     const matching=results.filter(r=>r.graph_sha256&&r.graph_sha256===base.graph_sha256);
     state.selectedIds=(matching.some(r=>r.choices>0)?matching.filter(r=>r.choices>0):matching)
       .sort(byRunOrder).slice(0,MAX_VISIBLE_RUNS).map(r=>r.id);
     state.selectionHydrated=true;
   }
   if(!results.length){state.selectedIds=[];state.graph=null;state.details.clear();updateSelectors();displayNoRuns();return;}
   updateSelectors();
   if(!state.selectedIds.length){displayNoRuns();return;}
   if(reselect||!state.graph||!state.details.size)await loadCurrent(true);
   else if(activeRuns().some(r=>r.status==='running'||state.details.get(r.id)?.run.status!==r.status))await refreshEventsInPlace();
 }catch(error){toast('Could not load runs: '+error.message);}
 finally{state.busyRefresh=false;}
}
async function loadCurrent(fit=true){
 const anchor=anchorRun();if(!anchor)return;
 const request=++state.requestVersion;
 try{
   const selected=activeRuns();
   if(selected.some(r=>!compatible(r,anchor)))throw new Error('All overlaid runs must share a story graph');
   const shouldFetchGraph=!state.graph||state.graphHash!==anchor.graph_sha256;
   const [graph, ...details]=await Promise.all([
     shouldFetchGraph?api(`/api/runs/${encodeURIComponent(anchor.id)}/flowchart`):Promise.resolve(state.graph),
     ...selected.map(r=>api(`/api/runs/${encodeURIComponent(r.id)}`))
   ]);
   if(request!==state.requestVersion)return;
   const switched=state.graphHash!==anchor.graph_sha256;
   state.graph=graph;state.graphHash=anchor.graph_sha256;
   state.details=new Map(selected.map((run,i)=>[run.id,details[i]]));
   const chapters=graph.chapters||[];
   const hashChapter=new URLSearchParams(location.hash.replace(/^#/,'')).get('chapter');
   if(switched||!chapters.includes(state.chapter)){
     state.chapter=hashChapter&&chapters.includes(hashChapter)?hashChapter:
       (details[0]?.run.chapters_visited||[]).find(ch=>chapters.includes(ch))||chapters[0]||null;
   }
   renderChapterList();renderChapter(fit);
 }catch(error){if(request!==state.requestVersion)return;toast('Could not load flowchart: '+error.message);$('graphEmpty').classList.remove('is-hidden');$('graphEmpty').innerHTML=`<strong>Flowchart unavailable</strong><p>${esc(error.message)}</p>`;}
}
async function refreshEventsInPlace(){
 const selected=activeRuns();if(!selected.length)return;
 const request=++state.requestVersion;
 try{
  const details=await Promise.all(selected.map(r=>api(`/api/runs/${encodeURIComponent(r.id)}`)));
  if(request!==state.requestVersion)return;
  const changed=selected.some((r,i)=>state.details.get(r.id)?.events.length!==details[i].events.length);
  if(changed){state.details=new Map(selected.map((r,i)=>[r.id,details[i]]));renderChapterList();renderChapter(false);}
 }catch(_){/* Retain last complete snapshot while runs are being written */}
}
function chapters() {return state.graph?.chapters || [];}
function chapterNumber(ch) {
  // Titled graphs have real chapter numbers (such as 30.1); others only have a position.
  if (state.graph?.chapter_info?.[ch]?.title) return ch==='final'?'':ch;
  const pos = chapters().indexOf(ch);
  return String(Math.max(1, pos + 1)).padStart(2,'0');
}
function chapterNumeral(ch,i) {
  if (state.graph?.chapter_info?.[ch]?.title) return ch==='final'?'END':ch;
  return String(i+1).padStart(2,'0');
}
function syncHash() {
  if (location.protocol === 'about:') return;
  const params = new URLSearchParams();
  if (state.chapter) params.set('chapter',state.chapter);
  if (state.view !== 'story') params.set('view',state.view);
  history.replaceState(null,'',location.pathname+location.search+'#'+params.toString());
}
function setView(view) {
  state.view = view;
  const story = view === 'story';
  $('storyView').classList.toggle('is-hidden',!story);
  $('viewerWrap').classList.toggle('is-hidden',story);
  document.querySelectorAll('.flow-only').forEach(el=>el.classList.toggle('is-hidden',story));
  $('viewStory').setAttribute('aria-pressed',String(story));
  $('viewFlow').setAttribute('aria-pressed',String(!story));
  if (story) closeDrawer();
  syncHash();
  renderChapter(true);
}
function renderChapterList() {
  const all = chapters();
  const followed = storyRun(), storyDetail = followed && state.details.get(followed.id);
  const decisionCounts = new Map((storyDetail?.decisions_by_chapter||[]).map(entry=>[entry.chapter,entry.choices]));
  $('chapterList').innerHTML = all.length ? all.map((ch,i) => {
    const reached = decisionCounts.has(ch), character = chapterCharacter(ch);
    return `<button type="button" class="chapter-entry ${state.chapter === ch ? 'active':''} ${followed&&!reached?'not-reached':''}" data-chapter="${esc(ch)}" data-character="${esc(String(character||'').toLowerCase())}" title="${esc(chapterTitle(ch))}" aria-current="${state.chapter===ch?'page':'false'}">
      <span class="chapter-numeral">${esc(chapterNumeral(ch,i))}</span>${typeof portraitThumb==='function'?portraitThumb(character):''}<span class="chapter-name"><b>${esc(chapterTitle(ch))}</b>${character?`<small>${esc(character)}</small>`:''}</span>
    </button>`;}).join('') : '';
  document.querySelectorAll('[data-chapter]').forEach(b => b.addEventListener('click', () => changeChapter(b.dataset.chapter)));
  document.querySelector('.chapter-entry.active')?.scrollIntoView({block:'nearest'});
}
function changeChapter(ch) {
  if (!chapters().includes(ch)) return;
  state.chapter = ch; closeDrawer();
  syncHash();
  renderChapterList(); renderChapter(true);
}
function optionId(parent, option) {return `${parent}::OPTION::${encodeURIComponent(option)}`;}
function modelView(runId){return {run:runById(runId),detail:state.details.get(runId)};}
const nodeTargets = n => n.type === 'choice' ? (n.options||[]).map(o=>o.next)
  : n.type === 'condition' ? [...(n.branches||[]).map(b=>b.next), n.next]
  : n.type === 'route' ? [n.if_true, n.if_false]
  : n.type === 'ending' ? [] : [n.next];
const inboundCache = new WeakMap();
function inboundCounts() {
  // Counted across the whole story, so an entry from another chapter also blocks a merge.
  if (!inboundCache.has(state.graph)) {
    const counts = new Map();
    for (const n of Object.values(state.graph.nodes))
      for (const target of new Set(nodeTargets(n).filter(Boolean))) counts.set(target,(counts.get(target)||0)+1);
    inboundCache.set(state.graph,counts);
  }
  return inboundCache.get(state.graph);
}
/* A scene joins the next one only if that is its sole exit and the next scene's sole
 * entrance. Nothing can branch inside such a run, so merging cannot hide a branch. */
function straightSceneRuns(originals) {
  const inbound = inboundCounts(), byId = new Map(originals.map(n=>[n.id,n]));
  const scenes = originals.filter(n=>n.type==='scene'), follows = new Map(), hasPrevious = new Set();
  for (const n of scenes) {
    const next = byId.get(n.next);
    if (next && next !== n && next.type === 'scene' && inbound.get(next.id) === 1) {
      follows.set(n.id,next); hasPrevious.add(next.id);
    }
  }
  const runs = [], grouped = new Set();
  for (const n of scenes) {
    if (hasPrevious.has(n.id)) continue;
    const run = [n];
    while (follows.has(run.at(-1).id)) run.push(follows.get(run.at(-1).id));
    run.forEach(member=>grouped.add(member.id));
    runs.push(run);
  }
  // A closed loop of scenes has no first scene, so its scenes stay separate.
  for (const n of scenes) if (!grouped.has(n.id)) runs.push([n]);
  return runs;
}
function sceneRunLabel(run) {
  const headings = [...new Set(run.map(n=>n.heading).filter(Boolean))];
  if (!headings.length) return shortTitle(run[0].id,26);
  return headings.length === 1 ? headings[0] : `${headings[0]} → ${headings.at(-1)}`;
}
function nodeDialogueMarkup(items) {
  return items.map(item => {
    if (item.kind === 'heading') return `<b class="node-section">${esc(item.text)}</b>`;
    if (item.kind === 'line') return `<p><b>${esc(item.speaker||'Unknown')}:</b> ${esc(item.text)}</p>`;
    if (item.kind === 'clue') return `<p class="node-clue"><b>Inspected${item.title?`: ${esc(item.title)}`:''}.</b> ${esc((item.lines||[]).join(' · ').replaceAll(' | ',', '))}</p>`;
    return `<p><i>${esc(item.text)}</i></p>`;
  }).join('');
}
function buildChapterGraph(chapter) {
  const originals = Object.values(state.graph?.nodes || {}).filter(n => n.chapter === chapter);
  const nodes = new Map(), edges = [], groupOf = new Map();
  const addEdge = (from, to, type='normal', id='') => {
    if (!to) return;
    edges.push({from, to, type, id});
  };
  for (const run of straightSceneRuns(originals)) {
    const head = run[0];
    // The first heading is already the node's title.
    const items = buildStoryItems(run.map(n=>({...n,type:'scene'}))).filter((item,i)=>!(i===0&&item.kind==='heading'));
    run.forEach(member=>groupOf.set(member.id,head.id));
    nodes.set(head.id,{id:head.id,parent:null,type:'scene',originalType:'scene',label:sceneRunLabel(run),node:head,
                       members:run,items,width:items.length?SCENE_NODE_WIDTH:190,height:60});
    addEdge(head.id,run.at(-1).next,'normal');
  }
  for (const n of originals) {
    if (n.type === 'scene') continue;
    const type = n.type === 'condition' || n.type === 'route' ? 'junction'
               : n.type === 'chapter_exit' ? 'exit' : n.type;
    const label = n.heading || ({choice:'CHOICE',condition:'CONDITION',route:'STORY BRANCH',chapter_exit:'CHAPTER COMPLETE',ending:'STORY END'}[n.type] || shortTitle(n.id,26));
    nodes.set(n.id, {id:n.id, parent:null, type, originalType:n.type, label, node:n,
                     width: n.type === 'choice' ? 180 : n.type === 'condition'||n.type === 'route' ? 135 : 190,
                     height: n.type === 'condition'||n.type === 'route' ? 39 : 60});
  }
  for (const n of originals) {
    if (n.type === 'scene') continue;
    if (n.type === 'choice') {
      for (const o of n.options || []) {
        const id = optionId(n.id, o.id);
        nodes.set(id,{id,parent:n.id,optionId:o.id,type:'option',originalType:'option',label:o.label||o.id,
                      node:o,width:188,height:54});
        addEdge(n.id,id,'choice-option',o.id);
        addEdge(id,o.next,'option-next',o.id);
      }
    } else if (n.type === 'condition') {
      for (const [i,b] of (n.branches||[]).entries()) addEdge(n.id,b.next,'condition',String(i));
      addEdge(n.id,n.next,'default','default');
    } else if (n.type === 'route') {
      addEdge(n.id,n.if_true,'route','true'); addEdge(n.id,n.if_false,'route','false');
    } else if (n.type !== 'ending') addEdge(n.id,n.next,'normal');
  }
  // Keep exits to other chapters as clickable portals. Do not discard any
  // edges merely because their destination belongs to another chapter.
  for (const e of edges) {
    e.to = groupOf.get(e.to) || e.to;
    if (nodes.has(e.to)) continue;
    const destination = state.graph?.nodes?.[e.to];
    if (!destination) continue;
    const portalId = `PORTAL::${e.to}`;
    if (!nodes.has(portalId)) {
      const chapterName = destination.chapter || 'END';
      nodes.set(portalId, {id:portalId, type:'portal', originalType:'portal',
        label:`CONTINUES · ${chapterName}`, destination:e.to,
        destinationChapter:destination.chapter || null,
        width:188, height:54});
    }
    e.to = portalId;
  }
  const internal = edges.filter(e => nodes.has(e.from) && nodes.has(e.to));
  const sourceSteps = originals.reduce((sum,n)=>sum+1+(n.options||[]).length,0);
  const merged = groupOf.size > [...nodes.values()].filter(n=>n.members).length;
  return {nodes, edges:internal, chapter, groupOf, sourceSteps, merged};
}
function computePath(view, chapter, graph) {
  const groupId = id => graph.groupOf.get(id) || id;
  const visited = new Set(), traversed = new Set(), byId = new Map(), counts = new Map();
  const events = view?.detail?.events || [];
  for (let i = 0; i < events.length; i++) {
    const ev = events[i], nid = groupId(ev.node_id);
    if (ev.chapter !== chapter || !ev.node_id) continue;
    visited.add(nid);
    if (!byId.has(nid)) byId.set(nid,[]);
    byId.get(nid).push(ev);
    counts.set(nid,(counts.get(nid)||0)+1);
    const next = events[i+1];
    const nextId = next?.chapter === chapter ? groupId(next.node_id) :
      next?.node_id && state.graph?.nodes?.[next.node_id] ? `PORTAL::${next.node_id}` : null;
    if (ev.type === 'decision') {
      const opt = optionId(nid, ev.choice_id);
      visited.add(opt);
      if (!byId.has(opt)) byId.set(opt,[]);
      byId.get(opt).push(ev);
      traversed.add(`${nid}\u0000${opt}`);
      if (nextId) {traversed.add(`${opt}\u0000${nextId}`); if(nextId.startsWith('PORTAL::')) {visited.add(nextId); byId.set(nextId,[ev]);}}
    } else if (nextId && nextId !== nid) {
      traversed.add(`${nid}\u0000${nextId}`);
      if(nextId.startsWith('PORTAL::')) {visited.add(nextId); byId.set(nextId,[ev]);}
    }
  }
  return {visited,traversed,byId,counts};
}
function layoutGraph(graph) {
  const all = Array.from(graph.nodes.values()), byId = graph.nodes;
  const outgoing = new Map(all.map(n=>[n.id,[]])), incoming = new Map(all.map(n=>[n.id,[]]));
  for (const e of graph.edges) {outgoing.get(e.from).push(e.to);incoming.get(e.to).push(e.from);}
  const indegree = new Map(all.map(n=>[n.id,incoming.get(n.id).length]));
  const index = new Map(all.map((n,i)=>[n.id,i]));
  const queue = all.filter(n=>indegree.get(n.id)===0).map(n=>n.id);
  const topo = [], ranks = new Map(all.map(n=>[n.id,0]));
  while(queue.length) {
    const id = queue.shift(); topo.push(id);
    for(const to of outgoing.get(id)) {
      ranks.set(to,Math.max(ranks.get(to),ranks.get(id)+1));
      indegree.set(to,indegree.get(to)-1);
      if(indegree.get(to)===0) queue.push(to);
    }
  }
  // Cyclic imported graphs: display the remaining nodes without an infinite walk.
  for(const n of all) if(!topo.includes(n.id)) topo.push(n.id);
  const maxRank = Math.max(0,...ranks.values());
  const layers = Array.from({length:maxRank+1},()=>[]);
  for(const id of topo) layers[ranks.get(id)].push(id);
  // Consecutive forward / backward barycentric sweeps minimize accidental crossings.
  for(let pass=0; pass<4;pass++) {
    for(const backward of [false,true]) {
      const columns = backward ? [...layers.keys()].reverse() : [...layers.keys()];
      for (const rank of columns) {
        if (rank === 0 && !backward || rank === layers.length-1 && backward) continue;
        const neighborList = backward ? outgoing : incoming;
        const comparator = (a,b) => {
          const score = id => {
            const arr = neighborList.get(id).filter(x=>ranks.get(x)===(backward?rank+1:rank-1));
            if(!arr.length) return Infinity;
            const otherLayer = layers[backward?rank+1:rank-1];
            return arr.reduce((s,x)=>s+otherLayer.indexOf(x),0)/arr.length;
          };
          return score(a)-score(b) || index.get(a)-index.get(b);
        };
        layers[rank].sort(comparator);
      }
    }
  }
  // Nodes vary in size now that they hold dialogue, so each column fits its own nodes.
  const gapX = 62, gapY = 42, left = 115, top = 110;
  const columnHeight = layer => layer.reduce((sum,id)=>sum+byId.get(id).height+gapY,0)-gapY;
  const contentHeight = Math.max(0,...layers.map(columnHeight));
  let x = left;
  for(const layer of layers) {
    let y = top+(contentHeight-columnHeight(layer))/2;
    for(const id of layer) {
      const n=byId.get(id); n.x=x; n.y=y; y+=n.height+gapY;
    }
    x += Math.max(0,...layer.map(id=>byId.get(id).width))+gapX;
  }
  return {width:x-gapX+left,height:Math.max(420,top*2+contentHeight),rankCount:layers.length};
}
/* A long jump that would cross the boxes in between runs instead through the empty lane
 * above or below them, whichever is nearer, with rounded corners in the column gaps. */
const EDGE_CLEARANCE = 8, LANE_MARGIN = 22, CORNER = 12;
function curveHitsNodes([x0,y0,c1x,c1y,c2x,c2y,x3,y3], nodes) {
  for (let i = 1; i < 40; i++) {
    const t = i/40, u = 1-t;
    const x = u*u*u*x0 + 3*u*u*t*c1x + 3*u*t*t*c2x + t*t*t*x3;
    const y = u*u*u*y0 + 3*u*u*t*c1y + 3*u*t*t*c2y + t*t*t*y3;
    if (nodes.some(n=>x>n.x-EDGE_CLEARANCE&&x<n.x+n.width+EDGE_CLEARANCE&&y>n.y-EDGE_CLEARANCE&&y<n.y+n.height+EDGE_CLEARANCE)) return true;
  }
  return false;
}
function detourMarkup(x1, y1, x2, y2, between, offset) {
  const top = Math.min(...between.map(n=>n.y)) - LANE_MARGIN + offset;
  const bottom = Math.max(...between.map(n=>n.y+n.height)) + LANE_MARGIN + offset;
  const lane = Math.abs(y1-top)+Math.abs(y2-top) <= Math.abs(y1-bottom)+Math.abs(y2-bottom) ? top : bottom;
  // The vertical runs sit in the gaps just before the first and after the last box in between.
  const xa = (x1 + Math.min(...between.map(n=>n.x))) / 2;
  const xb = (x2 + Math.max(...between.map(n=>n.x+n.width))) / 2;
  const turn = (fromY, toY) => Math.sign(toY-fromY) * Math.min(CORNER, Math.abs(toY-fromY)/2);
  const down = turn(y1, lane), up = turn(lane, y2);
  return `M ${x1} ${y1} L ${xa-CORNER} ${y1} Q ${xa} ${y1} ${xa} ${y1+down}`
    + ` L ${xa} ${lane-down} Q ${xa} ${lane} ${xa+CORNER} ${lane}`
    + ` L ${xb-CORNER} ${lane} Q ${xb} ${lane} ${xb} ${lane+up}`
    + ` L ${xb} ${y2-up} Q ${xb} ${y2} ${xb+CORNER} ${y2} L ${x2} ${y2}`;
}
function edgeMarkup(e, graph, offset=0) {
  const a=graph.nodes.get(e.from),b=graph.nodes.get(e.to);
  if (!a || !b) return '';
  const x1=a.x+a.width, y1=a.y+a.height/2+offset;
  const x2=b.x, y2=b.y+b.height/2+offset;
  if (x2 >= x1) {
    const bend = Math.max(20, (x2-x1)*.52);
    const curve = `M ${x1} ${y1} C ${x1+bend} ${y1}, ${x2-bend} ${y2}, ${x2} ${y2}`;
    const between = [...graph.nodes.values()].filter(n=>n!==a&&n!==b&&n.x>=x1&&n.x+n.width<=x2);
    if (!between.length || !curveHitsNodes([x1,y1,x1+bend,y1,x2-bend,y2,x2,y2], between)) return curve;
    return detourMarkup(x1, y1, x2, y2, between, offset);
  }
  return `M ${x1} ${y1} C ${x1+62} ${y1}, ${x1+62} ${y1+55}, ${x1+13} ${y1+55} L ${x2-13} ${y2+55} C ${x2-51} ${y2+55}, ${x2-51} ${y2}, ${x2} ${y2}`;
}
function svgPath(d, cls) {
  const el=document.createElementNS(svgNS,'path');el.setAttribute('d',d);el.setAttribute('class',cls);return el;
}
function createLogo(node, view) {
  const btn=document.createElement('button'), run=view.run, color=routeColor(run);
  btn.type='button';btn.className=`node-model-button provider-${providerOf(run)}`;
  btn.style.setProperty('--badge-color',color);btn.dataset.runId=run.id;
  btn.title=`${modelLabel(run)} — inspect recorded explanation at ${node.label}`;
  btn.setAttribute('aria-label',btn.title);
  btn.innerHTML=modelIcon(providerOf(run));
  btn.addEventListener('click',e=>{e.stopPropagation();inspect(node.id,run.id);});
  return btn;
}
/* The provider's mark at the middle of a route line, so same-colored routes stay apart.
 * Several models on one line get their marks stacked in a column, never on top of each other. */
const ROUTE_LOGO_MIN_LENGTH = 90, ROUTE_LOGO_SIZE = 14, ROUTE_LOGO_STEP = ROUTE_LOGO_SIZE + 6;
function routeLogo(path, run, shift=0) {
  const length=path.getTotalLength?.()||0;
  if(length<ROUTE_LOGO_MIN_LENGTH)return null;
  const middle=path.getPointAtLength(length/2), half=ROUTE_LOGO_SIZE/2, x=middle.x, y=middle.y+shift;
  const g=document.createElementNS(svgNS,'g');
  g.setAttribute('class','route-logo');g.setAttribute('aria-hidden','true');
  const disc=document.createElementNS(svgNS,'circle');
  disc.setAttribute('cx',x);disc.setAttribute('cy',y);disc.setAttribute('r',half+2);disc.style.stroke=routeColor(run);
  g.appendChild(disc);
  const src=modelIcon(providerOf(run)).match(/src="([^"]+)"/)?.[1];
  if(src){
    const img=document.createElementNS(svgNS,'image');
    img.setAttribute('href',src);img.setAttribute('x',x-half);img.setAttribute('y',y-half);
    img.setAttribute('width',ROUTE_LOGO_SIZE);img.setAttribute('height',ROUTE_LOGO_SIZE);
    g.appendChild(img);
  }
  return g;
}
function drawGraph(graph, paths) {
  const world=$('graphWorld'), nodesEl=$('graphNodes'), edgesEl=$('graphEdges');
  const views=activeViews();
  // Idle nodes show only their title; model logos stack in a column at the right edge,
  // so a node grows just tall enough to keep every logo visible.
  for(const node of graph.nodes.values()) {
    const count=paths.filter(x=>x.path.visited.has(node.id)).length;
    node.height=Math.max(node.height, count*NODE_LOGO_STEP+NODE_LOGO_PADDING);
  }
  const bounds=layoutGraph(graph);
  world.style.width=bounds.width+'px';world.style.height=bounds.height+'px';
  nodesEl.style.width=bounds.width+'px';nodesEl.style.height=bounds.height+'px';
  edgesEl.setAttribute('width',String(bounds.width));edgesEl.setAttribute('height',String(bounds.height));
  edgesEl.setAttribute('viewBox',`0 0 ${bounds.width} ${bounds.height}`);
  edgesEl.replaceChildren();nodesEl.replaceChildren();
  for(const edge of graph.edges) {
    const d=edgeMarkup(edge,graph);
    edgesEl.appendChild(svgPath(d,'edge-path'));
    const users=paths.filter(x=>x.path.traversed.has(`${edge.from}\u0000${edge.to}`));
    const step=Math.min(3,Math.max(1.5,30/Math.max(1,users.length)));
    users.forEach((view,i)=>{
      const offset=(i-(users.length-1)/2)*step;
      const path=svgPath(edgeMarkup(edge,graph,offset),'edge-path route-overlay');
      path.style.stroke=routeColor(view.run);
      path.classList.add(`provider-${providerStyle(view.run)}`);
      path.setAttribute('data-run-id',view.run.id);
      path.setAttribute('aria-label',`${modelLabel(view.run)} took this branch`);
      const title=document.createElementNS(svgNS,'title');title.textContent=modelLabel(view.run);path.appendChild(title);
      edgesEl.appendChild(path);
      const logo=routeLogo(path,view.run,(i-(users.length-1)/2)*ROUTE_LOGO_STEP-offset);
      if(logo)edgesEl.appendChild(logo);
    });
  }
  for(const node of graph.nodes.values()) {
    const users=paths.filter(view=>view.path.visited.has(node.id));
    const n=document.createElement('div');
    // Exploration Choices and key inspect scenes carry their own marks (story-marks.css).
    const exploration=Boolean(node.node?.exploration), hasKey=Boolean(node.members?.some(member=>member.key));
    n.className=['flow-node',`kind-${node.type}`,users.length?'visited':'',state.selected?.id===node.id?'selected':'',exploration?'is-exploration':'',hasKey?'has-key':''].filter(Boolean).join(' ');
    n.style.left=node.x+'px';n.style.top=node.y+'px';n.style.width=node.width+'px';n.style.height=node.height+'px';
    n.style.setProperty('--node-accent',users.length?routeColor(users[0].run):'#cad8df');
    n.role='button';n.tabIndex=0;n.dataset.nodeId=node.id;
    if(node.type!=='portal')n.dataset.moment=node.parent||node.members?.[0]?.id||node.id;
    n.dataset.visitedCount=String(users.length);
    n.setAttribute('aria-label',node.label);
    const label=document.createElement('span');label.className='node-label';label.textContent=node.label;n.appendChild(label);
    if(node.items?.length){
      const dialogue=document.createElement('div');dialogue.className='node-dialogue';
      dialogue.innerHTML=nodeDialogueMarkup(node.items);n.appendChild(dialogue);
    }
    const left=document.createElement('i');left.className='node-socket left';left.setAttribute('aria-hidden','true');n.appendChild(left);
    const right=document.createElement('i');right.className='node-socket right';right.setAttribute('aria-hidden','true');n.appendChild(right);
    if(node.type==='choice'||node.type==='junction'){
      const mini=document.createElement('span');mini.className='node-mini';
      if(exploration){mini.innerHTML=`<span class="node-glyph">${MAGNIFIER}</span>EXPLORATION`;mini.title='Exploration Choice: how thoroughly to search';}
      else mini.textContent=node.type==='choice'?'DECISION':'STATE CHECK';
      n.appendChild(mini);
    }
    if(users.length){
      n.classList.add('has-logos');
      const logos=document.createElement('div');logos.className='node-logos';
      for(const view of users)logos.appendChild(createLogo(node,view));
      n.appendChild(logos);
    }
    n.addEventListener('click',e=>{
      e.stopPropagation();
      if(node.type==='portal'&&node.destinationChapter&&chapters().includes(node.destinationChapter))changeChapter(node.destinationChapter);
      else showMomentInStory(node,users.map(view=>view.run.id));
    });
    n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();n.click();}});
    nodesEl.appendChild(n);
  }
  return bounds;
}
/* Opens the Story at a Flowchart node, following a Run that passed through it. A node no
 * selected Run reached has no Story to show, so its script opens beside the Flowchart. */
function showMomentInStory(node,visitorIds){
 const followed=storyRun()?.id, runId=visitorIds.includes(followed)?followed:visitorIds[0];
 if(!runId){inspect(node.id,activeRuns()[0]?.id);return;}
 const events=state.rendered?.paths.find(p=>p.run.id===runId)?.path.byId.get(node.id)||[];
 const moments=node.members?node.members.map(member=>member.id):[node.parent||node.id];
 state.pendingMoment={moments,index:events[0]?.index??Infinity};
 state.storyRunId=runId;
 setView('story');renderChapterList();
}
function renderChapter(fit=true){
 if(!state.graph||!state.chapter)return;
 const chapter=state.chapter;
 $('chapterIndexLabel').textContent=chapterNumber(chapter)?`Chapter ${chapterNumber(chapter)}`:'Endings';
 setCharacterTheme(chapterCharacter(chapter));
 emitScene();
 $('chapterTitle').textContent=chapterTitle(chapter);
 if(state.view==='story'){state.rendered=null;renderStory({keepScroll:!fit});return;}
 renderFlowchart(fit);
}
function renderFlowchart(fit=true){
 renderStoryToolbar(storyRun());
 const chapter=state.chapter, views=activeViews(), graph=buildChapterGraph(chapter);
 const paths=views.map(v=>({...v,path:computePath(v,chapter,graph)}));
 $('chapterSubtitle').textContent=chapterCharacter(chapter)||'';
 const notice=$('graphNotice');notice.classList.toggle('is-hidden',state.graph.complete);
 if(!state.graph.complete)notice.textContent='Story graph missing for this run.';
 const legend=$('canvasLegend');
 legend.innerHTML=`<summary class="legend-title">Models</summary><div class="legend-runs">${views.map(v=>`<div class="legend-line" data-focus-id="${esc(v.run.id)}" role="button" tabindex="0" title="Click to focus ${esc(modelLabel(v.run))}"><svg class="legend-dash" viewBox="0 0 24 4" aria-hidden="true"><line class="route-overlay provider-${providerStyle(v.run)}" x1="0" y1="2" x2="24" y2="2" style="stroke:${routeColor(v.run)}"/></svg><span class="legend-model">${modelIcon(providerOf(v.run))}</span><span class="legend-run-name">${esc(v.run.model)}</span></div>`).join('')}</div>`;
 if(!state.graph.complete){
   $('graphEdges').replaceChildren();$('graphNodes').replaceChildren();
   $('graphEmpty').classList.remove('is-hidden');
   $('graphEmpty').innerHTML='<strong>Story graph missing</strong>';
   state.rendered=null;return;
 }
 $('graphEmpty').classList.toggle('is-hidden',graph.nodes.size>0);
 if(!graph.nodes.size)$('graphEmpty').innerHTML='<strong>Nothing here yet</strong>';
 const bounds=drawGraph(graph,paths);
 state.rendered={graph,paths,bounds};
 setupRunFocus();applyRunFocus();
 if(fit)requestAnimationFrame(openChapterView);else applyTransform();
 if(state.selected&&!graph.nodes.has(state.selected.id))closeDrawer();
 emitFlowScene(state.selected?.id);
}
function applyTransform(){ $('graphWorld').style.transform=`translate3d(${state.panX}px,${state.panY}px,0) scale(${state.scale})`; }
function openChapterView(){
  // Long chapters are unreadable when fitted, so start at a legible zoom on the first node.
  if(!state.rendered)return;
  state.viewTouched=false;
  fitGraph();
  if(state.scale>=MIN_READABLE_FIT)return;
  const nodes=[...state.rendered.graph.nodes.values()], first=nodes.reduce((a,b)=>b.x<a.x?b:a,nodes[0]);
  if(!first)return;
  const box=$('viewport').getBoundingClientRect();
  state.scale=OPENING_ZOOM;
  state.panX=48-first.x*state.scale;
  state.panY=box.height/2-(first.y+first.height/2)*state.scale;
  applyTransform();
}
function fitGraph(){
  if(!state.rendered) return;
  const viewport=$('viewport').getBoundingClientRect();
  if(!viewport.width||!viewport.height)return;
  const b=state.rendered.bounds;
  const xPad=105,yPad=105;
  state.scale=clamp(Math.min((viewport.width-xPad)/b.width,(viewport.height-yPad)/b.height),.18,1.28);
  state.panX=(viewport.width-b.width*state.scale)/2;
  state.panY=(viewport.height-b.height*state.scale)/2;
  applyTransform();
}
function centerSelectedNode({glide=false}={}) {
  if (!state.selected || !state.rendered) return;
  const node=state.rendered.graph.nodes.get(state.selected.id);
  if(!node)return;
  state.viewTouched=true;
  const box=$('viewport').getBoundingClientRect();
  state.scale=clamp(Math.max(.72,state.scale),.16,1.45);
  state.panX=box.width*.44-(node.x+node.width/2)*state.scale;
  state.panY=box.height*.50-(node.y+node.height/2)*state.scale;
  const world=$('graphWorld');
  if(glide&&!matchMedia('(prefers-reduced-motion: reduce)').matches){
    world.classList.add('is-gliding');clearTimeout(state.glideTimer);
    state.glideTimer=setTimeout(()=>world.classList.remove('is-gliding'),700);
  }
  applyTransform();
}
function zoom(factor,clientX,clientY){
  const vp=$('viewport').getBoundingClientRect();
  const x=clientX===undefined?vp.width/2:clientX-vp.left;
  const y=clientY===undefined?vp.height/2:clientY-vp.top;
  state.viewTouched=true;
  const old=state.scale,next=clamp(old*factor,.16,2.2);
  state.panX=x-(x-state.panX)/old*next;
  state.panY=y-(y-state.panY)/old*next;
  state.scale=next;applyTransform();
}
function closeDrawer(){state.selected=null;if(state.view==='flow')emitFlowScene(null);$('reasoningDrawer').classList.add('is-hidden');document.querySelectorAll('.flow-node.selected').forEach(n=>n.classList.remove('selected'));}
function fmtValue(v) {return typeof v==='string'?v:JSON.stringify(v);}
function renderInspectorShell(node,runId,view){
 const run=view.run, color=routeColor(run),provider=providerOf(run);
 $('reasoningDrawer').style.setProperty('--inspect-color',color);
 return `<div class="inspect-model-line"><span class="inspect-logo" style="border-color:${color};color:${color}">${modelIcon(provider)}</span><div><div class="inspect-model-name">${esc(modelName(provider))}</div><div class="inspect-run-name">${esc(run?.model||'Unknown')} · ${esc(run?.name||'')}</div></div></div>
  ${run?.synthetic?'<p class="inspect-note synthetic-disclaimer">Synthetic preview</p>':''}
    <h2 class="inspect-title">${esc(node.label)}</h2>`;
}
async function inspect(nodeId,runId,{glide=false}={}){
 const rendered=state.rendered?.graph;
 const node=rendered?.nodes.get(rendered.groupOf.get(nodeId)||nodeId);if(!node)return;
 nodeId=node.id;
 const view=modelView(runId), path=state.rendered?.paths.find(p=>p.run.id===runId)?.path;
 const events=path?.byId.get(nodeId)||[];
 const selectedEvent=events.findLast?.(e=>e.type==='decision')||events[events.length-1];
 state.selected={id:nodeId,runId};emitFlowScene(nodeId);
 $('reasoningDrawer').classList.remove('is-hidden');requestAnimationFrame(()=>centerSelectedNode({glide}));
 document.querySelectorAll('.flow-node').forEach(el=>{
  el.classList.toggle('selected',el.dataset.nodeId===nodeId);
  el.classList.toggle('moment-focus',glide&&el.dataset.nodeId===nodeId);
 });
 if(!selectedEvent){
  $('drawerContent').innerHTML=renderInspectorShell(node,runId,view)+`<div class="nondecision-msg">Not taken by this model.</div>${sceneScriptSection(node)}`;
  return;
 }
 $('drawerContent').innerHTML=renderInspectorShell(node,runId,view)+'';
 const marker=state.selected;
 try{
  const raw=await api(`/api/runs/${encodeURIComponent(runId)}/events/${selectedEvent.index}`);
  if(state.selected!==marker)return;
  if(raw.type==='decision')renderDecisionInspector(node,raw,runId,view);
  else renderSceneInspector(node,raw,runId,view);
 }catch(err){if(state.selected===marker)$('drawerContent').innerHTML=renderInspectorShell(node,runId,view)+`<div class="nondecision-msg">${esc(err.message)}</div>`;}
}
function renderDecisionInspector(node,ev,runId,view){
 const input=ev.input||{},output=ev.output||{},history=input.entire_decision_history||[];
 const options=input.available_choices||[],selectedOption=options.find(o=>o.id===output.choice_id);
 const before=ev.flags_before||{},after=ev.flags_after||{};
 const changes=Array.from(new Set([...Object.keys(before),...Object.keys(after)]))
   .filter(k=>JSON.stringify(before[k])!==JSON.stringify(after[k]));
 const color=routeColor(view.run);
 $('drawerContent').innerHTML=renderInspectorShell(node,runId,view)+`
  <p class="inspect-subtitle">${esc(input.current_scene?.description||'')}</p>
  <div class="selected-choice" style="border-left-color:${color}"><div class="selected-label">Chose</div><strong>${esc(selectedOption?.label||ev.label||output.choice_id||'Not recorded')}</strong></div>
  <section class="inspect-section"><h3>Why</h3><p class="rationale">${esc(output.rationale||'—')}</p></section>
  <section class="inspect-section"><h3>Options</h3><div class="option-list">${options.map(o=>`<div class="option-pill ${o.id===output.choice_id?'chosen':''}" style="${o.id===output.choice_id?`border-color:${color}`:''}"><span class="option-symbol" style="${o.id===output.choice_id?`background:${color};border-color:${color}`:''}">✓</span><span>${esc(o.label||o.id)}</span></div>`).join('')}</div></section>
  <section class="inspect-section">${changes.length?`<h3>Consequences</h3>${changes.map(k=>`<div class="state-row"><span class="state-key">${esc(k)}</span><span class="state-before">${esc(fmtValue(before[k]??'—'))}</span><span class="state-after">→ ${esc(fmtValue(after[k]??'—'))}</span></div>`).join('')}`:''}</section>
  <section class="inspect-section">${history.length?`<h3>Earlier</h3>${history.slice(-10).map(h=>`<div class="inspect-history"><strong>${esc(h.scene||h.choice_key||'')} · ${esc(h.label||'')}</strong><p>${esc(h.rationale||'')}</p></div>`).join('')}`:''}</section>
  <section class="inspect-section"><details class="inspect-disclosure"><summary>Prompt</summary><pre>${esc(JSON.stringify({system_prompt:ev.system_prompt,input,output},null,2))}</pre></details></section>`;
}
function sceneScriptSection(node){
 if(!node.members)return '';
 const items=buildStoryItems(node.members.map(n=>({...n,type:'scene'})));
 if(items.every(item=>item.kind==='heading'))return '';
 const context={character:chapterCharacter(state.chapter)};
 return `<section class="inspect-section inspect-script">${items.map(item=>renderItem(item,context)).join('')}</section>`;
}
function renderSceneInspector(node,ev,runId,view){
 const data=ev.visible_to_agent||{};
 const preceding=(view.detail?.decisions||[]).filter(d=>d.index<ev.index).at(-1);
 const prior=preceding?`<section class="inspect-section"><h3>Previous decision</h3><div class="selected-choice" style="border-left-color:${routeColor(view.run)}"><div class="selected-label">${esc(preceding.heading||'')}</div><strong>${esc(preceding.label||preceding.choice_id)}</strong></div><p class="rationale">${esc(preceding.rationale||'')}</p></section>`:'';
 $('drawerContent').innerHTML=renderInspectorShell(node,runId,view)+`
  ${node.members?'':`<p class="inspect-subtitle">${esc(data.description||ev.description||node.node.description||'')}</p>`}
  ${sceneScriptSection(node)}
${prior}`;
}
function setupInteractions(){
 // The background follows the hovered node, else the selected one.
 $('graphNodes').addEventListener('mouseover',e=>{const n=e.target.closest('.flow-node');if(n)emitFlowScene(n.dataset.nodeId);});
 $('graphNodes').addEventListener('mouseleave',()=>emitFlowScene(state.selected?.id));
 $('pickerToggle').addEventListener('click',e=>{e.stopPropagation();state.pickerOpen=!state.pickerOpen;updateSelectors();if(state.pickerOpen)$('searchRuns').focus();});
 $('pickerPanel').addEventListener('click',e=>e.stopPropagation());
 document.addEventListener('click',e=>{if(state.pickerOpen&&!e.target.closest('#pickerContainer')){state.pickerOpen=false;updateSelectors();}});
 $('searchRuns').addEventListener('input',e=>{state.search=e.target.value;renderPickerList();});
 $('selectAllRuns').addEventListener('click',async()=>{
  const all=selectAllCandidates();if(!all.length)return;
  const hadAnchor=Boolean(anchorRun());
  state.selectedIds=all.slice(0,MAX_VISIBLE_RUNS);
  if(all.length>MAX_VISIBLE_RUNS)toast('Showing six models at a time.');
  updateSelectors();await loadCurrent(!hadAnchor);
 });
 $('clearRuns').addEventListener('click',async()=>{state.focusedId=null;state.selectedIds=[];state.graph=null;state.details.clear();state.selected=null;closeDrawer();updateSelectors();renderChapterList();displayNoRuns();});
 const fitToButton=()=>{fitGraph();state.viewTouched=true;};
 $('zoomIn').addEventListener('click',()=>zoom(1.2));
 $('zoomOut').addEventListener('click',()=>zoom(1/1.2));
 $('zoomReset').addEventListener('click',fitToButton);
 $('closeDrawer').addEventListener('click',closeDrawer);
 document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeDrawer();if(state.pickerOpen){state.pickerOpen=false;updateSelectors();}}});
 const vp=$('viewport');let drag=null;
 vp.addEventListener('pointerdown',e=>{
  if(e.button!==0||e.target.closest('.flow-node,.canvas-zoombar,.graph-notice,.canvas-legend'))return;
  drag={id:e.pointerId,x:e.clientX,y:e.clientY,px:state.panX,py:state.panY};
  vp.classList.add('dragging');vp.setPointerCapture(e.pointerId);
 });
 vp.addEventListener('pointermove',e=>{
  if(!drag||e.pointerId!==drag.id)return;
  state.viewTouched=true;
  state.panX=drag.px+e.clientX-drag.x;state.panY=drag.py+e.clientY-drag.y;applyTransform();
 });
 const end=e=>{if(drag&&drag.id===e.pointerId){drag=null;vp.classList.remove('dragging');}};
 vp.addEventListener('pointerup',end);vp.addEventListener('pointercancel',end);
 vp.addEventListener('wheel',e=>{
  // Over a node's dialogue, the wheel scrolls the text instead of zooming.
  const dialogue=e.target.closest('.node-dialogue');
  if(dialogue&&dialogue.scrollHeight>dialogue.clientHeight)return;
  e.preventDefault();zoom(e.deltaY<0?1.1:1/1.1,e.clientX,e.clientY);},{passive:false});
 let resizeDebounce;
 new ResizeObserver(()=>{clearTimeout(resizeDebounce);resizeDebounce=setTimeout(()=>{
  // Closing the drawer also resizes the canvas; that must not undo where the viewer has moved to.
  if(state.selected)centerSelectedNode();
  else if(!state.viewTouched)openChapterView();
 },130);}).observe(vp);
}
async function init(){
 setupInteractions();setupStoryInteractions();
 if(new URLSearchParams(location.hash.replace(/^#/,'')).get('view')==='flow'){
  state.view='flow';$('storyView').classList.add('is-hidden');$('viewerWrap').classList.remove('is-hidden');
  $('viewStory').setAttribute('aria-pressed','false');$('viewFlow').setAttribute('aria-pressed','true');
 }else document.querySelectorAll('.flow-only').forEach(el=>el.classList.add('is-hidden'));
 await refreshRuns({reselect:true});setInterval(()=>refreshRuns(),8000);}
init();
