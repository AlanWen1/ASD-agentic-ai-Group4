let bills = [];

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function money(value) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "AUD" }).format(Number(value || 0));
}

function renderBills() {
  const body = $("bill-table");
  if (!bills.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">No bills yet. Add your first bill above.</td></tr>';
    return;
  }
  body.innerHTML = bills.map(bill => `
    <tr>
      <td><strong>${escapeHtml(bill.name)}</strong></td>
      <td>${money(bill.amount)}</td>
      <td>${escapeHtml(bill.due_date)}</td>
      <td>${escapeHtml(bill.frequency)}</td>
      <td><span class="status ${escapeHtml(bill.status)}">${escapeHtml(bill.status)}</span></td>
      <td><div class="actions">
        <button class="secondary" onclick="openEdit(${bill.id})">Edit</button>
        <button class="danger" onclick="removeBill(${bill.id})">Delete</button>
      </div></td>
    </tr>`).join("");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[ch]));
}

async function loadAll() {
  try {
    const [billData, summary, health] = await Promise.all([api("/bills"), api("/summary"), api("/health")]);
    bills = billData;
    renderBills();
    $("bill-count").textContent = summary.bill_count;
    $("total-amount").textContent = money(summary.total_amount);
    $("pending-amount").textContent = money(summary.pending_amount);
    $("overdue-count").textContent = summary.overdue_count;
    $("last-updated").textContent = `Updated ${new Date().toLocaleString()}`;
    const model = health.ollama ? `Ollama connected · ${health.ollama_model}` : "Ollama unavailable";
    $("health").textContent = health.database ? model : "Backend/database unavailable";
  } catch (error) {
    $("health").textContent = "Service error";
    console.error(error);
  }
}

function openCreate() {
  $("dialog-title").textContent = "Add bill";
  $("bill-id").value = "";
  $("bill-form").reset();
  $("bill-frequency").value = "Monthly";
  $("bill-status").value = "Pending";
  $("form-error").textContent = "";
  $("bill-dialog").showModal();
}

function openEdit(id) {
  const bill = bills.find(item => item.id === id);
  if (!bill) return;
  $("dialog-title").textContent = "Edit bill";
  $("bill-id").value = bill.id;
  $("bill-name").value = bill.name;
  $("bill-amount").value = bill.amount;
  $("bill-due").value = bill.due_date;
  $("bill-frequency").value = bill.frequency;
  $("bill-status").value = bill.status;
  $("form-error").textContent = "";
  $("bill-dialog").showModal();
}

function closeDialog() { $("bill-dialog").close(); }

$("bill-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = $("bill-id").value;
  const payload = {
    name: $("bill-name").value.trim(),
    amount: Number($("bill-amount").value),
    due_date: $("bill-due").value,
    frequency: $("bill-frequency").value,
    status: $("bill-status").value,
  };
  try {
    if (id) await api(`/bills/${id}`, { method: "PUT", body: JSON.stringify(payload) });
    else await api("/bills", { method: "POST", body: JSON.stringify(payload) });
    closeDialog();
    await loadAll();
  } catch (error) {
    $("form-error").textContent = error.message;
  }
});

async function removeBill(id) {
  const bill = bills.find(item => item.id === id);
  if (!bill || !confirm(`Delete “${bill.name}”?`)) return;
  try {
    await api(`/bills/${id}`, { method: "DELETE" });
    await loadAll();
  } catch (error) {
    alert(error.message);
  }
}

function appendChat(role, text) {
  const log = $("chat-log");
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = $("chat-input");
  const message = input.value.trim();
  if (!message) return;
  appendChat("user", message);
  input.value = "";
  const pending = appendChat("assistant", "Thinking…");
  try {
    const data = await api("/chat", { method: "POST", body: JSON.stringify({ message }) });
    pending.textContent = data.answer;
  } catch (error) {
    pending.textContent = `Error: ${error.message}`;
  }
});

loadAll();
