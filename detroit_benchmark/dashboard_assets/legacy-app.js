'use strict';
const el = id => document.getElementById(id);
const state = {runs:[], selectedRun:null, detail:null, selectedIndex:null, view:'playthrough',
               comparison:null, compareFilter:'different', loading:false};
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => Number(n||0).toLocaleString('en-US');
const readable = value => typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—');
const when = date => {if(!date)return '—';const d=new Date(date);return Number.isNaN(d.valueOf())?date:d.toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'});};
const providerName = value => ({openai:'ChatGPT · OpenAI',anthropic:'Claude · Anthropic',mock:'Simulation'})[value]||value||'Unknown';
const providerGlyph = value => ({openai:'O',anthropic:'A',mock:'M'})[value]||'?';
function toast(message){const node=el('toast');node.textContent=message;node.classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.classList.remove('show'),3500);}
async function api(path){const result=await fetch(path,{cache:'no-store'});if(!result.ok){let message=result.statusText;try{message=(await result.json()).detail||message;}catch{}throw new Error(message);}return result.json();}
function empty(message){return `<div class="empty-main">${esc(message)}</div>`;}
function badge(title,css=''){return `<span class="tag ${css}">${esc(title)}</span>`;}
function view(name){state.view=name;for(const n of ['playthrough','compare','about']){el(n+'View').classList.toggle('hidden',n!==name);}document.querySelectorAll('.nav-link').forEach(btn=>btn.classList.toggle('active',btn.dataset.view===name));el('breadcrumbCurrent').textContent=({playthrough:'PLAYTHROUGH',compare:'MODEL COMPARISON',about:'METHODOLOGY'})[name];location.hash=name;}
function renderRunList(){
  el('runList').innerHTML=state.runs.length?state.runs.map(run=>`<button class="run-list-item ${run.id===state.selectedRun?'active':''}" data-run="${esc(run.id)}" type="button">
    <span class="provider-mark ${esc(run.provider)}">${esc(providerGlyph(run.provider))}</span>
    <span class="run-list-text"><strong title="${esc(run.name)}">${esc(run.name)}</strong><small>${esc(providerName(run.provider))} · ${fmt(run.choices)} choices${run.status==='running'?' · running':''}</small></span></button>`).join(''):
    `<div class="empty-side">No runs yet. Create one using the benchmark CLI, or open the included demo_runs folder.</div>`;
  document.querySelectorAll('[data-run]').forEach(btn=>btn.addEventListener('click',()=>selectRun(btn.dataset.run)));
}
function updatePickers(){
  for(const id of ['compareA','compareB']){
    const select=el(id), old=select.value;
    select.innerHTML=state.runs.map(run=>`<option value="${esc(run.id)}">${esc(run.name+' · '+providerName(run.provider))}</option>`).join('');
    if(state.runs.some(run=>run.id===old)) select.value=old;
  }
  if(state.runs.length>1&&el('compareA').value===el('compareB').value)el('compareB').selectedIndex=1;
  el('compareBtn').disabled=state.runs.length<2;
}
async function refresh(silent=false){
  if(state.loading)return;
  state.loading=true;
  try{
    const result=await api('/api/runs');
    state.runs=result.runs;
    renderRunList();updatePickers();
    el('lastRefresh').textContent='Updated '+new Date().toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'});
    el('liveStatus').textContent=state.runs.some(run=>run.status==='running')?'RUN IN PROGRESS':'LOCAL INSTANCE';
    if(!state.selectedRun&&state.runs.length)await selectRun(state.runs[0].id);
    else if(state.selectedRun&&state.runs.some(run=>run.id===state.selectedRun)){
      const run=state.runs.find(run=>run.id===state.selectedRun);
      if(run.status==='running' || (state.detail&&state.detail.run.status==='running'))await loadRun(state.selectedRun,true);
    }
    if(!silent)toast('Run list refreshed');
  }catch(error){if(!silent)toast('Could not load runs: '+error.message);el('lastRefresh').textContent='Connection unavailable';}
  finally{state.loading=false;}
}
async function selectRun(id){state.selectedRun=id;state.selectedIndex=null;state.detail=null;renderRunList();view('playthrough');await loadRun(id);}
async function loadRun(id,soft=false){
  try{
    const detail=await api(`/api/runs/${encodeURIComponent(id)}`);
    if(state.selectedRun!==id)return;
    state.detail=detail;
    renderHero();renderStats();renderChapterSelect();renderTimeline();
    const available=detail.decisions||[];
    if(available.length&&(!soft||!available.some(e=>e.index===state.selectedIndex))){await inspect(available[0].index);}
    else if(!available.length)el('inspector').innerHTML=`<div class="empty-inspector">No decisions have been recorded for this run yet. If the benchmark is still running, the dashboard will update automatically.</div>`;
    el('exportBtn').disabled=!available.length;
  }catch(error){toast('Could not load playthrough: '+error.message);}
}
function renderHero(){
  const run=state.detail?.run;
  if(!run){el('heroRun').innerHTML='<div class="loading-block">No run selected</div>';return;}
  const statusClass=run.status==='complete'?'complete':'running';
  el('heroRun').innerHTML=`<div class="hero-details"><div class="run-title-row"><div class="hero-mark ${esc(run.provider)}">${esc(providerGlyph(run.provider))}</div>
    <div><div class="hero-run-name">${esc(run.name)}</div><div class="hero-sub">${esc(providerName(run.provider))} / ${esc(run.model)} · ${esc(when(run.started_at))}</div></div></div>
    <div class="run-goal"><strong style="color:#cad8e7">Objective:</strong> ${esc(run.goal||'Not recorded')}</div></div>
    <div class="run-hero-right">${badge(run.status.toUpperCase(),statusClass)}${run.synthetic?badge('SYNTHETIC DEMO','unverified'):run.unverified||run.fidelity!=='verified_game_rules'?badge('EXPLORATORY','unverified'):badge('VERIFIED RULES','complete')}</div>`;
}
function renderStats(){const r=state.detail.run;const events=state.detail.events;
  const stats=[['DECISIONS',r.choices,'model-selected actions','◇'],['CHAPTERS',r.chapters,'visited in this run','▣'],['INPUT TOKENS',fmt(r.total_input_tokens),'reported API usage','⌁'],['OUTPUT TOKENS',fmt(r.total_output_tokens),'reported API usage','✧']];
  el('statsGrid').innerHTML=stats.map(([label,n,foot,icon])=>`<div class="stat-card"><div class="stat-name">${esc(label)}</div><div class="stat-accent">${esc(icon)}</div><div class="stat-number">${esc(n)}</div><div class="stat-foot">${esc(foot)}</div></div>`).join('');
  el('timelineCount').textContent=fmt(state.detail.decisions.length);
}
function renderChapterSelect(){const sel=el('filterChapter'), old=sel.value;const chapters=[...new Set(state.detail.events.map(e=>String(e.chapter??'Unknown')))];
  sel.innerHTML='<option value="all">All chapters</option>'+chapters.map(ch=>`<option value="${esc(ch)}">${esc(ch)}</option>`).join('');
  if(chapters.includes(old))sel.value=old;
}
function renderTimeline(){
  if(!state.detail){el('timeline').innerHTML=empty('Select a playthrough to start exploring.');return;}
  const q=el('filterSearch').value.trim().toLowerCase();const chapter=el('filterChapter').value;const showScenes=el('showScenes').checked;
  let items=state.detail.events.filter(e=>e.type==='decision'||(showScenes&&(e.type==='scene'||e.type==='ending')));
  if(chapter!=='all')items=items.filter(e=>String(e.chapter??'Unknown')===chapter);
  if(q)items=items.filter(e=>[e.chapter,e.node_id,e.heading,e.description,e.label,e.rationale,e.choice_id].some(v=>String(v||'').toLowerCase().includes(q)));
  if(!items.length){el('timeline').innerHTML='<div class="empty-inspector">No matching events. Try changing the filters.</div>';return;}
  let lastChapter;const html=[];
  for(const e of items){
    const ch=String(e.chapter??'Unknown');
    if(ch!==lastChapter){html.push(`<div class="chapter-heading"><strong>${esc(ch)}</strong><span>STORY SEGMENT</span></div>`);lastChapter=ch;}
    const choice=e.type==='decision';
    const title=choice?e.heading||'Decision point':e.heading||e.type;
    html.push(`<div class="timeline-row ${choice?'choice':''}"><button type="button" data-event="${e.index}" class="event-card ${choice?'':'scene'} ${state.selectedIndex===e.index?'selected':''}">
      <div class="event-topline"><span class="event-kicker">${choice?'DECISION':esc(e.type.toUpperCase())}</span><span class="event-number">#${e.index}</span></div>
      <div class="event-title">${esc(title)}</div>${e.description?`<div class="event-desc">${esc(e.description).slice(0,260)}</div>`:''}
      ${choice?`<div class="event-choice">↳ ${esc(e.label)}</div>${e.rationale?`<div class="event-rationale">“${esc(e.rationale).slice(0,260)}”</div>`:''}`:''}
    </button></div>`);
  }
  el('timeline').innerHTML=html.join('');
  el('timeline').querySelectorAll('[data-event]').forEach(button=>button.addEventListener('click',()=>inspect(Number(button.dataset.event))));
}
function changes(before,after){
  before=before||{};after=after||{};
  return [...new Set([...Object.keys(before),...Object.keys(after)])].filter(k=>JSON.stringify(before[k])!==JSON.stringify(after[k])).map(k=>({key:k,from:before[k],to:after[k]}));
}
async function inspect(index){
  if(!state.detail)return;
  const id=state.selectedRun;
  state.selectedIndex=index;
  document.querySelectorAll('.event-card').forEach(card=>card.classList.toggle('selected',Number(card.dataset.event)===index));
  el('inspector').innerHTML='<div class="empty-inspector">Loading event context…</div>';
  try{
    const raw=await api(`/api/runs/${encodeURIComponent(id)}/events/${index}`);
    if(state.selectedRun!==id||state.selectedIndex!==index)return;
    if(raw.type!=='decision')return renderNonDecision(raw);
    const input=raw.input||{}, output=raw.output||{};
    const scene=input.current_scene||{};
    const selected=output.choice_id;
    const available=input.available_choices||[];
    const allChanges=changes(raw.flags_before,raw.flags_after);
    const history=input.entire_decision_history||[];
    const sceneHistory=input.narrative_since_last_choice||[];
    const pertinent=input.relevant_earlier_scenes||[];
    const usage=(raw.model_info||{}).token_usage||{};
    el('inspector').innerHTML=`
      <div class="inspect-meta">${esc(raw.chapter||'Unknown')} · EVENT ${raw.index} · ${esc(scene.character||'Unknown character')}</div>
      <h2 class="inspect-title">${esc(scene.heading||'Decision point')}</h2>
      <p class="inspect-desc">${esc(scene.description||'No scene description provided.')}</p>
      <div class="inspect-block"><h3>Available actions <span style="color:#658aa0">(${available.length})</span></h3>
        ${available.map(opt=>`<div class="choice-option ${opt.id===selected?'active':''}"><span class="radio-ring"></span><span>${esc(opt.label)}${opt.id===selected?' · SELECTED':''}</span></div>`).join('')}
      </div>
      <div class="inspect-block"><h3>Model's stated justification</h3><div class="quote">“${esc(output.rationale||'No rationale recorded')}”</div>
        <div class="quote-foot">Model-reported explanation · not private chain-of-thought</div></div>
      <div class="inspect-block"><h3>World-state changes</h3>
        ${allChanges.length?allChanges.map(item=>`<div class="flag-chip"><span class="flag-key">${esc(item.key)}</span><span class="flag-old">${esc(readable(item.from))}</span><span>→</span><span class="flag-value">${esc(readable(item.to))}</span></div>`).join(''):`<p class="subtle-note">No explicit state flags changed by this choice.</p>`}
      </div>
      <div class="inspect-block"><h3>Previous decisions in model context</h3>
        <p class="subtle-note">${fmt(history.length)} earlier choices and their explanations were supplied to this decision.</p>
        ${history.length?history.slice(-6).map((x,i)=>`<div class="history-item"><div class="history-top">${esc(x.scene||x.choice_key||'Earlier choice')} · ${esc(x.label||'')}</div><div class="history-reason">${esc(x.rationale||'')}</div></div>`).join(''):'<p class="subtle-note">This is the first decision in the run.</p>'}
        ${history.length>6?'<p class="subtle-note">Showing the six most recent; the complete input is available below.</p>':''}
        ${output.relevant_prior_choices?.length?`<div class="quote-foot">Model referenced: ${esc(output.relevant_prior_choices.join(', '))}</div>`:''}
      </div>
      <div class="inspect-block"><h3>Current narrative context</h3><div class="subtle-note">${fmt(sceneHistory.length)} scenes since the previous choice · ${fmt(pertinent.length)} earlier scenes retrieved</div>
       ${sceneHistory.slice(-3).map(x=>`<div class="history-item"><div class="history-top">${esc(x.heading||x.scene_id)}</div><div class="history-reason">${esc(x.description||'')}</div></div>`).join('')}
       <details><summary>View full model input and output</summary><pre>${esc(JSON.stringify({system_prompt:raw.system_prompt||'Not recorded by this engine version; see engine.py.',input:input,output:output},null,2))}</pre></details>
      </div>
      <div class="inspect-block"><h3>Inference telemetry</h3>
       <div class="micro-stat"><span>Model</span><strong>${esc(raw.model||'—')}</strong></div>
       <div class="micro-stat"><span>Input tokens</span><strong>${fmt(usage.input_tokens)}</strong></div>
       <div class="micro-stat"><span>Output tokens</span><strong>${fmt(usage.output_tokens)}</strong></div>
       <div class="micro-stat"><span>LLM latency</span><strong>${raw.model_info?.latency_seconds!=null?esc(raw.model_info.latency_seconds)+' s':'—'}</strong></div>
       <div class="micro-stat"><span>Event recorded</span><strong>${esc(when(raw.timestamp))}</strong></div>
       ${raw.unverified_requirements?.length?`<p class="subtle-note" style="color:#e7bd80">Some requirements in this event are unverified.</p>`:''}
      </div>`;
  }catch(error){el('inspector').innerHTML=empty('Could not load decision: '+error.message);}
}
function renderNonDecision(raw){
  const scene=raw.visible_to_agent||{};
  el('inspector').innerHTML=`<div class="inspect-meta">${esc(raw.chapter||'Unknown')} · EVENT ${raw.index} · ${esc(raw.type.toUpperCase())}</div>
    <h2 class="inspect-title">${esc(scene.heading||raw.type)}</h2><p class="inspect-desc">${esc(scene.description||raw.description||'')}</p>
    ${scene.observations?.length?`<div class="inspect-block"><h3>Observations</h3>${scene.observations.map(v=>`<div class="history-item">${esc(v)}</div>`).join('')}</div>`:''}
    ${scene.dialogue?.length?`<div class="inspect-block"><h3>Observed dialogue</h3>${scene.dialogue.map(v=>`<div class="history-item"><div class="history-top">${esc(v.speaker)}</div><div class="history-reason">${esc(v.text)}</div></div>`).join('')}</div>`:''}
    <div class="inspect-block"><details><summary>View raw event</summary><pre>${esc(JSON.stringify(raw,null,2))}</pre></details></div>`;
}
function renderComparison(data){
  const [a,b]=data.runs;
  const card=r=>`<div class="duel-card panel"><div class="duel-head"><div class="hero-mark ${esc(r.provider)}">${esc(providerGlyph(r.provider))}</div><div><div class="duel-name">${esc(r.model)}</div><div class="duel-provider">${esc(r.name)} · ${esc(providerName(r.provider))}</div></div></div>
    <div class="duel-meta"><div><strong>${fmt(r.choices)}</strong><span>DECISIONS</span></div><div><strong>${fmt(r.chapters)}</strong><span>CHAPTERS</span></div><div><strong>${fmt(r.total_input_tokens+r.total_output_tokens)}</strong><span>TOTAL TOKENS</span></div></div>
    ${r.synthetic?`<div style="margin-top:18px">${badge('SYNTHETIC DEMO','unverified')}</div>`:r.unverified||r.fidelity!=='verified_game_rules'?`<div style="margin-top:18px">${badge('EXPLORATORY · UNVERIFIED','unverified')}</div>`:''}</div>`;
  const allChapters=[...new Set([...(state.comparisonDetails?.[0]?.decisions_by_chapter||[]),...(state.comparisonDetails?.[1]?.decisions_by_chapter||[])].map(c=>c.chapter))];
  const counts = state.comparisonDetails?.map(d=>Object.fromEntries(d.decisions_by_chapter.map(c=>[c.chapter,c.choices])))||[{},{}];
  const max=Math.max(1,...allChapters.flatMap(c=>[counts[0][c]||0,counts[1][c]||0]));
  el('compareContent').innerHTML=`<div class="duel-grid">${card(a)}${card(b)}</div>
    <div class="compare-summary"><div class="compare-stat same panel"><strong>${fmt(data.identical)}</strong><span>SAME DECISION</span></div><div class="compare-stat diff panel"><strong>${fmt(data.different)}</strong><span>DIFFERENT DECISION</span></div><div class="compare-stat exclusive panel"><strong>${fmt(data.unshared)}</strong><span>PATH-EXCLUSIVE NODES</span></div></div>
    <div class="compare-grid"><div class="bar-panel panel"><h2 class="section-title">Choices by chapter</h2><p class="section-sub">Number of decisions made within each chapter encountered by either run.</p>
      ${allChapters.map(ch=>`<div class="bar-row"><div class="bar-label">${esc(ch)}</div><div class="bar-tracks"><div class="bar-track"><div class="bar-fill" style="width:${100*(counts[0][ch]||0)/max}%"></div></div><div class="bar-track secondary"><div class="bar-fill" style="width:${100*(counts[1][ch]||0)/max}%"></div></div></div></div>`).join('')||'<div class="subtle-note">No recorded decisions</div>'}
      <div class="legend"><span><i></i>${esc(a.model)}</span><span class="secondary"><i></i>${esc(b.model)}</span></div></div>
      <div class="divergence-panel panel"><h2 class="section-title">Decision comparison</h2><p class="section-sub">${esc(data.notes)}</p><div class="divergence-tabs">
      <button class="toggle-pill" data-diff-filter="different">Differences</button><button class="toggle-pill" data-diff-filter="all">All choices</button><button class="toggle-pill" data-diff-filter="same">Matches</button><button class="toggle-pill" data-diff-filter="exclusive">Path-exclusive</button>
      </div><div id="divergences"></div></div></div>`;
  document.querySelectorAll('[data-diff-filter]').forEach(btn=>btn.addEventListener('click',()=>{state.compareFilter=btn.dataset.diffFilter;renderDiffRows();}));
  renderDiffRows();
}
function renderDiffRows(){
  if(!state.comparison)return;
  const data=state.comparison,[a,b]=data.runs;
  document.querySelectorAll('[data-diff-filter]').forEach(btn=>btn.classList.toggle('selected',btn.dataset.diffFilter===state.compareFilter));
  const rows=data.rows.filter(row=>state.compareFilter==='all'||(state.compareFilter==='exclusive'?row.status==='only_left'||row.status==='only_right':row.status===state.compareFilter));
  if(!rows.length){el('divergences').innerHTML='<p class="subtle-note">No decisions match this filter.</p>';return;}
  const side=(dec,run)=>`<div class="diff-side"><div class="diff-model">${esc(run.model)}</div>${dec?`<div class="diff-label">${esc(dec.label||dec.choice_id)}</div><div class="diff-rationale">${esc(dec.rationale||'')}</div>`:'<div class="diff-placeholder">Not visited on this path</div>'}</div>`;
  el('divergences').innerHTML=rows.map(row=>{
    const same=row.status==='same', path=row.status.startsWith('only');
    return `<article class="diff-item"><div class="diff-header"><strong>${esc(row.chapter||'Unknown')} / ${esc(row.node_id)}${row.occurrence>1?' · visit '+row.occurrence:''}</strong>
      <span class="diff-status ${same?'same':path?'path':''}">${same?'MATCH':path?'PATH EXCLUSIVE':'DIVERGENCE'}</span></div><div class="diff-choices">${side(row.left,a)}${side(row.right,b)}</div></article>`;
  }).join('');
}
async function compare(){
  const a=el('compareA').value,b=el('compareB').value;
  if(!a||!b||a===b){toast('Choose two different runs.');return;}
  el('compareContent').innerHTML='<div class="empty-main">Analyzing shared decisions and branching paths…</div>';
  const query=new URLSearchParams();query.append('run_ids',a);query.append('run_ids',b);
  try{
    const [result,da,db]=await Promise.all([api('/api/compare?'+query.toString()),api(`/api/runs/${encodeURIComponent(a)}`),api(`/api/runs/${encodeURIComponent(b)}`)]);
    state.comparison=result;state.comparisonDetails=[da,db];renderComparison(result);
  }catch(error){el('compareContent').innerHTML=empty('Comparison failed: '+error.message);}
}
function wire(){
  document.querySelectorAll('[data-view]').forEach(btn=>btn.addEventListener('click',()=>view(btn.dataset.view)));
  el('refreshBtn').addEventListener('click',()=>refresh());
  el('filterSearch').addEventListener('input',renderTimeline);
  el('filterChapter').addEventListener('change',renderTimeline);
  el('showScenes').addEventListener('change',renderTimeline);
  el('exportBtn').addEventListener('click',()=>{if(state.selectedRun)window.location.href=`/api/runs/${encodeURIComponent(state.selectedRun)}/decisions.csv`;});
  el('compareBtn').addEventListener('click',compare);
  el('homeLink').addEventListener('click',event=>{event.preventDefault();view('playthrough');});
  const initial=location.hash.slice(1);if(['playthrough','compare','about'].includes(initial))view(initial);
  setInterval(()=>refresh(true),5000);
}
wire();refresh(true);
