'use strict';
const $ = (selector) => document.querySelector(selector);
const state = { project: null, cueId: null, busy: false, dirty: false, configured: false, pollStarted: Date.now(), pollPaused: false };
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const cue = () => state.project?.cues.find(item => item.id === state.cueId);

function notice(message, error = false) {
  $('#notice').textContent = message;
  $('#notice').className = error ? 'error' : '';
  $('#notice').hidden = !message;
}
async function api(path, method = 'GET', body) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch(path, {method, signal: controller.signal,
      headers: body ? {'Content-Type': 'application/json'} : {},
      body: body ? JSON.stringify(body) : undefined});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed.');
    return data;
  } finally { clearTimeout(timeout); }
}
async function run(action) {
  if (state.busy) return;
  state.busy = true;
  updateButtons();
  try { await action(); }
  catch (error) { notice(error.name === 'AbortError' ? 'The local request timed out. Refresh the project to find its take before generating again.' : error.message, true); }
  finally { state.busy = false; updateButtons(); }
}
function updateButtons() {
  const current = cue();
  const unresolved = current?.takes.some(t => ['SUBMITTING','UNKNOWN','RUNNING','QUEUED'].includes(t.status));
  $('#generate').disabled = state.busy || !state.configured || !!unresolved;
  $('#generate').textContent = state.busy ? 'Working…' : current?.takes.length ? 'Generate a new take ↗' : 'Generate this cue ↗';
  $('#save').disabled = state.busy;
  $('#export').disabled = state.busy || !state.project || state.dirty || state.project.cues.some(c => !c.takes.some(t => t.id === c.selected && t.status === 'SUCCESS' && !t.stale));
  $('#project-select').disabled = state.busy;
  $('#new-project').disabled = state.busy;
}
function renderSidebar() {
  $('#cue-count').textContent = `${state.project?.cues.length || 0} ${state.project?.cues.length === 1 ? "cue" : "cues"}`;
  if (!state.project) return;
  $('#cue-list').innerHTML = state.project.cues.map((c, i) => {
    const selected = c.takes.find(t => t.id === c.selected);
    const status = selected ? selected.stale ? 'Draft changed' : 'Ready for delivery' : c.takes.length ? c.takes[0].status : 'Not generated';
    return `<button class="cue-item ${c.id === state.cueId ? 'active' : ''}" data-cue="${c.id}" aria-current="${c.id === state.cueId}"><span class="cue-number">CUE ${String(i+1).padStart(2,'0')}</span><b>${esc(c.title)}</b><small>${esc(status)}</small></button>`;
  }).join('');
  const ready = state.project.cues.filter(c => c.takes.some(t => t.id === c.selected && t.status === 'SUCCESS' && !t.stale)).length;
  $('#export-description').textContent = `${ready} of ${state.project.cues.length} cues ready · MP3 files + script + settings manifest`;
}
function renderEditor() {
  const current = cue();
  $('#editor').hidden = !current;
  $('#empty-editor').hidden = !!current;
  if (!current) return;
  $('#cue-title').value = current.title;
  $('#cue-text').value = current.text;
  $('#voice').value = current.voice;
  $('#speed').value = current.speed;
  state.dirty = false;
  $('#save-state').textContent = 'Saved locally';
  $('#char-count').textContent = `${current.text.length} / 2000`;
}
function renderTakes() {
  const current = cue();
  $('#take-count').textContent = `${current?.takes.length || 0} ${current?.takes.length === 1 ? "take" : "takes"}`;
  if (!current || !current.takes.length) {
    $('#take-list').innerHTML = '<div class="empty-takes"><div class="sound-bars" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></div><h3>Your takes live here.</h3><p>Generate this cue to hear it. Your script is saved locally; no audio has been generated yet.</p></div>';
    return;
  }
  $('#take-list').innerHTML = current.takes.map((t, i) => `<article class="take ${current.selected === t.id ? 'chosen' : ''}"><div class="take-header"><span>Take ${current.takes.length-i} ${current.selected === t.id ? '✓' : ''}</span><span class="status">${esc(t.status)}</span></div><p>${esc(t.payload.voice_id)} · ${t.payload.speed}×</p><p class="snapshot">${esc(t.payload.text)}</p>${t.stale ? '<p class="stale">Saved draft differs. This take cannot be exported until its settings match.</p>' : ''}${t.task_id ? `<label class="sr-only" for="task-${t.id}">Task ID</label><input class="task-id" id="task-${t.id}" readonly value="${esc(t.task_id)}" aria-label="Task ID">` : ''}${t.error ? `<p class="error">${esc(t.error)}</p>` : ''}${t.status === 'SUCCESS' ? `<audio controls preload="metadata" src="/api/takes/${t.id}/audio"></audio><div class="take-actions"><button data-action="select" data-id="${t.id}">${current.selected === t.id ? 'Selected ✓' : 'Use this take'}</button><a href="/api/takes/${t.id}/audio?download=1" download>Save MP3 ↧</a></div>` : `<div class="take-actions">${t.task_id ? `<button data-action="query" data-id="${t.id}">Retry query</button>` : ''}${t.status === 'UNKNOWN' ? `<button data-action="attach" data-id="${t.id}">Attach task ID</button><button data-action="resolve" data-id="${t.id}">No remote task</button>` : ''}</div>`}</article>`).join('');
}
async function loadProject(id, full = true) {
  if (!id) return;
  state.project = await api('/api/projects/' + id);
  if (!state.project.cues.some(c => c.id === state.cueId)) state.cueId = state.project.cues[0]?.id;
  localStorage.setItem('cuecraft.project', id);
  $('#project-select').value = id;
  renderSidebar();
  if (full) renderEditor();
  renderTakes(); updateButtons();
}
async function listProjects() {
  const projects = await api('/api/projects');
  $('#project-select').innerHTML = '<option value="">Choose a project</option>' + projects.map(p => `<option value="${p.id}">${esc(p.title)}</option>`).join('');
  return projects;
}
async function save() {
  if (!cue()) return;
  if (!$('#editor').reportValidity()) throw new Error('Check the cue title, text and speed.');
  await api('/api/cues/' + state.cueId, 'PATCH', {title: $('#cue-title').value, text: $('#cue-text').value, voice: $('#voice').value, speed: Number($('#speed').value)});
  state.dirty = false;
  $('#save-state').textContent = 'Saved locally';
  await loadProject(state.project.id, false);
}
function openDialog() {
  if (state.dirty && !confirm('Discard unsaved changes to this cue?')) return;
  $('#dialog-error').textContent = '';
  $('#project-dialog').showModal();
  $('#project-title').focus();
}
$('#new-project').onclick = openDialog;
$('#start-project').onclick = openDialog;
$('#close-dialog').onclick = () => $('#project-dialog').close();
$('#sample').onclick = () => {
  $('#project-title').value = 'Sample · A quiet gallery';
  $('#script').value = 'Welcome to the gallery. Take a moment to notice the light.\n\nOn your left, a quiet landscape invites us to slow down.\n\nBefore you leave, choose one detail you would like to remember.';
};
$('#project-form').onsubmit = async (event) => {
  event.preventDefault();
  if (state.busy) return;
  state.busy = true;
  const submit = event.submitter;
  submit.disabled = true;
  try {
    const project = await api('/api/projects','POST',{title:$('#project-title').value,script:$('#script').value});
    await listProjects();
    state.cueId = null;
    await loadProject(project.id);
    $('#project-dialog').close();
    notice('Project created locally. Choose a cue and generate when you are ready.');
  } catch (error) { $('#dialog-error').textContent = error.message; }
  finally {state.busy = false; submit.disabled = false; updateButtons();}
};
$('#editor').addEventListener('input', () => {state.dirty=true; $('#save-state').textContent='Unsaved changes'; $('#char-count').textContent=`${$('#cue-text').value.length} / 2000`; updateButtons();});
$('#editor').onsubmit = (event) => {event.preventDefault(); run(async () => {await save(); notice('Cue draft saved. Existing takes are kept.');});};
$('#cue-list').onclick = (event) => {
  const button = event.target.closest('[data-cue]');
  if (!button) return;
  run(async () => {if (state.dirty) await save(); state.cueId=button.dataset.cue; renderSidebar(); renderEditor(); renderTakes();});
};
$('#project-select').onchange = () => run(async () => {const id=$('#project-select').value; if(state.dirty) await save(); await loadProject(id);});
$('#generate').onclick = () => run(async () => {
  if (cue().takes.length && !confirm('Generate a new paid take? Previous takes will be kept.')) return;
  await save();
  const key = 'cuecraft.pending.' + state.cueId;
  const token = localStorage.getItem(key) || crypto.randomUUID();
  localStorage.setItem(key, token);
  notice('Submitting once. Keep this page open; the task record will be saved locally.');
  await api('/api/cues/' + state.cueId + '/takes', 'POST', {token});
  localStorage.removeItem(key);
  state.pollStarted = Date.now(); state.pollPaused=false;
  await loadProject(state.project.id, false);
  notice('Take recorded. Running tasks are queried every 4 seconds; querying never creates a new take.');
});
$('#take-list').onclick = (event) => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  run(async () => {
    const {action,id} = button.dataset;
    let data = {};
    if (action === 'attach') {
      const taskId = prompt('Paste the matching speech task ID from RunningHub history. Check its text and account first.');
      if (!taskId) return;
      data = {task_id:taskId.trim()};
    }
    if (action === 'resolve') {
      if (!confirm('Have you checked RunningHub history and confirmed that no task was created? A later generation is a new paid request.')) return;
      data = {confirmed_no_task:true};
    }
    await api(`/api/takes/${id}/${action}`,'POST',data);
    state.pollStarted=Date.now(); state.pollPaused=false;
    await loadProject(state.project.id,false);
    notice(action === 'select' ? 'Delivery take selected.' : 'Task record updated.');
  });
};
$('#export').onclick = () => run(async () => {
  const response = await fetch('/api/projects/' + state.project.id + '/export');
  if (!response.ok) throw new Error((await response.json()).error);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a'); link.href=url; link.download='cuecraft-narration-kit.zip'; link.click();
  setTimeout(() => URL.revokeObjectURL(url),60000);
  notice('Delivery kit exported with selected audio, script.md and manifest.json.');
});
window.addEventListener('beforeunload', event => {if(state.dirty){event.preventDefault();event.returnValue='';}});
async function poll() {
  if (state.busy || !state.project || state.pollPaused) return;
  const pending = state.project.cues.flatMap(c => c.takes).filter(t => ['RUNNING','QUEUED'].includes(t.status) && t.task_id);
  if (!pending.length) return;
  if (Date.now()-state.pollStarted > 15*60*1000) {
    state.pollPaused=true;
    notice('Automatic querying paused after 15 minutes. Your tasks are kept. Use Retry query to continue.',true);
    return;
  }
  state.busy = true; updateButtons();
  try {
    let changed=false;
    for (const take of pending) {
      const result = await api(`/api/takes/${take.id}/query`,'POST',{});
      if (result.status !== take.status || result.error !== take.error) changed=true;
    }
    if (changed) await loadProject(state.project.id,false);
  } catch (error) {
    state.pollPaused=true;
    notice(error.message + ' Auto-query paused. Use Retry query; this does not regenerate audio.',true);
    await loadProject(state.project.id,false).catch(() => {});
  } finally {state.busy=false;updateButtons();}
}
(async () => {
  try {
    const config = await api('/api/config'); state.configured=config.configured;
    $('#config').textContent = config.configured ? 'API key configured' : 'API key missing';
    $('#voice').innerHTML=config.voices.map(v=>`<option value="${esc(v)}">${esc(v.replaceAll('_',' '))}</option>`).join('');
    const projects=await listProjects();
    const saved=localStorage.getItem('cuecraft.project');
    if (projects.length) await loadProject(projects.find(p=>p.id===saved)?.id || projects[0].id);
    if (!config.configured) notice('Add RUNNINGHUB_API_KEY to .env and restart. You can still prepare and save scripts.',true);
  } catch(error) {notice(error.message,true);}
  updateButtons(); setInterval(poll,4000);
})();
