/* Decision Atlas — multi-run chapter flowchart. All branches remain visible.
 * The saved story graph is immutable; any number of run traces may be overlaid.
 */
'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const svgNS = 'http://www.w3.org/2000/svg';
const MIN_READABLE_FIT = 0.5, OPENING_ZOOM = 0.85;
const PALETTE = ['#1596bd','#d36b56','#7756b7','#1b946f','#bb7622','#b34b8a','#2376a4','#a09d29','#815c43','#d25b7b','#3e7b47','#6660aa','#b55329','#607b91','#b34651','#2e8c8a'];
const state = {
  runs: [], selectedIds: [], details: new Map(), graph: null, chapter: null,
  rendered: null, selected: null, scale: 1, panX: 0, panY: 0,
  requestVersion: 0, busyRefresh: false, pickerOpen: false, search: '',
  toastTimer: null, selectionHydrated: false, assignedColors: new Map(), focusedId: null, viewTouched: false,
  view: 'story', readerRunId: null, storyMode: 'full', pendingStoryIndex: null
};
const providerOf = run => String(run?.display_provider || run?.provider || 'unknown').toLowerCase();
const modelName = provider => ({openai:'OpenAI',anthropic:'Anthropic',xai:'xAI',grok:'xAI',google:'Google',gemini:'Google',deepseek:'DeepSeek',mistral:'Mistral',openrouter:'OpenRouter',mock:'Mock agent'})[provider] || provider || 'Other';
const modelLabel = run => `${run?.model || 'Unknown model'} · ${run?.name || 'run'}`;
const niceNum = n => Number(n || 0).toLocaleString('en-US');
const runStatusLabel = run => {
  const count = `${niceNum(run?.choices)} ${run?.choices === 1 ? 'decision' : 'decisions'}`;
  if (run?.status === 'running') return `running, ${count}`;
  if (run?.status === 'stopped') return run.choices ? `stopped early, ${count}` : 'stopped, no decisions';
  return count;
};
const shortTitle = (s, n=44) => String(s||'').length>n ? String(s).slice(0,n-1)+'…' : String(s||'');
function colorFor(run) {
  // Stable identifier across reordering/filtering. Distinct runs from one provider
  // receive different colors; palette cycles only once 16 simultaneous runs exist.
  const id=String(run?.id||''), model=String(run?.model||'');
  let h=2166136261;
  for(const c of `${id}:${model}`){h^=c.charCodeAt(0);h=Math.imul(h,16777619);}
  return PALETTE[(h>>>0)%PALETTE.length];
}
function runById(id) {return state.runs.find(r=>r.id===id) || null;}
function activeRuns(){return state.selectedIds.map(runById).filter(Boolean);}
function activeViews(){return activeRuns().map(run=>({run,detail:state.details.get(run.id)})).filter(x=>x.detail);}
function anchorRun(){return activeRuns()[0]||null;}
function compatible(run,anchor=anchorRun()) {return !anchor || Boolean(run.graph_sha256 && run.graph_sha256===anchor.graph_sha256);}
function routeColor(run){return state.routeColors?.get(run?.id) || colorFor(run);}
function rebalanceColors(){
 // Assign each run once; selecting, removing or reordering runs cannot change
 // an existing run's color. More than 16 runs get distinct extra hues.
 const taken=new Set([...state.assignedColors.values()]);
 for(const run of state.runs){
  if(state.assignedColors.has(run.id))continue;
  let selected=null, start=PALETTE.indexOf(colorFor(run));
  for(let n=0;n<PALETTE.length;n++){
    const color=PALETTE[(start+n)%PALETTE.length];
    if(!taken.has(color)){selected=color;break;}
  }
  if(!selected){
    const extra=state.assignedColors.size-PALETTE.length;
    selected=`hsl(${Math.round((extra*137.508+18)%360)},${extra%2?61:69}%,${extra%3===0?35:45}%)`;
  }
  state.assignedColors.set(run.id,selected);taken.add(selected);
 }
 state.routeColors=state.assignedColors;
}
function applyRunFocus(runId){
 const active=runId||state.focusedId;
 document.querySelectorAll('.route-overlay').forEach(edge=>{
   const match=!active||edge.dataset.runId===active;
   edge.style.opacity=match?'0.97':'0.14';
   edge.style.strokeWidth=match&&active?'4.2':'2.7';
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
     if(state.view==='story'&&el.classList.contains('run-chip')){setReaderRun(el.dataset.focusId);return;}
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
  rebalanceColors();
  $('selectedRunCount').textContent=state.selectedIds.length;
  $('pickerToggle').setAttribute('aria-expanded',String(state.pickerOpen));
  $('pickerPanel').classList.toggle('is-hidden',!state.pickerOpen);
  $('pickerToggle').classList.toggle('on',state.pickerOpen);
  $('selectAllRuns').disabled=!anchorRun();
  const chips=$('selectedRunChips');
  chips.innerHTML=activeRuns().length ? activeRuns().map(run=>`<span class="run-chip" data-focus-id="${esc(run.id)}" role="button" tabindex="0" title="Click to follow this run" style="--run-color:${routeColor(run)}"><span class="run-chip-mark">${modelIcon(providerOf(run))}</span><span class="run-chip-label" title="${esc(modelLabel(run))}">${esc(shortTitle(run.model,24))}</span><button type="button" class="run-chip-remove" data-remove-id="${esc(run.id)}" aria-label="Remove ${esc(modelLabel(run))} from view" title="Remove from view">×</button></span>`).join('') : '<span class="chips-empty">Select a playthrough to see its route</span>';
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
  list.innerHTML=[...groups.entries()].map(([group,runs])=>`<div class="picker-group"><div class="picker-group-heading">${esc(group)} <span>${runs.length}</span></div>${runs.map(run=>{
    const checked=state.selectedIds.includes(run.id),allowed=compatible(run)||checked;
    return `<label class="picker-run ${allowed?'':'incompatible'}"><input type="checkbox" data-run-id="${esc(run.id)}" ${checked?'checked':''} ${allowed?'':'disabled'}><span class="picker-check"></span><span class="picker-run-logo">${modelIcon(providerOf(run))}</span><span class="picker-run-text"><strong>${esc(run.model)}</strong><small>${esc(runStatusLabel(run))}${run.synthetic?' · SYNTHETIC':''}</small></span><span class="picker-color" style="background:${checked?routeColor(run):'#c9d4da'}"></span></label>`;
  }).join('')}</div>`).join('')||'<div class="picker-no-runs">No matching playthroughs.</div>';
  list.querySelectorAll('[data-run-id]').forEach(input=>input.addEventListener('change',()=>toggleRun(input.dataset.runId,input.checked)));
  const anchor=anchorRun();
  $('pickerHelp').textContent=anchor
    ?`Comparisons use one identical story graph. Runs from other graphs are disabled until you clear the selection. ${state.selectedIds.length} selected.`
    :'Choose a run to establish the story graph; then add as many compatible runs as you like.';
}
async function toggleRun(id,enabled){
  const run=runById(id);if(!run)return;
  const selected=state.selectedIds.includes(id);
  if(enabled&&!selected&&!compatible(run)){toast('Choose runs with the same story-graph hash. Clear selection to change stories.');return;}
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
 $('graphEmpty').innerHTML='<div class="empty-glyph">◇</div><strong>Select one or more playthroughs</strong><p>The complete source graph remains in the background while each selected run gets its own colored path.</p>';
 $('graphEdges').replaceChildren();$('graphNodes').replaceChildren();$('canvasLegend').innerHTML='<summary class="legend-title">NO RUNS SELECTED</summary>';
 $('storyContent').innerHTML='<div class="story-empty"><strong>Select a playthrough to read its story</strong></div>';$('decisionStrip').replaceChildren();renderStoryToolbar(null);
 $('chapterList').innerHTML='<div class="sidebar-loading">No chapter selected.</div>';
 $('storyName').textContent='Select recorded runs';$('visibleCount').textContent='0';$('totalCount').textContent='0';
 state.rendered=null;
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
     state.selectedIds=(matching.some(r=>r.choices>0)?matching.filter(r=>r.choices>0):matching).map(r=>r.id);
     state.selectionHydrated=true;
   }
   if(!results.length){state.selectedIds=[];state.graph=null;state.details.clear();updateSelectors();displayNoRuns();return;}
   updateSelectors();
   if(!state.selectedIds.length){displayNoRuns();return;}
   if(reselect||!state.graph||!state.details.size)await loadCurrent(true);
   else if(activeRuns().some(r=>r.status==='running'||state.details.get(r.id)?.run.status!==r.status))await refreshEventsInPlace();
   $('refreshStatus').textContent='UP TO DATE';
 }catch(error){$('refreshStatus').textContent='SYNC FAILED';toast('Could not load runs: '+error.message);}
 finally{state.busyRefresh=false;}
}
async function loadCurrent(fit=true){
 const anchor=anchorRun();if(!anchor)return;
 const request=++state.requestVersion;
 $('refreshStatus').textContent='LOADING';
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
   $('refreshStatus').textContent='UP TO DATE';
 }catch(error){if(request!==state.requestVersion)return;$('refreshStatus').textContent='UNAVAILABLE';toast('Could not load flowchart: '+error.message);$('graphEmpty').classList.remove('is-hidden');$('graphEmpty').innerHTML=`<strong>Flowchart unavailable</strong><p>${esc(error.message)}</p>`;}
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
  $('chapterTotal').textContent = String(all.length).padStart(2,'0');
  $('storyName').textContent = activeViews()[0]?.detail?.run.story_title || state.graph?.metadata?.title || 'Branching narrative';
  const reader = readerRun(), readerDetail = reader && state.details.get(reader.id);
  const decisionCounts = new Map((readerDetail?.decisions_by_chapter||[]).map(entry=>[entry.chapter,entry.choices]));
  $('chapterList').innerHTML = all.length ? all.map((ch,i) => {
    const reached = decisionCounts.has(ch), count = decisionCounts.get(ch)||0, character = chapterCharacter(ch);
    const countLabel = !reader ? '' : reached ? `${count} ${count===1?'decision':'decisions'}` : `Not reached by ${reader.model}`;
    return `<button type="button" class="chapter-entry ${state.chapter === ch ? 'active':''} ${reader&&!reached?'not-reached':''}" data-chapter="${esc(ch)}" title="${esc(chapterTitle(ch))}${countLabel?` · ${esc(countLabel)}`:''}" aria-current="${state.chapter===ch?'page':'false'}">
      <span class="chapter-numeral">${esc(chapterNumeral(ch,i))}</span><span class="chapter-name"><b>${esc(chapterTitle(ch))}</b>${character?`<small>${esc(character)}</small>`:''}</span><span class="chapter-count">${reached&&count?count:''}</span>
    </button>`;}).join('') : '<div class="sidebar-loading">No chapter graph available.</div>';
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
function buildChapterGraph(chapter) {
  const originals = Object.values(state.graph?.nodes || {}).filter(n => n.chapter === chapter);
  const nodes = new Map(), edges = [];
  const addEdge = (from, to, type='normal', id='') => {
    if (!to) return;
    edges.push({from, to, type, id});
  };
  for (const n of originals) {
    const type = n.type === 'condition' || n.type === 'route' ? 'junction'
               : n.type === 'chapter_exit' ? 'exit' : n.type;
    const label = n.heading || ({choice:'CHOICE',condition:'CONDITION',route:'STORY BRANCH',chapter_exit:'CHAPTER COMPLETE',ending:'STORY END'}[n.type] || shortTitle(n.id,26));
    nodes.set(n.id, {id:n.id, parent:null, type, originalType:n.type, label, node:n,
                     width: n.type === 'choice' ? 180 : n.type === 'condition'||n.type === 'route' ? 135 : 190,
                     height: n.type === 'condition'||n.type === 'route' ? 39 : 60});
  }
  for (const n of originals) {
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
  return {nodes, edges:internal, chapter};
}
function computePath(view, chapter) {
  const visited = new Set(), traversed = new Set(), byId = new Map(), counts = new Map();
  const events = view?.detail?.events || [];
  for (let i = 0; i < events.length; i++) {
    const ev = events[i], nid = ev.node_id;
    if (ev.chapter !== chapter || !nid) continue;
    visited.add(nid);
    if (!byId.has(nid)) byId.set(nid,[]);
    byId.get(nid).push(ev);
    counts.set(nid,(counts.get(nid)||0)+1);
    const next = events[i+1];
    const nextId = next?.chapter === chapter ? next.node_id :
      next?.node_id && state.graph?.nodes?.[next.node_id] ? `PORTAL::${next.node_id}` : null;
    if (ev.type === 'decision') {
      const opt = optionId(nid, ev.choice_id);
      visited.add(opt);
      if (!byId.has(opt)) byId.set(opt,[]);
      byId.get(opt).push(ev);
      traversed.add(`${nid}\u0000${opt}`);
      if (nextId) {traversed.add(`${opt}\u0000${nextId}`); if(nextId.startsWith('PORTAL::')) {visited.add(nextId); byId.set(nextId,[ev]);}}
    } else if (nextId) {
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
  const maxRows = Math.max(1,...layers.map(x=>x.length));
  const stepX = 250, stepY = Math.max(109, ...all.map(n=>n.height + 42)), left = 115, top = 110;
  const contentHeight = maxRows * stepY;
  for(let rank=0;rank<layers.length;rank++) {
    const layer=layers[rank], startY=top+(contentHeight-layer.length*stepY)/2;
    for(let i=0;i<layer.length;i++) {
      const n=byId.get(layer[i]); n.x=left+rank*stepX; n.y=startY+i*stepY+15;
    }
  }
  return {width: left*2+Math.max(0,layers.length-1)*stepX+220,
          height:Math.max(420,top*2+contentHeight),rankCount:layers.length};
}
function edgeMarkup(e, graph, offset=0) {
  const a=graph.nodes.get(e.from),b=graph.nodes.get(e.to);
  if (!a || !b) return '';
  const x1=a.x+a.width, y1=a.y+a.height/2+offset;
  const x2=b.x, y2=b.y+b.height/2+offset;
  if (x2 >= x1) {
    const bend = Math.max(20, (x2-x1)*.52);
    return `M ${x1} ${y1} C ${x1+bend} ${y1}, ${x2-bend} ${y2}, ${x2} ${y2}`;
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
function drawGraph(graph, paths) {
  const world=$('graphWorld'), nodesEl=$('graphNodes'), edgesEl=$('graphEdges');
  const views=activeViews();
  // Keep every model logo visible. Additional rows expand node heights as needed.
  for(const node of graph.nodes.values()) {
    const count=paths.filter(x=>x.path.visited.has(node.id)).length;
    node.height=Math.max(node.height, count ? 58 + Math.ceil(count/7)*22 : node.height);
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
      path.setAttribute('data-run-id',view.run.id);
      path.setAttribute('aria-label',`${modelLabel(view.run)} took this branch`);
      const title=document.createElementNS(svgNS,'title');title.textContent=modelLabel(view.run);path.appendChild(title);
      edgesEl.appendChild(path);
    });
  }
  for(const node of graph.nodes.values()) {
    const users=paths.filter(view=>view.path.visited.has(node.id));
    const n=document.createElement('div');
    n.className=['flow-node',`kind-${node.type}`,users.length?'visited':'',state.selected?.id===node.id?'selected':''].filter(Boolean).join(' ');
    n.style.left=node.x+'px';n.style.top=node.y+'px';n.style.width=node.width+'px';n.style.height=node.height+'px';
    n.style.setProperty('--node-accent',users.length?routeColor(users[0].run):'#cad8df');
    n.role='button';n.tabIndex=0;n.dataset.nodeId=node.id;
    n.dataset.visitedCount=String(users.length);
    n.setAttribute('aria-label',`${node.label}. ${users.length} of ${views.length} selected runs visited this node.`);
    n.title=`${node.label} · ${users.length} / ${views.length} runs visited`;
    const label=document.createElement('span');label.className='node-label';label.textContent=node.label;n.appendChild(label);
    const left=document.createElement('i');left.className='node-socket left';left.setAttribute('aria-hidden','true');n.appendChild(left);
    const right=document.createElement('i');right.className='node-socket right';right.setAttribute('aria-hidden','true');n.appendChild(right);
    if(node.type==='choice'||node.type==='junction'){
      const mini=document.createElement('span');mini.className='node-mini';mini.textContent=node.type==='choice'?'DECISION':'STATE CHECK';n.appendChild(mini);
    }
    if(users.length){
      const logos=document.createElement('div');logos.className='node-logos';
      for(const view of users)logos.appendChild(createLogo(node,view));
      n.appendChild(logos);
    }
    n.addEventListener('click',e=>{
      e.stopPropagation();
      if(node.type==='portal'&&node.destinationChapter&&chapters().includes(node.destinationChapter))changeChapter(node.destinationChapter);
      else inspect(node.id,users[0]?.run.id||activeRuns()[0]?.id);
    });
    n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();n.click();}});
    nodesEl.appendChild(n);
  }
  return bounds;
}
function renderChapter(fit=true){
 if(!state.graph||!state.chapter)return;
 const chapter=state.chapter;
 $('chapterIndexLabel').textContent=chapterNumber(chapter)?`CHAPTER ${chapterNumber(chapter)}`:'ENDINGS';
 $('breadcrumbChapter').textContent=$('chapterIndexLabel').textContent;
 $('chapterTitle').textContent=chapterTitle(chapter);
 if(state.view==='story'){state.rendered=null;renderStory({keepScroll:!fit});return;}
 renderFlowchart(fit);
}
function renderFlowchart(fit=true){
 renderStoryToolbar(readerRun());
 const chapter=state.chapter, views=activeViews(), graph=buildChapterGraph(chapter);
 const paths=views.map(v=>({...v,path:computePath(v,chapter)}));
 const visited=new Set(paths.flatMap(v=>[...v.path.visited]));
 const choiceCount=views.reduce((sum,v)=>sum+(v.detail?.decisions||[]).filter(x=>x.chapter===chapter).length,0);
 $('chapterMetrics').textContent=`${niceNum(graph.nodes.size)} nodes · ${niceNum(choiceCount)} recorded decisions · ${niceNum(views.length)} runs`;
 $('chapterSubtitle').textContent=state.graph.metadata?.description||'Every script branch, with each selected run traced in color';
 $('visibleCount').textContent=niceNum(visited.size);$('totalCount').textContent=niceNum(graph.nodes.size);
 $('integrityNotice').textContent=!state.graph.complete?'SOURCE GRAPH MISSING · CANNOT SHOW ALL BRANCHES':
   views.some(v=>v.run.synthetic)?'SYNTHETIC PREVIEW · NOT ACTUAL MODEL DECISIONS':
   views.some(v=>v.run.unverified||v.run.fidelity!=='verified_game_rules')?'ALL INDEXED SCRIPT BRANCHES · GAME RULES UNVERIFIED':'FULL SAVED GRAPH · CHOICES AUDITABLE';
 $('integrityNotice').classList.toggle('warning',!state.graph.complete||views.some(v=>v.run.synthetic||v.run.unverified||v.run.fidelity!=='verified_game_rules'));
 const notice=$('graphNotice');notice.classList.toggle('is-hidden',state.graph.complete);
 if(!state.graph.complete)notice.textContent='The source graph is required to show all possible paths. Provide story-graph.json or a matching file via --graphs-dir.';
 const legend=$('canvasLegend');
 legend.innerHTML=`<summary class="legend-title">${niceNum(views.length)} RUNS · ${niceNum(graph.edges.length)} SCRIPT CONNECTIONS</summary><div class="legend-runs">${views.map(v=>`<div class="legend-line" data-focus-id="${esc(v.run.id)}" role="button" tabindex="0" title="Click to focus ${esc(modelLabel(v.run))}"><span class="legend-dash" style="border-color:${routeColor(v.run)}"></span><span class="legend-model">${modelIcon(providerOf(v.run))}</span><span class="legend-run-name">${esc(v.run.model)}</span></div>`).join('')}</div><div class="legend-line"><span class="legend-dash unvisited"></span>Untaken script branch</div>`;
 if(!state.graph.complete){
   $('graphEdges').replaceChildren();$('graphNodes').replaceChildren();
   $('graphEmpty').classList.remove('is-hidden');
   $('graphEmpty').innerHTML='<div class="empty-glyph">◇</div><strong>Original script graph required</strong><p>A run only records visited events. To display every possible branch, add the original matching story JSON via <code>--graphs-dir</code> or generate new runs with a story-graph.json snapshot.</p>';
   state.rendered=null;return;
 }
 $('graphEmpty').classList.toggle('is-hidden',graph.nodes.size>0);
 if(!graph.nodes.size)$('graphEmpty').innerHTML='<strong>No nodes in this chapter</strong><p>Select another chapter.</p>';
 const bounds=drawGraph(graph,paths);
 state.rendered={graph,paths,bounds};
 setupRunFocus();applyRunFocus();
 if(fit)requestAnimationFrame(openChapterView);else applyTransform();
 if(state.selected&&!graph.nodes.has(state.selected.id))closeDrawer();
}
function applyTransform(){ $('graphWorld').style.transform=`translate3d(${state.panX}px,${state.panY}px,0) scale(${state.scale})`; $('zoomLabel').textContent=`${Math.round(state.scale*100)}%`; }
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
function centerSelectedNode() {
  if (!state.selected || !state.rendered) return;
  const node=state.rendered.graph.nodes.get(state.selected.id);
  if(!node)return;
  state.viewTouched=true;
  const box=$('viewport').getBoundingClientRect();
  state.scale=clamp(Math.max(.72,state.scale),.16,1.45);
  state.panX=box.width*.44-(node.x+node.width/2)*state.scale;
  state.panY=box.height*.50-(node.y+node.height/2)*state.scale;
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
function closeDrawer(){state.selected=null;$('reasoningDrawer').classList.add('is-hidden');document.querySelectorAll('.flow-node.selected').forEach(n=>n.classList.remove('selected'));}
function fmtValue(v) {return typeof v==='string'?v:JSON.stringify(v);}
function renderInspectorShell(node,runId,view){
 const run=view.run, color=routeColor(run),provider=providerOf(run);
 $('reasoningDrawer').style.setProperty('--inspect-color',color);
 return `<div class="inspect-model-line"><span class="inspect-logo" style="border-color:${color};color:${color}">${modelIcon(provider)}</span><div><div class="inspect-model-name">${esc(modelName(provider))}</div><div class="inspect-run-name">${esc(run?.model||'Unknown')} · ${esc(run?.name||'')}</div></div></div>
  ${run?.synthetic?'<p class="inspect-note synthetic-disclaimer">SYNTHETIC PREVIEW — the recorded agent was a deterministic mock, not the named commercial model.</p>':''}
  <div class="inspect-overline">${esc(state.chapter)} · ${esc(node.type==='option'?'ACTION':'STORY NODE')}</div>
  <h2 class="inspect-title">${esc(node.label)}</h2>
  <button type="button" class="story-link inspect-read" data-read-run="${esc(runId)}">Read this moment in the story</button>`;
}
async function inspect(nodeId,runId){
 const node=state.rendered?.graph.nodes.get(nodeId);if(!node)return;
 const view=modelView(runId), path=state.rendered?.paths.find(p=>p.run.id===runId)?.path;
 const events=path?.byId.get(nodeId)||[];
 const selectedEvent=events.findLast?.(e=>e.type==='decision')||events[events.length-1];
 state.selected={id:nodeId,runId};
 $('drawerEventIndex').textContent=' / '+(selectedEvent?.index??'—');
 $('reasoningDrawer').classList.remove('is-hidden');requestAnimationFrame(centerSelectedNode);
 document.querySelectorAll('.flow-node').forEach(el=>el.classList.toggle('selected',el.dataset.nodeId===nodeId));
 if(!selectedEvent){
  $('drawerContent').innerHTML=renderInspectorShell(node,runId,view)+`<div class="nondecision-msg">This branch was not visited by this run. No model explanation or state transition was recorded here.</div>`;
  return;
 }
 $('drawerContent').innerHTML=renderInspectorShell(node,runId,view)+'<div class="nondecision-msg">Loading recorded decision…</div>';
 const marker=state.selected;
 try{
  const raw=await api(`/api/runs/${encodeURIComponent(runId)}/events/${selectedEvent.index}`);
  if(state.selected!==marker)return;
  if(raw.type==='decision')renderDecisionInspector(node,raw,runId,view);
  else renderSceneInspector(node,raw,runId,view);
 }catch(err){if(state.selected===marker)$('drawerContent').innerHTML=renderInspectorShell(node,runId,view)+`<div class="nondecision-msg">Could not load event: ${esc(err.message)}</div>`;}
}
function renderDecisionInspector(node,ev,runId,view){
 const input=ev.input||{},output=ev.output||{},history=input.entire_decision_history||[];
 const options=input.available_choices||[],selectedOption=options.find(o=>o.id===output.choice_id);
 const before=ev.flags_before||{},after=ev.flags_after||{};
 const changes=Array.from(new Set([...Object.keys(before),...Object.keys(after)]))
   .filter(k=>JSON.stringify(before[k])!==JSON.stringify(after[k]));
 const usage=ev.model_info?.token_usage||{},color=routeColor(view.run);
 $('drawerContent').innerHTML=renderInspectorShell(node,runId,view)+`
  <p class="inspect-subtitle">${esc(input.current_scene?.description||'')}</p>
  <div class="selected-choice" style="border-left-color:${color}"><div class="selected-label">ACTION SELECTED</div><strong>${esc(selectedOption?.label||ev.label||output.choice_id||'Not recorded')}</strong></div>
  <section class="inspect-section"><h3>MODEL'S STATED REASONING</h3><p class="rationale">${esc(output.rationale||'No explanation recorded for this action.')}</p><p class="inspect-note">An auditable justification, not private hidden reasoning.</p></section>
  <section class="inspect-section"><h3>AVAILABLE ACTIONS · ${niceNum(options.length)}</h3><div class="option-list">${options.map(o=>`<div class="option-pill ${o.id===output.choice_id?'chosen':''}" style="${o.id===output.choice_id?`border-color:${color}`:''}"><span class="option-symbol" style="${o.id===output.choice_id?`background:${color};border-color:${color}`:''}">✓</span><span>${esc(o.label||o.id)}</span></div>`).join('')}</div></section>
  <section class="inspect-section"><h3>WORLD STATE · ${changes.length} CHANGES</h3>${changes.length?changes.map(k=>`<div class="state-row"><span class="state-key">${esc(k)}</span><span class="state-before">${esc(fmtValue(before[k]??'—'))}</span><span class="state-after">→ ${esc(fmtValue(after[k]??'—'))}</span></div>`).join(''):'<p class="no-state">No tracked world-state flags changed.</p>'}</section>
  <section class="inspect-section"><h3>EARLIER DECISIONS IN CONTEXT · ${history.length}</h3>${history.length?history.slice(-10).map(h=>`<div class="inspect-history"><strong>${esc(h.scene||h.choice_key||'Earlier action')} · ${esc(h.label||'')}</strong><p>${esc(h.rationale||'No explanation')}</p></div>`).join(''):'<p class="no-state">No earlier decisions in context.</p>'}</section>
  <section class="inspect-section"><h3>RECORD METADATA</h3><div class="inspect-metrics"><div class="inspect-metric"><span>INPUT TOKENS</span><b>${niceNum(usage.input_tokens)}</b></div><div class="inspect-metric"><span>OUTPUT TOKENS</span><b>${niceNum(usage.output_tokens)}</b></div><div class="inspect-metric"><span>PRIOR SCENES</span><b>${niceNum((input.relevant_earlier_scenes||[]).length)}</b></div><div class="inspect-metric"><span>LATENCY</span><b>${ev.model_info?.latency_seconds!=null?esc(ev.model_info.latency_seconds)+' s':'—'}</b></div></div><details class="inspect-disclosure"><summary>VIEW FULL RECORDED INPUT + OUTPUT</summary><pre>${esc(JSON.stringify({system_prompt:ev.system_prompt,input,output},null,2))}</pre></details></section>
 ${ev.unverified_requirements?.length?'<p class="inspect-note">This decision involved unverified game-state requirements.</p>':''}`;
}
function renderSceneInspector(node,ev,runId,view){
 const data=ev.visible_to_agent||{};
 const preceding=(view.detail?.decisions||[]).filter(d=>d.index<ev.index).at(-1);
 const prior=`<section class="inspect-section"><h3>MOST RECENT MODEL DECISION</h3>${preceding?
 `<div class="selected-choice" style="border-left-color:${routeColor(view.run)}"><div class="selected-label">${esc(preceding.heading||'PREVIOUS ACTION')}</div><strong>${esc(preceding.label||preceding.choice_id)}</strong></div><p class="rationale">${esc(preceding.rationale||'No rationale recorded')}</p><p class="inspect-note">The latest recorded decision before this scene; other state variables can also affect the outcome.</p>`:
 '<p class="no-state">No prior decision in this run.</p>'}</section>`;
 $('drawerContent').innerHTML=renderInspectorShell(node,runId,view)+`
  <p class="inspect-subtitle">${esc(data.description||ev.description||node.node.description||'')}</p>
  <div class="nondecision-msg">This is a ${esc(ev.type)} event. It was not a direct model choice; the previous decision is shown below.</div>${prior}
  ${(data.observations||[]).length?`<section class="inspect-section"><h3>OBSERVATIONS</h3>${data.observations.map(o=>`<p class="nondecision-text">${esc(o)}</p>`).join('')}</section>`:''}
  ${(data.dialogue||[]).length?`<section class="inspect-section"><h3>DIALOGUE VISIBLE TO MODEL</h3>${data.dialogue.map(d=>`<div class="inspect-history"><strong>${esc(d.speaker||'Unknown')}</strong><p>${esc(d.text||'')}</p></div>`).join('')}</section>`:''}
  <section class="inspect-section"><details class="inspect-disclosure"><summary>VIEW RAW SAVED EVENT</summary><pre>${esc(JSON.stringify(ev,null,2))}</pre></details></section>`;
}
function setupInteractions(){
 $('pickerToggle').addEventListener('click',e=>{e.stopPropagation();state.pickerOpen=!state.pickerOpen;updateSelectors();if(state.pickerOpen)$('searchRuns').focus();});
 $('pickerPanel').addEventListener('click',e=>e.stopPropagation());
 document.addEventListener('click',e=>{if(state.pickerOpen&&!e.target.closest('#pickerContainer')){state.pickerOpen=false;updateSelectors();}});
 $('searchRuns').addEventListener('input',e=>{state.search=e.target.value;renderPickerList();});
 $('selectAllRuns').addEventListener('click',async()=>{
  const anchor=anchorRun()||state.runs[0];if(!anchor)return;
  state.selectedIds=state.runs.filter(r=>r.graph_sha256 && r.graph_sha256===anchor.graph_sha256).map(r=>r.id);
  updateSelectors();await loadCurrent(false);
 });
 $('clearRuns').addEventListener('click',async()=>{state.focusedId=null;state.selectedIds=[];state.graph=null;state.details.clear();state.selected=null;closeDrawer();updateSelectors();renderChapterList();displayNoRuns();});
 const fitToButton=()=>{fitGraph();state.viewTouched=true;};
 $('fitBtn').addEventListener('click',fitToButton);
 $('zoomIn').addEventListener('click',()=>zoom(1.2));
 $('zoomOut').addEventListener('click',()=>zoom(1/1.2));
 $('zoomReset').addEventListener('click',fitToButton);
 $('closeDrawer').addEventListener('click',closeDrawer);
 $('drawerContent').addEventListener('click',e=>{
  const link=e.target.closest('[data-read-run]');if(!link)return;
  const path=state.rendered?.paths.find(p=>p.run.id===link.dataset.readRun)?.path;
  const events=path?.byId.get(state.selected?.id)||[];
  state.pendingStoryIndex=events[0]?.index??null;
  state.readerRunId=link.dataset.readRun;
  setView('story');renderChapterList();
 });
 $('refreshBtn').addEventListener('click',()=>refreshRuns({reselect:true}));
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
 vp.addEventListener('wheel',e=>{e.preventDefault();zoom(e.deltaY<0?1.1:1/1.1,e.clientX,e.clientY);},{passive:false});
 let resizeDebounce;
 new ResizeObserver(()=>{clearTimeout(resizeDebounce);resizeDebounce=setTimeout(()=>{
  // Closing the drawer also resizes the canvas; that must not undo where the reader has moved to.
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
