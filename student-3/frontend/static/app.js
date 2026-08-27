const state = { sources: [], schedules: [], chatHistory: [] };
const money = new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD' });
const $ = (selector) => document.querySelector(selector);

document.addEventListener('DOMContentLoaded', () => {
  const monthPicker = $('#monthPicker');
  if (!monthPicker.value) monthPicker.value = new Date().toISOString().slice(0, 7);
  bindEvents();
  refreshAll();
  checkAiStatus();
});

function bindEvents() {
  $('#refreshButton').addEventListener('click', refreshAll);
  $('#monthPicker').addEventListener('change', refreshAll);
  $('#newSourceButton').addEventListener('click', () => openSourceForm());
  $('#newScheduleButton').addEventListener('click', () => openScheduleForm());
  $('#generateButton').addEventListener('click', () => showOnlyForm('generateForm'));
  $('#sourceForm').addEventListener('submit', saveSource);
  $('#scheduleForm').addEventListener('submit', saveSchedule);
  $('#generateForm').addEventListener('submit', generateSchedules);
  $('#paymentStatus').addEventListener('change', syncReceivedFields);
  $('#chatForm').addEventListener('submit', sendChat);
  $('#analyseButton').addEventListener('click', analyseMonth);
  document.querySelectorAll('[data-close]').forEach((button) => {
    button.addEventListener('click', () => { $('#' + button.dataset.close).hidden = true; });
  });
  document.querySelectorAll('[data-prompt]').forEach((button) => {
    button.addEventListener('click', () => {
      $('#chatInput').value = button.dataset.prompt;
      $('#chatInput').focus();
    });
  });
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  let payload = null;
  if (response.status !== 204) {
    try { payload = await response.json(); }
    catch { payload = { error: 'The service returned an unreadable response.' }; }
  }
  if (!response.ok) throw new Error(payload?.error || `Request failed (${response.status})`);
  return payload;
}

async function refreshAll() {
  setBusy($('#refreshButton'), true, 'Refreshing…');
  try {
    const month = $('#monthPicker').value;
    const [sourcePayload, dashboardPayload] = await Promise.all([
      api('/api/income-sources'),
      api(`/api/dashboard?month=${encodeURIComponent(month)}`),
    ]);
    state.sources = sourcePayload.items;
    state.schedules = dashboardPayload.schedules;
    renderSources();
    renderSchedules();
    renderSummary(dashboardPayload.summary);
    populateSourceSelects();
  } catch (error) {
    notify(error.message, true);
  } finally {
    setBusy($('#refreshButton'), false, 'Refresh');
  }
}

function renderSummary(summary) {
  $('#receivedTotal').textContent = money.format(summary.received_total);
  $('#expectedTotal').textContent = money.format(summary.expected_total);
  $('#outstandingTotal').textContent = money.format(summary.outstanding_total);
  $('#activeSources').textContent = summary.active_source_count;
  $('#receivedCount').textContent = `${summary.received_count} received payment${summary.received_count === 1 ? '' : 's'}`;
  $('#outstandingCount').textContent = `${summary.scheduled_count} scheduled / ${summary.late_count} late`;
  $('#varianceText').textContent = `Received variance ${money.format(summary.variance)}`;
}

function renderSources() {
  const body = $('#sourceTableBody');
  if (!state.sources.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty-cell">No income sources yet.</td></tr>';
    return;
  }
  body.innerHTML = state.sources.map((source) => `
    <tr>
      <td><strong>${escapeHtml(source.source_name)}</strong></td>
      <td>${escapeHtml(source.income_type)}</td>
      <td class="money">${money.format(source.standard_amount)}</td>
      <td>${titleCase(source.payment_frequency)}</td>
      <td><span class="tag ${source.active ? 'active' : 'inactive'}">${source.active ? 'Active' : 'Inactive'}</span></td>
      <td class="align-right">
        <button class="table-action" type="button" onclick="editSource(${source.id})">Edit</button>
        <button class="table-action danger" type="button" onclick="deleteSource(${source.id})">Delete</button>
      </td>
    </tr>`).join('');
}

function renderSchedules() {
  const body = $('#scheduleTableBody');
  if (!state.schedules.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty-cell">No pay schedules in this month.</td></tr>';
    return;
  }
  body.innerHTML = state.schedules.map((schedule) => `
    <tr>
      <td>${formatDate(schedule.expected_pay_date)}</td>
      <td><strong>${escapeHtml(schedule.source_name)}</strong></td>
      <td class="money">${money.format(schedule.expected_amount)}</td>
      <td class="money">${schedule.actual_amount == null ? '—' : money.format(schedule.actual_amount)}</td>
      <td><span class="tag ${escapeHtml(schedule.status)}">${escapeHtml(schedule.status)}</span></td>
      <td class="align-right">
        <button class="table-action" type="button" onclick="editSchedule(${schedule.id})">Edit</button>
        <button class="table-action danger" type="button" onclick="deleteSchedule(${schedule.id})">Delete</button>
      </td>
    </tr>`).join('');
}

function populateSourceSelects() {
  const options = state.sources.map((source) =>
    `<option value="${source.id}">${escapeHtml(source.source_name)} — ${money.format(source.standard_amount)} ${titleCase(source.payment_frequency)}</option>`
  ).join('');
  ['#scheduleSource', '#generateSource'].forEach((selector) => {
    const selected = $(selector).value;
    $(selector).innerHTML = options || '<option value="">Add an income source first</option>';
    if (selected) $(selector).value = selected;
  });
}

function showOnlyForm(formId) {
  ['sourceForm', 'scheduleForm', 'generateForm'].forEach((id) => { $('#' + id).hidden = id !== formId; });
  $('#' + formId).scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function openSourceForm(source = null) {
  $('#sourceForm').reset();
  $('#sourceId').value = source?.id || '';
  $('#sourceFormTitle').textContent = source ? 'Edit income source' : 'Add income source';
  $('#sourceName').value = source?.source_name || '';
  $('#incomeType').value = source?.income_type || 'Salary';
  $('#standardAmount').value = source?.standard_amount ?? '';
  $('#paymentFrequency').value = source?.payment_frequency || 'fortnightly';
  $('#sourceActive').checked = source ? Boolean(source.active) : true;
  showOnlyForm('sourceForm');
}

window.editSource = (id) => openSourceForm(state.sources.find((item) => item.id === id));
window.deleteSource = async (id) => {
  if (!confirm('Delete this income source? Sources with pay schedules must be marked inactive instead.')) return;
  try { await api(`/api/income-sources/${id}`, { method: 'DELETE' }); notify('Income source deleted.'); await refreshAll(); }
  catch (error) { notify(error.message, true); }
};

async function saveSource(event) {
  event.preventDefault();
  const id = $('#sourceId').value;
  const payload = {
    source_name: $('#sourceName').value.trim(), income_type: $('#incomeType').value,
    standard_amount: Number($('#standardAmount').value), payment_frequency: $('#paymentFrequency').value,
    active: $('#sourceActive').checked,
  };
  try {
    await api(id ? `/api/income-sources/${id}` : '/api/income-sources', { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    $('#sourceForm').hidden = true; notify(`Income source ${id ? 'updated' : 'created'}.`); await refreshAll();
  } catch (error) { notify(error.message, true); }
}

function openScheduleForm(schedule = null) {
  $('#scheduleForm').reset();
  $('#scheduleId').value = schedule?.id || '';
  $('#scheduleFormTitle').textContent = schedule ? 'Edit pay schedule' : 'Add pay schedule';
  $('#scheduleSource').value = schedule?.income_source_id || state.sources[0]?.id || '';
  $('#expectedDate').value = schedule?.expected_pay_date || `${$('#monthPicker').value}-01`;
  $('#expectedAmount').value = schedule?.expected_amount ?? state.sources[0]?.standard_amount ?? '';
  $('#paymentStatus').value = schedule?.status || 'scheduled';
  $('#receivedDate').value = schedule?.received_date || '';
  $('#actualAmount').value = schedule?.actual_amount ?? '';
  $('#scheduleNotes').value = schedule?.notes || '';
  syncReceivedFields(); showOnlyForm('scheduleForm');
}

window.editSchedule = (id) => openScheduleForm(state.schedules.find((item) => item.id === id));
window.deleteSchedule = async (id) => {
  if (!confirm('Delete this pay schedule?')) return;
  try { await api(`/api/pay-schedules/${id}`, { method: 'DELETE' }); notify('Pay schedule deleted.'); await refreshAll(); }
  catch (error) { notify(error.message, true); }
};

function syncReceivedFields() {
  const received = $('#paymentStatus').value === 'received';
  $('#receivedDate').required = received; $('#actualAmount').required = received;
  if (received && !$('#receivedDate').value) $('#receivedDate').value = new Date().toISOString().slice(0, 10);
  if (received && !$('#actualAmount').value) $('#actualAmount').value = $('#expectedAmount').value;
}

async function saveSchedule(event) {
  event.preventDefault();
  const id = $('#scheduleId').value;
  const payload = {
    income_source_id: Number($('#scheduleSource').value), expected_pay_date: $('#expectedDate').value,
    expected_amount: Number($('#expectedAmount').value), status: $('#paymentStatus').value,
    received_date: $('#receivedDate').value || null,
    actual_amount: $('#actualAmount').value ? Number($('#actualAmount').value) : null,
    notes: $('#scheduleNotes').value.trim(),
  };
  try {
    await api(id ? `/api/pay-schedules/${id}` : '/api/pay-schedules', { method: id ? 'PUT' : 'POST', body: JSON.stringify(payload) });
    $('#scheduleForm').hidden = true; notify(`Pay schedule ${id ? 'updated' : 'created'}.`); await refreshAll();
  } catch (error) { notify(error.message, true); }
}

async function generateSchedules(event) {
  event.preventDefault();
  try {
    const result = await api('/api/pay-schedules/generate', { method: 'POST', body: JSON.stringify({
      income_source_id: Number($('#generateSource').value), start_date: $('#generateStart').value,
      count: Number($('#generateCount').value),
    }) });
    $('#generateForm').hidden = true; notify(`${result.count} pay schedule${result.count === 1 ? '' : 's'} generated.`); await refreshAll();
  } catch (error) { notify(error.message, true); }
}

async function checkAiStatus() {
  try {
    const result = await api('/api/ai/status');
    $('#aiStatus').textContent = result.model_installed ? 'Online' : 'Model missing';
    $('#aiStatus').classList.toggle('online', result.model_installed);
  } catch { $('#aiStatus').textContent = 'Offline'; }
}

async function sendChat(event) {
  event.preventDefault();
  const input = $('#chatInput'); const message = input.value.trim();
  if (!message) return;
  const priorHistory = state.chatHistory.slice(-6);
  addChatBubble(message, 'user'); state.chatHistory.push({ role: 'user', content: message }); input.value = '';
  setBusy($('#sendChatButton'), true, 'Thinking…');
  try {
    const result = await api('/api/ai/chat', { method: 'POST', body: JSON.stringify({ message, month: $('#monthPicker').value, history: priorHistory }) });
    addChatBubble(result.answer, 'assistant'); state.chatHistory.push({ role: 'assistant', content: result.answer });
  } catch (error) { addChatBubble(error.message, 'assistant error'); }
  finally { setBusy($('#sendChatButton'), false, 'Send'); }
}

async function analyseMonth() {
  setBusy($('#analyseButton'), true, 'Analysing…');
  addChatBubble(`Analyse my income for ${$('#monthPicker').value}.`, 'user');
  try {
    const result = await api('/api/ai/analyse', { method: 'POST', body: JSON.stringify({ month: $('#monthPicker').value }) });
    addChatBubble(result.answer, 'assistant'); state.chatHistory.push({ role: 'assistant', content: result.answer });
  } catch (error) { addChatBubble(error.message, 'assistant error'); }
  finally { setBusy($('#analyseButton'), false, 'Analyse month'); }
}

function addChatBubble(text, className) {
  const bubble = document.createElement('div'); bubble.className = `chat-bubble ${className}`; bubble.textContent = text;
  $('#chatMessages').appendChild(bubble); $('#chatMessages').scrollTop = $('#chatMessages').scrollHeight;
}

function notify(message, isError = false) {
  const box = $('#notification'); box.textContent = message; box.hidden = false; box.classList.toggle('error', isError);
  clearTimeout(notify.timer); notify.timer = setTimeout(() => { box.hidden = true; }, 5000);
}
function setBusy(button, busy, label) { button.disabled = busy; button.textContent = label; }
function titleCase(value) { return String(value).replace('-', ' ').replace(/\b\w/g, (char) => char.toUpperCase()); }
function formatDate(value) { return new Date(`${value}T00:00:00`).toLocaleDateString('en-AU', { day: '2-digit', month: 'short', year: 'numeric' }); }
function escapeHtml(value) { const div = document.createElement('div'); div.textContent = String(value ?? ''); return div.innerHTML; }
