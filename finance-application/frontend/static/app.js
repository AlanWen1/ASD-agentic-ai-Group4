let bills = [];
let registerMode = false;
const $ = (id) => document.getElementById(id);
const TOKEN_KEY = "finance_token";

function token() { return localStorage.getItem(TOKEN_KEY) || ""; }
function setToken(value) { localStorage.setItem(TOKEN_KEY, value); }
function clearToken() { localStorage.removeItem(TOKEN_KEY); }

async function api(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  const response = await fetch(`/api${path}`, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function money(value) {
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "AUD" }).format(Number(value || 0));
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;","\"":"&quot;"}[ch]));
}

function renderBills() {
  const body = $("bill-table");
  if (!bills.length) {
    body.innerHTML = '<tr><td colspan="6" class="empty">No bills yet.</td></tr>';
    return;
  }
  body.innerHTML = bills.map(bill => `
    <tr><td><strong>${escapeHtml(bill.name)}</strong></td><td>${money(bill.amount)}</td><td>${escapeHtml(bill.due_date)}</td><td>${escapeHtml(bill.frequency)}</td><td><span class="status ${escapeHtml(bill.status)}">${escapeHtml(bill.status)}</span></td><td><div class="actions"><button class="secondary" onclick="openEdit(${bill.id})">Edit</button><button class="danger" onclick="removeBill(${bill.id})">Delete</button></div></td></tr>`).join("");
}

async function loadHome() {
  try {
    const [me, health] = await Promise.all([
      api("/auth/me"), api("/health")
    ]);
    $("welcome-name").textContent = me.user.username;
    $("health").textContent = health.status === "ok" ? "Services connected" : "Some services unavailable";
  } catch (error) {
    if (/session|authentication|invalid|expired/i.test(error.message)) showAuth();
    else $("health").textContent = error.message;
  }
}

function showAuth() {
  $("auth-view").hidden = false;
  $("home-view").hidden = true;
  $("identifier").required = true;
}
function updateBillTrackerLink() {
  const link = $("bill-tracker-link");
  if (!link) return;
  const currentToken = token();
  link.href = currentToken
    ? `http://localhost:3004/?token=${encodeURIComponent(currentToken)}`
    : "http://localhost:3004/";
}
function updateExpenseTrackerLink() {
  const link = $("expense-tracker-link");
  if (!link) return;
  const currentToken = token();
  link.href = currentToken
    ? `http://localhost:3002/?token=${encodeURIComponent(currentToken)}`
    : "http://localhost:3002/";
}

function updateIncomeManagerLink() {
  const link = $("income-manager-link");
  if (!link) return;

  const currentToken = token();

  link.href = currentToken
    ? `http://localhost:3003/?token=${encodeURIComponent(currentToken)}`
    : "http://localhost:3003/";
}

function showHome() {
  updateBillTrackerLink();
  updateExpenseTrackerLink();
  updateIncomeManagerLink();

  $("auth-view").hidden = true;
  $("home-view").hidden = false;
  loadHome();
}

function setRegisterMode(value) {
  registerMode = value;
  $("auth-title").textContent = value ? "Create your account" : "Welcome back";
  $("auth-subtitle").textContent = value ? "Register to start managing your finances." : "Sign in to manage your personal finances.";
  $("register-fields").hidden = !value;
  $("username").required = value;
  $("email").required = value;
  $("identifier").hidden = value;
  $("identifier").required = !value;
  $("password").autocomplete = value ? "new-password" : "current-password";
  $("auth-submit").textContent = value ? "Create account" : "Sign in";
  $("auth-switch").textContent = value ? "Already have an account? Sign in" : "Create an account";
  $("auth-error").textContent = "";
}

$("auth-switch").addEventListener("click", () => setRegisterMode(!registerMode));
$("auth-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("auth-error").textContent = "";
  try {
    const payload = registerMode
      ? { username: $("username").value.trim(), email: $("email").value.trim(), password: $("password").value }
      : { identifier: $("identifier").value.trim(), password: $("password").value };
    if (registerMode) await api("/auth/register", { method: "POST", body: JSON.stringify(payload) });
    const loginData = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier: registerMode ? payload.username : payload.identifier, password: payload.password })
    });
    setToken(loginData.token);
    $("auth-form").reset();
    setRegisterMode(false);
    showHome();
  } catch (error) {
    $("auth-error").textContent = error.message;
  }
});

$("logout").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST", body: JSON.stringify({ token: token() }) }); } catch (_) {}
  clearToken();
  showAuth();
  setRegisterMode(false);
});

if (token()) showHome(); else showAuth();
