"""
Expense database service — owns the SQLite file exclusively. Exposes a
plain REST API over categories/expenses; expense-backend is the only
thing allowed to call it. Mirrors the shape of bill-tracker/database and
finance-application/database (own container, own port, own DATABASE_PATH).

Every record belongs to a single user. Every route requires a `user_id`
query parameter (expense-backend supplies it from the validated session)
and every read/write is scoped to that user_id, so different users never
see or touch each other's categories/expenses — mirrors bill-tracker's
user_id-per-row pattern.
"""
from flask import Flask, request, jsonify
from database import get_db, init_db

app = Flask(__name__)
init_db()


def row_to_dict(row):
    return dict(row) if row is not None else None


def get_user_id():
    """Reads and validates the required user_id query parameter."""
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return None, (jsonify({"error": "user_id is required"}), 400)
    return user_id, None


def category_belongs_to_user(conn, category_id, user_id):
    if category_id is None:
        return True
    row = conn.execute(
        "SELECT id FROM categories WHERE id = ? AND user_id = ?", (category_id, user_id)
    ).fetchone()
    return row is not None


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "expense-database"})


# ---------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------

@app.route("/categories", methods=["GET"])
def get_categories():
    user_id, error = get_user_id()
    if error:
        return error
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM categories WHERE user_id = ? ORDER BY name", (user_id,)
    ).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/categories", methods=["POST"])
def create_category():
    user_id, error = get_user_id()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (user_id, name, data.get("type", "Discretionary")),
        )
        conn.commit()
    except Exception:
        conn.close()
        return jsonify({"error": "Category already exists"}), 409
    new_id = cur.lastrowid
    row = conn.execute("SELECT * FROM categories WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/categories/<int:cat_id>", methods=["PUT"])
def update_category(cat_id):
    user_id, error = get_user_id()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM categories WHERE id = ? AND user_id = ?", (cat_id, user_id)
    ).fetchone()
    if existing is None:
        conn.close()
        return jsonify({"error": "Category not found"}), 404
    conn.execute(
        "UPDATE categories SET name = ?, type = ? WHERE id = ? AND user_id = ?",
        (data.get("name", existing["name"]), data.get("type", existing["type"]), cat_id, user_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM categories WHERE id = ?", (cat_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route("/categories/<int:cat_id>", methods=["DELETE"])
def delete_category(cat_id):
    user_id, error = get_user_id()
    if error:
        return error
    conn = get_db()
    conn.execute("DELETE FROM categories WHERE id = ? AND user_id = ?", (cat_id, user_id))
    conn.commit()
    conn.close()
    return "", 204


# ---------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------

@app.route("/expenses", methods=["GET"])
def get_expenses():
    user_id, error = get_user_id()
    if error:
        return error
    category_id = request.args.get("category_id")
    conn = get_db()
    query = (
        "SELECT expenses.*, categories.name AS category_name "
        "FROM expenses LEFT JOIN categories ON expenses.category_id = categories.id "
        "WHERE expenses.user_id = ?"
    )
    params = [user_id]
    if category_id:
        query += " AND expenses.category_id = ?"
        params.append(category_id)
    query += " ORDER BY date DESC, expenses.id DESC"
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/expenses/<int:expense_id>", methods=["GET"])
def get_expense(expense_id):
    user_id, error = get_user_id()
    if error:
        return error
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
    ).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(row_to_dict(row))


@app.route("/expenses", methods=["POST"])
def create_expense():
    user_id, error = get_user_id()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    required = ("amount", "description", "date")
    if any(k not in data for k in required):
        return jsonify({"error": "amount, description and date are required"}), 400
    conn = get_db()
    category_id = data.get("category_id") or None
    if not category_belongs_to_user(conn, category_id, user_id):
        conn.close()
        return jsonify({"error": "Category not found"}), 400
    cur = conn.execute(
        "INSERT INTO expenses (user_id, amount, description, merchant, category_id, date) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            user_id, data["amount"], data["description"], data.get("merchant", ""),
            category_id, data["date"],
        ),
    )
    conn.commit()
    new_id = cur.lastrowid
    row = conn.execute("SELECT * FROM expenses WHERE id = ?", (new_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route("/expenses/<int:expense_id>", methods=["PUT"])
def update_expense(expense_id):
    user_id, error = get_user_id()
    if error:
        return error
    data = request.get_json(silent=True) or {}
    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
    ).fetchone()
    if existing is None:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    category_id = data.get("category_id", existing["category_id"])
    if not category_belongs_to_user(conn, category_id, user_id):
        conn.close()
        return jsonify({"error": "Category not found"}), 400
    conn.execute(
        "UPDATE expenses SET amount=?, description=?, merchant=?, category_id=?, date=? "
        "WHERE id=? AND user_id=?",
        (
            data.get("amount", existing["amount"]),
            data.get("description", existing["description"]),
            data.get("merchant", existing["merchant"]),
            category_id,
            data.get("date", existing["date"]),
            expense_id,
            user_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route("/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    user_id, error = get_user_id()
    if error:
        return error
    conn = get_db()
    existing = conn.execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id)
    ).fetchone()
    if existing is None:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    conn.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (expense_id, user_id))
    conn.commit()
    conn.close()
    return "", 204


@app.errorhandler(Exception)
def unhandled_error(exc):
    app.logger.exception("Unhandled expense-database error")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6002)
