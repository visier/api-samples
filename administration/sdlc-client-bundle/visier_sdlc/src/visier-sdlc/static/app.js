const icons = {
  layers:'<path d="m3 7 9-4 9 4-9 4-9-4Z"/><path d="m3 12 9 4 9-4M3 17l9 4 9-4"/>',
  history:'<path d="M3 11a9 9 0 1 1 2.4 7M3 4v7h7"/><path d="M12 7v5l3 2"/>',
  settings:'<path d="m9 3-.6 2.4-2.1 1.2L4 6l-2 3.5 1.7 1.8v2.4L2 15.5 4 19l2.3-.6 2.1 1.2L9 22h4l.6-2.4 2.1-1.2 2.3.6 2-3.5-1.7-1.8v-2.4L20 9.5 18 6l-2.3.6-2.1-1.2L13 3Z"/><circle cx="11" cy="12.5" r="3"/>',
  help:'<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4 2c-1.5 1-1.5 1.5-1.5 3M12 17h.01"/>',
  external:'<path d="M14 3h7v7M21 3 11 13"/><path d="M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
  chevron:'<path d="m9 5 7 7-7 7"/>',
  refresh:'<path d="M20 7a8 8 0 0 0-14-1L3 9m0-6v6h6M4 17a8 8 0 0 0 14 1l3-3m0 6v-6h-6"/>',
  sync:'<path d="M4 7h15l-4-4M20 17H5l4 4M20 7l-5 4M4 17l5-4"/>',
  shield:'<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/><path d="m8 12 3 3 5-6"/>',
  database:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
  warning:'<path d="M10.3 4 2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 4a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
  code:'<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
  globe:'<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  arrow:'<path d="M4 12h16m-6-6 6 6-6 6"/>',
  undo:'<path d="M3 9h11a6 6 0 0 1 0 12M3 9l5-5M3 9l5 5"/>',
  lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
  check:'<path d="m5 12 4 4L19 6"/>',
  plus:'<path d="M12 4v16M4 12h16"/>',
};
const icon = name => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.55" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.layers}</svg>`;
const $ = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
let state = null, selectedId = null, currentView = 'promotions', busy = false, stale = false, fetching = false;
let refreshTask = null;
let dialogAction = null, baselineAction = null, recoveryAction = null, toastTimer = null;
let sourceMigrationResult = null;
document.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML = icon(el.dataset.icon); });

function dateParts(value) {
  if (!value) return {day:'Not available', time:''};
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return {day:'Not available', time:''};
  return {day:date.toLocaleDateString(undefined, {month:'short', day:'numeric'}), time:date.toLocaleTimeString(undefined, {hour:'numeric', minute:'2-digit'})};
}
function relativeTime(value) {
  if (!value) return 'No sync recorded';
  const date = new Date(value), diff = Math.max(0, Date.now() - date.getTime());
  if (diff < 60000) return 'Just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)} min ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} hr ago`;
  if (diff < 172800000) return 'Yesterday';
  return date.toLocaleDateString(undefined, {month:'short', day:'numeric'});
}
function pendingVersions() { return state?.source.filter(v => v.status === 'pending') || []; }
function selection() {
  const pending = pendingVersions(), index = pending.findIndex(v => v.id === selectedId);
  return index < 0 ? [] : pending.slice(index).reverse();
}
function notify(message, error = false) {
  $('toast').textContent = message;
  $('toast').className = 'toast' + (error ? ' error' : '');
  $('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('toast').hidden = true; }, error ? 8000 : 5000);
}
async function api(path, data) {
  const options = data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)};
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || 'The request could not be completed.');
  return payload;
}
async function refresh(announce = false, force = false) {
  if (fetching) {
    await refreshTask;
    if (force) return refresh(announce);
    return;
  }
  let release;
  refreshTask = new Promise(resolve => {release = resolve;});
  fetching = true;
  $('refresh').disabled = true;
  $('refresh').innerHTML = '<span class="spinner"></span><span>Refreshing</span>';
  try {
    const next = await api('/api/state');
    // A changed tenant history invalidates a selection based on the previous snapshot.
    if (state && state.fingerprint !== next.fingerprint) selectedId = null;
    state = next;
    stale = false;
    $('error-banner').hidden = true;
    $('loading').hidden = true;
    render();
    if (announce) notify('Both tenant histories are up to date.');
  } catch (error) {
    stale = true;
    $('loading').hidden = true;
    $('error-banner').textContent = error.message + ' Use Refresh to try again.';
    $('error-banner').hidden = false;
    if (state) render();
    if (announce) notify(error.message, true);
  } finally {
    fetching = false;
    $('refresh').disabled = false;
    $('refresh').innerHTML = icon('refresh') + '<span>Refresh</span>';
    release();
  }
}
function versionRow(version, source, includedIds) {
  const isBaseline = source && version.status === 'synced';
  const isEndpoint = version.id === selectedId;
  const isIncluded = source && includedIds.has(version.id);
  const tag = isBaseline ? `<span class="row-status synced">${icon('check')}${state.checkpoint?.rebaselined_at ? 'Baseline' : 'Last synced'}</span>` : isIncluded ? `<span class="row-status included">${icon('check')}${isEndpoint ? 'Selected' : 'Included'}</span>` : !source && version.status === 'unconfirmed' ? '<span class="row-status included">Awaiting confirmation</span>' : !source && version.status === 'drift' ? `<span class="row-status drift">Drift</span>` : !source && version.status === 'synced' ? `<span class="row-status synced">${icon('check')}${state.checkpoint?.rebaselined_at && version.id === state.checkpoint.target_id ? 'Baseline' : 'Synced'}</span>` : '';
  const control = source ? isBaseline ? `<span class="row-lock">${icon('lock')}</span>` : `<input type="radio" name="version" value="${escapeHtml(version.id)}" ${isEndpoint ? 'checked' : ''} ${busy || state.operation || stale ? 'disabled' : ''} aria-label="Promote through ${escapeHtml(version.description)}">` : '';
  const content = `<span><span class="version-title">${escapeHtml(version.description)}</span><span class="version-subtitle"><span>${escapeHtml(version.id)}</span>${tag}</span></span>`;
  return `<tr class="${isBaseline ? 'baseline' : isEndpoint ? 'selected' : isIncluded ? 'included-row' : !source && version.status === 'drift' ? 'drift-row' : source ? 'row-hit' : ''}" ${source && !isBaseline ? `data-version-id="${escapeHtml(version.id)}"` : ''}><td>${source && !isBaseline ? `<label class="version-label">${control}${content}</label>` : `<div class="version-label">${control}${content}</div>`}</td><td class="version-number">${version.number != null ? escapeHtml(version.number) : '<span title="The Visier API did not provide a version number">—</span>'}</td></tr>`;
}
function activityRow(record) {
  const succeeded = record.status === 'succeeded';
  const reset = record.kind === 'rebaseline';
  const sources = record.kind === 'sources';
  const title = reset ? 'Sync baseline reset' : sources ? 'Unversioned sources migrated' : record.kind === 'rollback' ? 'Production rollback' : `${plural(record.count || 0, 'version')} synchronized`;
  const description = reset ? `${record.scope === 'both' ? 'Source and target' : record.scope === 'source' ? 'Source' : 'Target'} baseline · ${record.reason} · Source: ${record.before?.source_id || 'None'} → ${record.after.source_id} · Target: ${record.before?.target_id || 'None'} → ${record.after.target_id}` : sources ? `${record.replace_all_existing_sources ? 'Replace all target sources' : 'Keep target-only sources'} · ${record.summary ? sourceSummary(record.summary) : record.message || 'Operation did not complete'}` : succeeded ? record.kind === 'rollback' ? 'Restored the last synchronized production state' : 'Development → Production · Committed and published' : record.message || 'Operation did not complete';
  return `<div class="activity-row"><div class="activity-icon ${succeeded ? '' : 'failed'}">${icon(succeeded ? 'check' : 'warning')}</div><div class="activity-description"><strong>${escapeHtml(succeeded ? title : (sources ? 'Source migration' : record.kind === 'rollback' ? 'Rollback' : 'Sync') + ' needs attention')}</strong><p>${escapeHtml(description)}${record.project_id ? ' · Draft ' + escapeHtml(record.project_id) : ''}</p></div><span class="activity-time" title="${escapeHtml(record.finished_at || record.started_at)}">${escapeHtml(relativeTime(record.finished_at || record.started_at))}</span><span class="activity-tag ${succeeded ? '' : 'failed'}">${succeeded ? 'Successful' : 'Failed'}</span></div>`;
}
function sourceSummary(summary) { return `${summary.created} created · ${summary.updated} updated · ${summary.ignored} unchanged · ${summary.deleted} deleted`; }
function sourceResult(record) {
  if (!record) return '';
  const succeeded = record.status === 'succeeded';
  const heading = `<div class="sources-result-heading">${icon(succeeded ? 'check' : 'warning')}<strong>${succeeded ? 'Source migration complete' : 'Source migration failed'}</strong></div>`;
  const details = record.summary ? `<dl class="sources-result-counts">${[
    ['created', 'Created'], ['updated', 'Updated'], ['ignored', 'Unchanged'], ['deleted', 'Deleted']
  ].map(([key, label]) => `<div><dt>${label}</dt><dd>${escapeHtml(record.summary[key])}</dd></div>`).join('')}</dl><p class="sources-result-note">Counts reported by Visier.</p>` : `<p class="sources-result-note">${escapeHtml(record.message || 'No import counts available.')}</p>`;
  return heading + details;
}
function emptyActivity() { return `<div class="empty-activity">${icon('history')}<span>Your next move starts here. Syncs, source migrations, rollbacks, and baseline resets will appear in this activity log.</span></div>`; }
function render() {
  if (!state) return;
  $('mode-badge').textContent = state.mode === 'demo' ? 'Demo workspace' : 'Live workspace';
  $('mode-badge').classList.toggle('live', state.mode === 'live');
  $('pending-count').textContent = state.pending_count;
  $('pending-tag').textContent = state.source_name;
  $('sync-summary-label').textContent = state.checkpoint?.rebaselined_at ? 'Sync baseline' : 'Last successful sync';
  $('last-sync').textContent = state.checkpoint?.rebaselined_at ? 'Baseline reset' : state.checkpoint ? relativeTime(state.checkpoint.at) : 'Not synced yet';
  $('last-sync').title = state.checkpoint?.rebaselined_at ? 'Baseline reset on ' + new Date(state.checkpoint.rebaselined_at).toLocaleString() + '; no sync was published' : state.checkpoint?.at ? new Date(state.checkpoint.at).toLocaleString() : 'An initial baseline may have no recorded timestamp';
  let health = state.drift ? 'Drift detected' : 'In sync';
  if (busy) health = 'Operation in progress';
  if (state.operation) health = state.operation.kind === 'sources' ? 'Source migration in progress' : state.operation.kind === 'rollback' ? 'Rollback in progress' : 'Sync in progress';
  if (state.operation?.status === 'needs_review') health = state.operation.kind === 'sources' ? 'Review source import' : 'Review publication';
  if (state.operation?.status === 'retryable') health = 'Publication denied';
  if (state.issue) health = 'Review baseline';
  if (stale) health = 'Connection unavailable';
  const attention = state.drift || state.issue || stale || ['needs_review','retryable'].includes(state.operation?.status);
  $('health-value').textContent = health;
  $('health-icon').className = 'summary-icon ' + (attention ? 'amber' : 'mint');
  $('health-dot').className = 'status-dot ' + (attention ? 'amber-dot' : 'green-dot');
  $('tab-count').textContent = state.pending_count;
  $('checked-at').textContent = 'Updated ' + dateParts(state.checked_at).time;
  $('drift-banner').hidden = !state.drift;
  const driftCount = state.target.filter(v => v.status === 'drift').length;
  $('drift-description').textContent = `${plural(driftCount, 'version')} published directly to production. Roll back to the saved baseline, or reset the target sync baseline if these production changes are known not to cause merge conflicts with pending development changes.`;
  $('issue-banner').hidden = !state.issue;
  $('issue-description').textContent = state.issue || '';
  $('operation-banner').hidden = !state.operation && !busy;
  if (state.operation) {
    const steps = {export:'Exporting development versions', create:'Creating a production draft', upload:'Importing changes into the draft', publish:'Committing and publishing to production', delete:'Deleting the draft', rollback:'Preparing a rollback draft', export_sources:'Exporting development sources', import_sources:'Importing sources directly into production'};
    const recovery = ['needs_review','retryable'].includes(state.operation.status);
    const versionOperation = ['sync','rollback'].includes(state.operation.kind);
    const message = state.operation.status === 'retryable' ? 'Publication was denied. Correct the target user’s permissions, then retry or discard the draft.' : recovery && versionOperation && state.operation.step === 'publish' ? 'Publication may have completed. Verify the result in Visier, then recover this operation.' : state.operation.message;
    $('operation-banner').innerHTML = (recovery ? icon('warning') : '<span class="spinner"></span>') + `<span>${escapeHtml(recovery ? message : steps[state.operation.step] || 'Operation in progress')}${state.operation.project_id ? '<br>Draft: ' + escapeHtml(state.operation.project_id) : ''}<br><small>${versionOperation ? 'If this operation has stopped, use recovery to continue.' : 'Verify interrupted source imports in Visier and use administrator reconciliation.'}</small></span>` + (versionOperation ? `<button type="button" id="recover-operation" class="button secondary" ${busy || stale ? 'disabled' : ''}>Recover operation</button>` : '');
  } else if (busy) $('operation-banner').innerHTML = '<span class="spinner"></span><span>Preparing your operation…</span>';
  $('source-heading').textContent = state.source_name;
  $('target-heading').textContent = state.target_name;
  $('source-connection').textContent = stale ? 'Connection unavailable' : state.mode === 'demo' ? 'Simulated tenant' : 'Connected';
  $('target-connection').textContent = stale ? 'Connection unavailable' : state.mode === 'demo' ? 'Simulated tenant' : 'Connected';
  $('source-total').textContent = `${state.pending_count} pending`;
  $('target-total').textContent = plural(state.target.length, 'version');
  const included = selection(), ids = new Set(included.map(v => v.id));
  $('source-rows').innerHTML = state.source.map(v => versionRow(v,true,ids)).join('') || '<tr><td colspan="2" class="no-versions">No published development versions yet.</td></tr>';
  $('target-rows').innerHTML = state.target.map(v => versionRow(v,false,ids)).join('') || '<tr><td colspan="2" class="no-versions">No production versions yet.<br>Your first sync will appear here.</td></tr>';
  $('reset-baseline').disabled = busy || stale || !!state.operation;
  $('drift-rebaseline').disabled = busy || stale || !!state.operation;
  $('issue-rebaseline').disabled = busy || stale || !!state.operation;
  $('sync-menu-toggle').disabled = busy || stale || !!state.operation;
  if ($('sync-menu-toggle').disabled) setSyncMenu(false);
  $('restore-baseline').hidden = !previousBaseline();
  $('restore-baseline').disabled = busy || stale || !!state.operation;
  $('rollback').disabled = !state.can_rollback || busy || stale;
  $('rollback').title = state.can_rollback ? 'Restore the saved production baseline' : 'Rollback is available when production drift is detected';
  $('baseline-label').textContent = state.checkpoint ? 'Saved baseline is your rollback point' : 'No synchronized baseline yet';
  $('clear-selection').hidden = !selectedId;
  $('clear-selection').disabled = busy || !!state.operation;
  if (included.length) {
    $('selection-heading').textContent = `${plural(included.length, 'version')} selected for promotion`;
    const first = included[0], last = included[included.length - 1];
    $('selection-detail').textContent = `${first.number != null ? 'v' + first.number : first.id}${included.length > 1 ? ' through ' + (last.number != null ? 'v' + last.number : last.id) : ''} · ${state.source_name} → ${state.target_name}${state.drift ? ' · Resolve drift to continue' : ''}`;
  } else {
    $('selection-heading').textContent = state.pending_count ? 'Choose what moves forward' : 'Your tenants are up to date';
    $('selection-detail').textContent = state.pending_count ? 'Select a development version to prepare your promotion.' : 'New development versions will appear here when published.';
  }
  $('sync').disabled = !included.length || busy || !!state.operation || state.drift || !!state.issue || stale;
  $('menu-sync').disabled = $('sync').disabled;
  $('sync').innerHTML = (busy ? '<span class="spinner"></span>' : icon('sync')) + '<span>Sync to production</span>';
  $('sources-direction').textContent = `${state.source_name} → ${state.target_name}`;
  $('migrate-sources').disabled = !$('sources-replace').checked || busy || stale || !!state.operation;
  $('sources-replace').disabled = busy || stale || !!state.operation;
  $('sources-result').hidden = !sourceMigrationResult;
  $('sources-result').innerHTML = sourceResult(sourceMigrationResult);
  if ($('baseline-dialog').open) validateBaseline();
  if ($('recovery-dialog').open) validateRecovery();
  $('recent-rows').innerHTML = state.history.length ? state.history.slice(0,2).map(activityRow).join('') : emptyActivity();
  $('activity-rows').innerHTML = state.history.length ? state.history.map(activityRow).join('') : emptyActivity();
  $('activity-count').textContent = plural(state.history.length, 'operation');
  $('demo-controls').hidden = state.mode !== 'demo';
  $('add-drift').disabled = busy || !!state.operation || stale;
  const connectionFields = [['vanity', 'Tenant vanity'], ['host', 'API base URI'], ['username', 'API user']];
  const connectionDetails = role => connectionFields.map(([field, label]) => {
    const value = state.connections?.[role]?.[field] || (state.mode === 'demo' ? 'Not applicable (demo)' : 'Not configured');
    return `<div class="connection-detail"><span>${label}</span><span>${escapeHtml(value)}</span></div>`;
  }).join('');
  $('connections-content').innerHTML = ['source','target'].map(role => `<article class="content-card connection-card"><span class="environment-tag ${role === 'source' ? 'dev-tag' : 'prod-tag'}">${role === 'source' ? 'SOURCE TENANT' : 'TARGET TENANT'}</span><h2>${escapeHtml(state[role + '_name'])}</h2><div class="connection-detail"><span>Connection</span><span>${stale ? 'Unavailable' : state.mode === 'demo' ? 'Simulated tenant' : 'Visier platform SDK'}</span></div><div class="connection-detail"><span>Environment</span><span>${state.mode === 'demo' ? 'Local demo' : 'Live tenant'}</span></div>${connectionDetails(role)}<div class="connection-detail"><span>Authentication method</span><span>Basic Authentication</span></div><div class="connection-detail"><span>Last checked</span><span>${escapeHtml(dateParts(state.checked_at).time)}</span></div></article>`).join('');
  showView(currentView);
}
function showView(view) {
  if (view !== 'promotions') { setSyncMenu(false); resetSourceMigration(); }
  currentView = view;
  if (!state) return;
  $('promotion-view').hidden = view !== 'promotions';
  $('activity-view').hidden = view !== 'activity';
  $('connections-view').hidden = view !== 'connections';
  document.querySelectorAll('.nav-item').forEach(item => { item.classList.toggle('active',item.dataset.view === view); if(item.dataset.view === view) item.setAttribute('aria-current','page'); else item.removeAttribute('aria-current'); });
  document.querySelectorAll('.mobile-nav [data-view]').forEach(item => { item.classList.toggle('active',item.dataset.view === view); if(item.dataset.view === view) item.setAttribute('aria-current','page'); else item.removeAttribute('aria-current'); });
  const titles = {promotions:['Tenant promotion','Bring your development changes to production with confidence.'],activity:['Activity log','A record of every sync, rollback, and release decision.'],connections:['Connections','The development and production tenants in your promotion workflow.']};
  $('page-title').textContent = titles[view][0];
  $('breadcrumb-current').textContent = titles[view][0];
  $('page-description').textContent = titles[view][1];
}
function resetSourceMigration() {
  sourceMigrationResult = null;
  $('sources-result').hidden = true;
  $('sources-result').innerHTML = '';
  $('sources-replace').checked = false;
  $('migrate-sources').disabled = true;
}
function setTab(sources) {
  setSyncMenu(false);
  if (!sources) resetSourceMigration();
  $('sources-panel').hidden = !sources;
  $('version-panel').hidden = sources;
  ['sources','versions'].forEach(name => {
    const tab = $(name + '-tab'), active = (name === 'sources') === sources;
    tab.classList.toggle('active',active);
    tab.setAttribute('aria-selected',String(active));
    tab.tabIndex = active ? 0 : -1;
  });
}
async function perform(kind, fingerprint, versionId, details = {}) {
  if (kind === 'sources/migrate') sourceMigrationResult = null;
  busy = true; render();
  const poll = setInterval(() => refresh(), 2000);
  try {
    const result = await api('/api/' + kind, {fingerprint, ...(versionId ? {version_id:versionId} : {}), ...details});
    if (kind === 'sources/migrate') {
      $('sources-replace').checked = false;
      if (currentView === 'promotions' && !$('sources-panel').hidden) {
        sourceMigrationResult = {status:'succeeded', summary:result.summary};
      }
    }
    selectedId = null;
    notify(result.message);
  } catch (error) { notify(error.message,true); }
  finally { clearInterval(poll); busy = false; await refresh(false,true); if(state) render(); }
}
function review(kind) {
  setSyncMenu(false);
  if (!state || busy || stale) return;
  const included = selection();
  if (state.operation || (kind === 'sync' && $('sync').disabled)) return;
  const rollback = kind === 'rollback';
  const sources = kind === 'sources/migrate';
  const replace = $('sources-replace').checked;
  if (sources && $('migrate-sources').disabled) return;
  $('dialog-icon').innerHTML = icon(rollback ? 'undo' : 'sync');
  $('dialog-title').textContent = rollback ? 'Restore synchronized production?' : 'Ready to move forward?';
  $('dialog-description').textContent = rollback ? 'This creates and publishes a rollback project that reverses production changes made after the saved production baseline.' : `Promote ${plural(included.length,'development version')} to ${state.target_name}. These changes will be committed and published.`;
  $('dialog-details').innerHTML = rollback ? `<strong>Restore to the saved production baseline</strong><br>Production baseline: ${escapeHtml(state.checkpoint.target_id)}<br>Your pending development changes remain available.` : `<strong>${escapeHtml(state.source_name)} → ${escapeHtml(state.target_name)}</strong><br>${included.map(v => escapeHtml(v.description)).join('<br>')}`;
  if (sources) {
    $('dialog-title').textContent = replace ? 'Replace all production sources?' : 'Migrate unversioned sources?';
    $('dialog-description').textContent = `Import all current source definitions from ${state.source_name} directly into ${state.target_name}. Version rollback cannot undo this import.`;
    $('dialog-details').innerHTML = `<strong>${escapeHtml(state.source_name)} → ${escapeHtml(state.target_name)}</strong><br>${replace ? 'All existing target sources will be removed before importing the development sources.' : 'Matching sources will be updated. Target-only sources will be kept.'}<br>The current sources at the time of export will be imported.`;
  }
  $('confirm-action').innerHTML = (rollback ? 'Confirm rollback' : 'Confirm sync') + icon('arrow');
  if (sources) $('confirm-action').innerHTML = (replace ? 'Confirm replace all sources' : 'Confirm source migration') + icon('arrow');
  $('project-fields').hidden = rollback || sources;
  ['project-name', 'project-description', 'project-version'].forEach(id => { $(id).disabled = rollback || sources; });
  $('project-name').value = $('project-name').defaultValue;
  $('project-name').setCustomValidity('');
  $('project-description').value = '';
  $('project-version').value = state.next_version_number;
  dialogAction = {kind,fingerprint:state.fingerprint,versionId:sources ? null : selectedId,
    details:sources ? {replace_all_existing_sources:replace} : {}};
  $('confirm-dialog').returnValue = '';
  $('confirm-dialog').showModal();
}
function previousBaseline() {
  const latest = state?.history.find(record => record.kind === 'rebaseline');
  if (latest?.kind !== 'rebaseline' || !latest.before || !state.checkpoint) return null;
  const matches = ['source','target'].every(role =>
    state.checkpoint[role + '_id'] === latest.after[role + '_id'] &&
    state.baseline_versions[role].some(v => v.id === latest.before[role + '_id']));
  return matches ? latest.before : null;
}
function openRecovery() {
  if (!state?.operation || busy || stale || state.operation.kind === 'sources') return;
  const operation = state.operation;
  recoveryAction = {operation_id:operation.id, state_revision:state.state_revision};
  $('recovery-form').reset();
  $('recovery-details').textContent = `${operation.kind === 'rollback' ? 'Production rollback' : 'Development promotion'} · Draft: ${operation.project_id || 'No draft ID saved'}`;
  const options = [...$('recovery-action').options];
  options.forEach(option => {
    option.disabled = operation.published_target_id ? option.value !== 'published' :
      option.value === 'retry' ? operation.step !== 'publish' || !operation.project_id :
      option.value === 'discard' ? !operation.project_id : false;
  });
  $('recovery-action').value = options.find(option => !option.disabled).value;
  const beforeIndex = state.target.findIndex(version => version.id === operation.target_before);
  const candidates = beforeIndex < 0 ? state.target : state.target.slice(0, beforeIndex);
  $('recovery-target').innerHTML = '<option value="">Choose the verified published version</option>' + candidates.map(version => `<option value="${escapeHtml(version.id)}">${escapeHtml(version.description)} · ${escapeHtml(version.id)}</option>`).join('');
  if (operation.published_target_id) $('recovery-target').value = operation.published_target_id;
  updateRecovery();
  $('recovery-dialog').showModal();
}
function updateRecovery() {
  const action = $('recovery-action').value;
  const published = action === 'published';
  $('recovery-target-field').hidden = !published;
  $('recovery-target').disabled = !published;
  $('recovery-target').required = published;
  const labels = {retry:'Retry publishing', discard:'Delete draft', published:'Confirm publication', dismiss:'Dismiss operation'};
  const effects = {
    retry:'Publishes the same draft. Production must be unchanged since it was prepared.',
    discard:'Deletes the draft project in Visier and releases this operation. The sync baseline stays unchanged.',
    published:'Updates the sync baseline to the version you verified belongs to this operation. It does not publish again.',
    dismiss:'Releases this operation without changing the sync baseline. Any draft remains in Visier for manual cleanup.'
  };
  $('recovery-effect').textContent = effects[action];
  $('recovery-confirm').textContent = labels[action];
  $('recovery-verification').textContent = published ? 'I verified in Visier that this operation published the selected version, and the original operation is no longer running.' : 'I verified in Visier that this operation was never published, and the original operation is no longer running.';
  $('recovery-verified').checked = false;
  validateRecovery();
}
function validateRecovery() {
  const changed = !recoveryAction || busy || stale || state.operation?.id !== recoveryAction.operation_id || state.state_revision !== recoveryAction.state_revision;
  $('recovery-feedback').textContent = changed ? 'The operation changed. Close this dialog and review recovery again.' : '';
  const valid = !changed && $('recovery-verified').checked && $('recovery-form').checkValidity();
  $('recovery-confirm').disabled = !valid;
  return valid;
}
$('operation-banner').addEventListener('click', event => { if (event.target.closest('#recover-operation')) openRecovery(); });
$('recovery-action').addEventListener('change', updateRecovery);
$('recovery-target').addEventListener('change', () => { $('recovery-verified').checked = false; validateRecovery(); });
$('recovery-verified').addEventListener('change', validateRecovery);
$('recovery-cancel').addEventListener('click', () => $('recovery-dialog').close());
$('recovery-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!validateRecovery()) return;
  const details = {...recoveryAction, action:$('recovery-action').value, verified:true,
    target_id:$('recovery-target').disabled ? null : $('recovery-target').value};
  recoveryAction = null;
  $('recovery-dialog').close();
  perform('operations/recover', null, null, details);
});
function openBaseline(previous = null, scope = 'both') {
  if (!state || busy || stale || state.operation) return;
  setSyncMenu(false);
  baselineAction = {fingerprint:state.fingerprint, checkpoint:state.checkpoint};
  $('baseline-form').reset();
  $('baseline-scope').value = state.checkpoint ? scope : 'both';
  $('baseline-scope').disabled = !state.checkpoint;
  ['source','target'].forEach(role => {
    const versions = state.baseline_versions[role];
    $('baseline-' + role).innerHTML = '<option value="">Choose a version</option>' + versions.map(v => `<option value="${escapeHtml(v.id)}">${escapeHtml(v.number != null ? 'v' + v.number + ' · ' : '')}${escapeHtml(v.description)} · ${escapeHtml(v.id)}</option>`).join('');
    const selected = previous?.[role + '_id'] || state.checkpoint?.[role + '_id'];
    $('baseline-' + role).value = versions.some(v => v.id === selected) ? selected : state.checkpoint ? versions[0]?.id || '' : '';
  });
  if (scope === 'target') $('baseline-target').value = state.baseline_versions.target[0]?.id || '';
  if (previous) $('baseline-reason').value = 'Restore the previous baseline to review production drift and decide whether to roll back.';
  updateBaselinePreview();
  $('baseline-dialog').showModal();
}
function updateBaselinePreview() {
  const scope = $('baseline-scope').value;
  const before = baselineAction.checkpoint;
  const after = {};
  ['source','target'].forEach(role => {
    const changing = scope === 'both' || scope === role;
    $('baseline-' + role + '-field').hidden = !changing;
    $('baseline-' + role).disabled = !changing;
    after[role] = changing ? $('baseline-' + role).value : before?.[role + '_id'];
  });
  $('baseline-preview').innerHTML = '<strong>Saved baseline → New baseline</strong><br>' + ['source','target'].map(role => `${role === 'source' ? 'Source' : 'Target'}: ${escapeHtml(before?.[role + '_id'] || 'None')} → ${escapeHtml(after[role] || 'Choose a version')}`).join('<br>') + '<br>Versions newer than the target baseline will still be treated as drift.';
  validateBaseline();
}
function validateBaseline() {
  if (!baselineAction) { $('baseline-confirm').disabled = true; return false; }
  const scope = $('baseline-scope').value, before = baselineAction.checkpoint;
  const after = {};
  ['source','target'].forEach(role => { after[role] = scope === 'both' || scope === role ? $('baseline-' + role).value : before?.[role + '_id']; });
  const versionsValid = ['source','target'].every(role => state.baseline_versions[role].some(v => v.id === after[role]));
  const changed = ['source','target'].some(role => after[role] !== before?.[role + '_id']);
  const reason = $('baseline-reason').value;
  let feedback = '';
  if (busy || stale || state.operation || baselineAction.fingerprint !== state.fingerprint) feedback = 'Close this dialog and refresh to review the current tenant state.';
  else if (!versionsValid) feedback = 'Choose valid source and target baseline versions.';
  else if (!changed) feedback = 'Choose at least one version different from the saved baseline.';
  else if (!reason.trim() || reason.length > 1000) feedback = 'Provide a reason for resetting the baseline (up to 1000 characters).';
  else if (!$('baseline-verified').checked) feedback = 'Check the verification box to confirm your review.';
  $('baseline-feedback').textContent = feedback;
  const valid = !feedback && $('baseline-form').checkValidity();
  $('baseline-confirm').disabled = !valid;
  return valid;
}
$('reset-baseline').addEventListener('click', () => openBaseline());
$('issue-rebaseline').addEventListener('click', () => openBaseline());
$('drift-rebaseline').addEventListener('click', () => openBaseline(null, state.checkpoint ? 'target' : 'both'));
$('restore-baseline').addEventListener('click', () => { const previous = previousBaseline(); if (previous) openBaseline(previous); });
['baseline-scope','baseline-source','baseline-target'].forEach(id => $(id).addEventListener('change', updateBaselinePreview));
$('baseline-form').addEventListener('input', validateBaseline);
$('baseline-form').addEventListener('change', validateBaseline);
$('baseline-cancel').addEventListener('click', () => $('baseline-dialog').close());
$('baseline-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!validateBaseline()) return;
  const scope = $('baseline-scope').value;
  const details = {reason:$('baseline-reason').value, verified:$('baseline-verified').checked};
  ['source','target'].forEach(role => { if (scope === 'both' || scope === role) details[role + '_id'] = $('baseline-' + role).value; });
  const fingerprint = baselineAction.fingerprint;
  baselineAction = null;
  $('baseline-dialog').close();
  perform('rebaseline', fingerprint, null, details);
});
document.addEventListener('click', event => {
  if (!event.target.closest('#sync-actions')) setSyncMenu(false);
  const nav = event.target.closest('[data-view]');
  if (nav) showView(nav.dataset.view);
  const row = event.target.closest('[data-version-id]');
  if (row && !busy && !state?.operation && !stale) {
    event.preventDefault(); selectedId = row.dataset.versionId; render();
    document.querySelector('input[name="version"]:checked')?.focus({preventScroll:true});
  }
});
function setSyncMenu(open, last = false) {
  $('sync-menu').hidden = !open;
  $('sync-menu-toggle').setAttribute('aria-expanded', String(open));
  if (open) {
    const items = [...$('sync-menu').querySelectorAll('button:not(:disabled):not([hidden])')];
    (last ? items[items.length - 1] : items[0])?.focus();
  }
}
$('sync-menu-toggle').addEventListener('click', () => setSyncMenu($('sync-menu').hidden));
$('sync-menu-toggle').addEventListener('keydown', event => {
  if (['ArrowDown','ArrowUp'].includes(event.key)) { event.preventDefault(); setSyncMenu(true, event.key === 'ArrowUp'); }
});
$('sync-menu').addEventListener('keydown', event => {
  if (event.key === 'Tab') { setSyncMenu(false); $('sync-menu-toggle').focus(); return; }
  if (!['ArrowDown','ArrowUp','Home','End'].includes(event.key)) return;
  event.preventDefault();
  const items = [...$('sync-menu').querySelectorAll('button:not(:disabled):not([hidden])')];
  const index = items.indexOf(document.activeElement);
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
  items[next]?.focus();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !$('sync-menu').hidden) { event.preventDefault(); setSyncMenu(false); $('sync-menu-toggle').focus(); }
});
document.addEventListener('focusin', event => { if (!event.target.closest('#sync-actions')) setSyncMenu(false); });
$('menu-sync').addEventListener('click', () => review('sync'));
$('source-rows').addEventListener('change',event => { if(event.target.name === 'version') { selectedId = event.target.value; render(); document.querySelector('input[name="version"]:checked')?.focus({preventScroll:true}); } });
$('refresh').addEventListener('click',() => refresh(true));
$('clear-selection').addEventListener('click',() => { selectedId = null; render(); });
$('versions-tab').addEventListener('click',() => setTab(false));
$('sources-tab').addEventListener('click',() => setTab(true));
$('sources-replace').addEventListener('change',() => render());
document.querySelector('.section-tabs').addEventListener('keydown',event => {
  if (['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) {
    event.preventDefault(); const sources = event.key === 'Home' || (event.key !== 'End' && $('sources-tab').getAttribute('aria-selected') !== 'true');
    setTab(sources); $(sources ? 'sources-tab' : 'versions-tab').focus();
  }
});
$('help').addEventListener('click',() => $('help-dialog').showModal());
$('mobile-help').addEventListener('click',() => $('help-dialog').showModal());
$('sync').addEventListener('click',() => review('sync'));
$('migrate-sources').addEventListener('click',() => review('sources/migrate'));
$('rollback').addEventListener('click',() => review('rollback'));
$('project-name').addEventListener('input', () => {
  const name = $('project-name').value.trim();
  $('project-name').setCustomValidity(!name ? 'Provide a draft project display name.' : name.length > 50 ? 'The display name must be 50 characters or fewer.' : '');
});
$('confirm-dialog').addEventListener('close', () => {
  const action = dialogAction;
  dialogAction = null;
  if ($('confirm-dialog').returnValue === 'confirm' && action) {
    const details = action.kind === 'sync' ? {
      project_name:$('project-name').value.trim(), project_description:$('project-description').value
    } : action.details;
    perform(action.kind, action.fingerprint, action.versionId, details);
  }
});
$('add-drift').addEventListener('click',async () => {
  if (busy || stale) return;
  busy = true; render();
  try { const result = await api('/api/demo/drift',{}); notify(result.message); }
  catch(error) { notify(error.message,true); }
  finally {busy = false;await refresh();if(state)render();}
});
refresh();
setInterval(() => { if (!document.hidden && !busy && !$('confirm-dialog').open && !$('baseline-dialog').open && !$('recovery-dialog').open) refresh(); }, 30000);
