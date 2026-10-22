let bills = [];
const TOKEN_KEY = "finance_token";
const $ = (id) => document.getElementById(id);
function token() { return localStorage.getItem(TOKEN_KEY) || ""; }

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const response = await fetch(`/api${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}
function money(value) { return new Intl.NumberFormat(undefined, { style: "currency", currency: "AUD" }).format(Number(value || 0)); }
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[ch])); }

function renderBills() {
  const body = $("bill-table");
  if (!bills.length) { body.innerHTML = '<tr><td colspan="6" class="empty">No bills yet. Add your first bill above.</td></tr>'; return; }
  body.innerHTML = bills.map(bill => `<tr><td><strong>${escapeHtml(bill.name)}</strong></td><td>${money(bill.amount)}</td><td>${escapeHtml(bill.due_date)}</td><td>${escapeHtml(bill.frequency)}</td><td><span class="status ${escapeHtml(bill.status)}">${escapeHtml(bill.status)}</span></td><td><div class="actions"><button class="secondary" onclick="openEdit(${bill.id})">Edit</button><button class="danger" onclick="removeBill(${bill.id})">Delete</button></div></td></tr>`).join("");
}

async function loadAll() {
  try {
    const [billData, summary, health] = await Promise.all([api("/bills"), api("/summary"), api("/health")]);
    bills = billData; renderBills();
    $("bill-count").textContent = summary.bill_count;
    $("total-amount").textContent = money(summary.total_amount);
    $("pending-amount").textContent = money(summary.pending_amount);
    $("overdue-count").textContent = summary.overdue_count;
    $("last-updated").textContent = `Updated ${new Date().toLocaleString()}`;
    $("health").textContent = health.ollama ? `Ollama connected · ${health.ollama_model}` : "Ollama unavailable";
  } catch (error) {
    $("health").textContent = error.message;
    if (/authentication|session|expired|invalid/i.test(error.message)) showGate();
  }
}
function showGate() {
  const homeUrl = (window.FINANCE_URL || document.body.dataset.financeUrl);
  const main = document.createElement("main");
  const title = document.createElement("h1"); title.textContent = "Sign in required";
  const text = document.createElement("p"); text.textContent = "Open Bill Tracker from the Finance Application home page.";
  const link = document.createElement("a"); link.href = homeUrl; link.textContent = "Return to Finance Application";
  main.append(title, text, link); document.body.replaceChildren(main);
}
function openCreate() { $("dialog-title").textContent = "Add bill"; $("bill-id").value = ""; $("bill-form").reset(); $("bill-frequency").value = "Monthly"; $("bill-status").value = "Pending"; $("form-error").textContent = ""; $("bill-dialog").showModal(); }
function openEdit(id) { const bill = bills.find(item => item.id === id); if (!bill) return; $("dialog-title").textContent = "Edit bill"; $("bill-id").value = bill.id; $("bill-name").value = bill.name; $("bill-amount").value = bill.amount; $("bill-due").value = bill.due_date; $("bill-frequency").value = bill.frequency; $("bill-status").value = bill.status; $("form-error").textContent = ""; $("bill-dialog").showModal(); }
function closeDialog() { $("bill-dialog").close(); }
async function removeBill(id) { const bill = bills.find(item => item.id === id); if (!bill || !confirm(`Delete “${bill.name}”?`)) return; try { await api(`/bills/${id}`, { method: "DELETE" }); await loadAll(); } catch (error) { alert(error.message); } }

$("bill-form").addEventListener("submit", async event => {
  event.preventDefault();
  const id = $("bill-id").value;
  const payload = { name: $("bill-name").value.trim(), amount: Number($("bill-amount").value), due_date: $("bill-due").value, frequency: $("bill-frequency").value, status: $("bill-status").value };
  try { await api(id ? `/bills/${id}` : "/bills", { method: id ? "PUT" : "POST", body: JSON.stringify(payload) }); closeDialog(); await loadAll(); }
  catch (error) { $("form-error").textContent = error.message; }
});

function appendChat(role, text) { const log = $("chat-log"); const div = document.createElement("div"); div.className = `message ${role}`; div.textContent = text; log.appendChild(div); log.scrollTop = log.scrollHeight; return div; }
$("chat-form").addEventListener("submit", async event => {
  event.preventDefault(); const input = $("chat-input"); const message = input.value.trim(); if (!message) return;
  appendChat("user", message); input.value = ""; const pending = appendChat("assistant", "Thinking…");
  try { const data = await api("/chat", { method: "POST", body: JSON.stringify({ message }) }); pending.textContent = data.answer; }
  catch (error) { pending.textContent = `Error: ${error.message}`; }
});

const queryToken = new URLSearchParams(window.location.search).get("token");
if (queryToken) { localStorage.setItem(TOKEN_KEY, queryToken); window.history.replaceState({}, document.title, window.location.pathname); }
if (!token()) showGate(); else loadAll();

// Release 1: shared MCP + RAG server access (via this frontend's own
// /api proxy - see app.py's backend_proxy).
function renderBillsSummaryText(result) {
  if (result && result.error) {
    return `<div class="mcp-error">${escapeHtml(result.error)}</div>`;
  }
  if (!result || typeof result !== "object") {
    return '<div class="mcp-empty">No summary available.</div>';
  }

  return `
    <div class="mcp-summary-grid">
      <div class="mcp-stat"><span>Total bills</span><strong>${result.bill_count ?? 0}</strong></div>
      <div class="mcp-stat"><span>Total value</span><strong>${money(result.total_amount)}</strong></div>
      <div class="mcp-stat"><span>Pending</span><strong>${money(result.pending_amount)}</strong></div>
      <div class="mcp-stat"><span>Overdue</span><strong>${result.overdue_count ?? 0}</strong></div>
    </div>
  `;
}

function renderMcpBills(result) {
  if (result && result.error) {
    return `<div class="mcp-error">${escapeHtml(result.error)}</div>`;
  }

  if (!Array.isArray(result)) {
    return '<div class="mcp-empty">No bills returned.</div>';
  }

  if (!result.length) {
    return '<div class="mcp-empty">You have no bills.</div>';
  }

  return `
    <div class="mcp-table-wrap">
      <table class="mcp-table">
        <thead>
          <tr>
            <th>Bill</th>
            <th>Amount</th>
            <th>Due date</th>
            <th>Frequency</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${result.map(bill => `
            <tr>
              <td><strong>${escapeHtml(bill.name ?? "Unnamed bill")}</strong></td>
              <td>${money(bill.amount)}</td>
              <td>${escapeHtml(bill.due_date ?? "—")}</td>
              <td>${escapeHtml(bill.frequency ?? "—")}</td>
              <td><span class="status ${escapeHtml(bill.status ?? "")}">${escapeHtml(bill.status ?? "Unknown")}</span></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
    <p class="mcp-result-count">Showing all ${result.length} bill${result.length === 1 ? "" : "s"} returned by MCP.</p>
  `;
}

async function callMcpTool(tool, renderer) {
  const resultEl = $("mcp-result");
  resultEl.innerHTML = '<div class="mcp-loading">Loading…</div>';

  try {
    const data = await api("/mcp/query", {
      method: "POST",
      body: JSON.stringify({ tool })
    });
    resultEl.innerHTML = renderer(data.result);
  } catch (error) {
    resultEl.innerHTML = `<div class="mcp-error">Error: ${escapeHtml(error.message)}</div>`;
  }
}

$("mcp-summary-button").addEventListener("click", () => {
  callMcpTool("get_bills_summary", renderBillsSummaryText);
});

$("mcp-bills-button").addEventListener("click", () => {
  callMcpTool("get_bills", renderMcpBills);
});

$("rag-form").addEventListener("submit", async event => {
  event.preventDefault();
  const input = $("rag-input");
  const message = input.value.trim();
  if (!message) return;
  const answerEl = $("rag-answer");
  answerEl.innerHTML = "<p>Thinking…</p>";
  try {
    const data = await api("/rag/ask", { method: "POST", body: JSON.stringify({ message }) });
    const citations = data.citations && data.citations.length
      ? `<p class="rag-citations">Sources: ${data.citations.map(escapeHtml).join(", ")}</p>`
      : "";
    answerEl.innerHTML = `<p class="rag-confidence">Confidence: <strong>${escapeHtml(data.confidence_category || "")}</strong></p><p>${escapeHtml(data.answer || "")}</p>${citations}`;
  } catch (error) {
    answerEl.innerHTML = `<p class="error">${escapeHtml(error.message)}</p>`;
  }
  input.value = "";
});


// Release 2: shared Planner / Worker / Reviewer workflow with explicit human review.
function maNode(tag, text, parent) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  parent.appendChild(node);
  return node;
}
function renderMultiAgentRun(run) {
  const root = $("multi-agent-result");
  if (!root) return;
  root.replaceChildren();
  maNode("h3", "Status: " + run.status.replaceAll("_", " "), root);
  maNode("p", "Run " + run.run_id + " · Corrections: " + (run.correction_count || 0) + "/3", root);
  const section = (title, value) => {
    const details = maNode("details", undefined, root);
    maNode("summary", title, details);
    maNode("pre", typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2), details);
  };
  section("Planner plan", run.plan || {});
  section("Worker proposal", run.worker_output || "");
  section("Reviewer assessment", run.review || {});
  if (run.status === "awaiting_human_review") {
    maNode("p", "Human review required. Approval is explicit and will not modify bills automatically.", root);
    const feedback = maNode("textarea", undefined, root);
    feedback.rows = 3; feedback.maxLength = 2000;
    feedback.placeholder = "Optional rejection reason or required correction instructions";
    feedback.setAttribute("aria-label", "Review feedback");
    const actions = maNode("div", undefined, root);
    actions.className = "actions";
    [["approve", "Approve"], ["correct", "Request correction"], ["reject", "Reject"]].forEach(([decision, label]) => {
      const button = maNode("button", label, actions);
      if (decision !== "approve") button.className = decision === "reject" ? "danger" : "secondary";
      button.type = "button";
      button.addEventListener("click", async () => {
        const note = feedback.value.trim();
        if (decision === "correct" && !note) { alert("Enter correction instructions first."); return; }
        button.disabled = true;
        try {
          const updated = await api("/multi-agent/runs/" + run.run_id + "/decision", {
            method: "POST", body: JSON.stringify({ decision, feedback: note })
          });
          renderMultiAgentRun(updated);
        } catch (error) {
          maNode("p", "Error: " + error.message, root);
          button.disabled = false;
        }
      });
    });
  } else if (run.status === "approved") {
    maNode("p", "Approved by human reviewer.", root);
  } else if (run.status === "rejected") {
    maNode("p", "Rejected by human reviewer. No application data was changed.", root);
  }
}
async function loadMultiAgentRuns() {
  const root = $("multi-agent-result");
  if (!root) return;
  try {
    const data = await api("/multi-agent/runs");
    if (data.runs && data.runs.length) renderMultiAgentRun(data.runs[0]);
    else root.textContent = "No review run yet.";
  } catch (error) { root.textContent = "Multi-Agent Server: " + error.message; }
}
const multiAgentForm = $("multi-agent-form");
if (multiAgentForm) {
  multiAgentForm.addEventListener("submit", async event => {
    event.preventDefault();
    const task = $("multi-agent-task").value.trim();
    if (!task) return;
    const root = $("multi-agent-result"); root.textContent = "Running Planner, Worker and Reviewer. This may take a few minutes…";
    const submit = multiAgentForm.querySelector("button[type=submit]"); submit.disabled = true;
    try {
      const run = await api("/multi-agent/run", {method: "POST", body: JSON.stringify({task})});
      renderMultiAgentRun(run);
    } catch (error) { root.textContent = "Multi-Agent error: " + error.message; }
    finally { submit.disabled = false; }
  });
  if (token()) loadMultiAgentRuns();
}
