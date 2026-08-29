const API_BASE = "http://localhost:5001/api";

let currentUserId = document.getElementById("userIdInput").value.trim();
let activeBudgetId = null;

function apiHeaders(extra = {}) {
  return {
    "Content-Type": "application/json",
    "X-User-Id": currentUserId,
    ...extra,
  };
}

function showMessage(elementId, text, isError = false) {
  const el = document.getElementById(elementId);
  el.textContent = text;
  el.classList.remove("error", "success");
  el.classList.add(isError ? "error" : "success");
}

async function fetchBudgets() {
  const res = await fetch(`${API_BASE}/budgets`, {
    headers: apiHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to load budgets (status ${res.status})`);
  }
  return res.json();
}

async function createBudget(payload) {
  const res = await fetch(`${API_BASE}/budgets`, {
    method: "POST",
    headers: apiHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to create budget (status ${res.status})`);
  }
  return res.json();
}

async function deleteBudget(budgetId) {
  const res = await fetch(`${API_BASE}/budgets/${budgetId}`, {
    method: "DELETE",
    headers: apiHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to delete budget (status ${res.status})`);
  }
}

async function fetchCategories(budgetId) {
  const res = await fetch(`${API_BASE}/budgets/${budgetId}/categories`, {
    headers: apiHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to load categories (status ${res.status})`);
  }
  return res.json();
}

async function createCategory(budgetId, payload) {
  const res = await fetch(`${API_BASE}/budgets/${budgetId}/categories`, {
    method: "POST",
    headers: apiHeaders(),
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Failed to create category (status ${res.status})`);
  }
  return res.json();
}

async function deleteCategory(categoryId) {
  const res = await fetch(`${API_BASE}/categories/${categoryId}`, {
    method: "DELETE",
    headers: apiHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Failed to delete category (status ${res.status})`);
  }
}

function renderBudgets(budgets) {
  const container = document.getElementById("budgetsList");
  container.innerHTML = "";

  if (!budgets.length) {
    container.innerHTML = `<p>No budgets yet for user "${currentUserId}".</p>`;
    return;
  }

  budgets.forEach((budget) => {
    const card = document.createElement("div");
    card.className = "budget-card";

    card.innerHTML = `
      <div class="budget-meta">
        <strong>${budget.month}/${budget.year}</strong>
        <span>Created: ${budget.created_date} · 
          <span class="badge ${budget.status}">${budget.status}</span>
        </span>
      </div>
      <div class="budget-actions">
        <button class="secondary" data-action="categories" data-id="${budget.budget_id}">Categories</button>
        <button class="danger" data-action="delete" data-id="${budget.budget_id}">Delete</button>
      </div>
    `;

    container.appendChild(card);
  });

  container.querySelectorAll('button[data-action="categories"]').forEach((btn) => {
    btn.addEventListener("click", () => openCategoriesPanel(btn.dataset.id));
  });

  container.querySelectorAll('button[data-action="delete"]').forEach((btn) => {
    btn.addEventListener("click", () => handleDeleteBudget(btn.dataset.id));
  });
}

async function refreshBudgets() {
  try {
    const budgets = await fetchBudgets();
    renderBudgets(budgets);
  } catch (err) {
    document.getElementById("budgetsList").innerHTML =
      `<p class="form-message error">${err.message}</p>`;
  }
}

async function handleDeleteBudget(budgetId) {
  if (!confirm("Delete this budget and all its categories?")) return;
  try {
    await deleteBudget(budgetId);
    await refreshBudgets();
    if (activeBudgetId === budgetId) {
      document.getElementById("categoriesPanel").classList.add("hidden");
      activeBudgetId = null;
    }
  } catch (err) {
    alert(err.message);
  }
}

function renderCategories(categories) {
  const tbody = document.getElementById("categoriesTableBody");
  tbody.innerHTML = "";

  categories.forEach((cat) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${cat.category_name}</td>
      <td>$${Number(cat.allocated_amount).toFixed(2)}</td>
      <td>${cat.notes || ""}</td>
      <td><button data-action="delete-category" data-id="${cat.category_id}">Delete</button></td>
    `;
    tbody.appendChild(row);
  });

  tbody.querySelectorAll('button[data-action="delete-category"]').forEach((btn) => {
    btn.addEventListener("click", () => handleDeleteCategory(btn.dataset.id));
  });
}

async function openCategoriesPanel(budgetId) {
  activeBudgetId = budgetId;
  document.getElementById("activeBudgetLabel").textContent = `#${budgetId}`;
  document.getElementById("categoriesPanel").classList.remove("hidden");
  await refreshCategories();
}

async function refreshCategories() {
  if (!activeBudgetId) return;
  try {
    const categories = await fetchCategories(activeBudgetId);
    renderCategories(categories);
  } catch (err) {
    document.getElementById("categoriesTableBody").innerHTML =
      `<tr><td colspan="4" class="form-message error">${err.message}</td></tr>`;
  }
}

async function handleDeleteCategory(categoryId) {
  if (!confirm("Delete this category?")) return;
  try {
    await deleteCategory(categoryId);
    await refreshCategories();
  } catch (err) {
    alert(err.message);
  }
}

document.getElementById("userIdApply").addEventListener("click", () => {
  currentUserId = document.getElementById("userIdInput").value.trim() || "test01";
  refreshBudgets();
});

document.getElementById("refreshBudgets").addEventListener("click", refreshBudgets);

document.getElementById("createBudgetForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const month = parseInt(document.getElementById("month").value, 10);
  const year = parseInt(document.getElementById("year").value, 10);
  const status = document.getElementById("status").value;

  try {
    await createBudget({ month, year, status });
    showMessage("createBudgetMessage", "Budget created successfully.");
    document.getElementById("createBudgetForm").reset();
    await refreshBudgets();
  } catch (err) {
    showMessage("createBudgetMessage", err.message, true);
  }
});

document.getElementById("createCategoryForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!activeBudgetId) return;

  const category_name = document.getElementById("categoryName").value.trim();
  const allocated_amount = parseFloat(document.getElementById("allocatedAmount").value);
  const notes = document.getElementById("categoryNotes").value.trim();

  try {
    await createCategory(activeBudgetId, { category_name, allocated_amount, notes });
    showMessage("createCategoryMessage", "Category added successfully.");
    document.getElementById("createCategoryForm").reset();
    await refreshCategories();
  } catch (err) {
    showMessage("createCategoryMessage", err.message, true);
  }
});

document.getElementById("closeCategoriesPanel").addEventListener("click", () => {
  document.getElementById("categoriesPanel").classList.add("hidden");
  activeBudgetId = null;
});

refreshBudgets();