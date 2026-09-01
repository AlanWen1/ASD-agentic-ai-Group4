from flask import Flask, request, jsonify
from database import get_db, init_db
import requests
import os

app = Flask(__name__)

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:0.5b")

ALLOWED_CATEGORIES = [
    "Groceries", "Dining", "Transport", "Utilities",
    "Entertainment", "Shopping", "Health", "Travel",
    "Education", "Other",
]

init_db()


# ---------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------

@app.route("/api/categories", methods=["GET"])
def get_categories():
    conn = get_db()
    rows = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/categories", methods=["POST"])
def create_category():
    data = request.get_json()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO categories (name, type) VALUES (?, ?)",
        (data["name"], data.get("type", "Discretionary")),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"id": new_id, "name": data["name"], "type": data.get("type", "Discretionary")}), 201


@app.route("/api/categories/<int:cat_id>", methods=["PUT"])
def update_category(cat_id):
    data = request.get_json()
    conn = get_db()
    conn.execute(
        "UPDATE categories SET name = ?, type = ? WHERE id = ?",
        (data["name"], data.get("type", "Discretionary"), cat_id),
    )
    conn.commit()
    conn.close()
    return jsonify({"id": cat_id, **data})


@app.route("/api/categories/<int:cat_id>", methods=["DELETE"])
def delete_category(cat_id):
    conn = get_db()
    conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    return "", 204


# ---------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------

@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    category_id = request.args.get("category_id")
    conn = get_db()
    query = """
        SELECT expenses.*, categories.name AS category_name
        FROM expenses
        LEFT JOIN categories ON expenses.category_id = categories.id
    """
    params = []
    if category_id:
        query += " WHERE expenses.category_id = ?"
        params.append(category_id)
    query += " ORDER BY date DESC, expenses.id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/expenses/<int:expense_id>", methods=["GET"])
def get_expense(expense_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/expenses", methods=["POST"])
def create_expense():
    data = request.get_json()
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO expenses (amount, description, merchant, category_id, date) VALUES (?, ?, ?, ?, ?)",
        (
            data["amount"],
            data["description"],
            data.get("merchant", ""),
            data.get("category_id") or None,
            data["date"],
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return jsonify({"id": new_id, **data}), 201


@app.route("/api/expenses/<int:expense_id>", methods=["PUT"])
def update_expense(expense_id):
    data = request.get_json()
    conn = get_db()
    conn.execute(
        "UPDATE expenses SET amount=?, description=?, merchant=?, category_id=?, date=? WHERE id=?",
        (
            data["amount"],
            data["description"],
            data.get("merchant", ""),
            data.get("category_id") or None,
            data["date"],
            expense_id,
        ),
    )
    conn.commit()
    conn.close()
    return jsonify({"id": expense_id, **data})


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    conn = get_db()
    conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
    return "", 204


# ---------------------------------------------------------------------
# AI: Suggest Category  (calls the team's shared Ollama service)
# ---------------------------------------------------------------------

@app.route("/api/expenses/suggest-category", methods=["POST"])
def suggest_category():
    data = request.get_json() or {}
    description = data.get("description", "")
    merchant = data.get("merchant", "")

    prompt = (
        "You are a financial assistant that categorises personal expenses.\n"
        f"Allowed categories: {', '.join(ALLOWED_CATEGORIES)}.\n"
        f'Expense description: "{description}"\n'
        f'Merchant: "{merchant}"\n'
        "Respond with ONLY the single best matching category name from the "
        "allowed list above. Do not explain your answer. Do not add punctuation."
    )

    try:
        resp = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()
    except requests.exceptions.RequestException as e:
        # AI service down -> fail gracefully instead of crashing the feature
        return jsonify({"category": "Other", "error": f"AI service unavailable: {str(e)}"}), 200

    matched = next((c for c in ALLOWED_CATEGORIES if c.lower() in raw.lower()), "Other")
    return jsonify({"category": matched, "raw_response": raw})


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
