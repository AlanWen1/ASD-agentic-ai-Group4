import os
import sqlite3
from flask import Flask, request, jsonify, g
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_PATH = os.environ.get("DATABASE_PATH", "/data/budget_manager.db")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")
SEED_PATH = os.path.join(BASE_DIR, "seed.sql")
RESET_ON_BOOT = os.environ.get("RESET_DB_ON_BOOT", "false").lower() == "true"


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    print("Schema applied: budgets, budget_categories")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM budgets")
    existing_rows = cur.fetchone()[0]

    if existing_rows == 0 or RESET_ON_BOOT:
        with open(SEED_PATH, "r") as f:
            conn.executescript(f.read())
        print("Seed data inserted")
    else:
        print(f"Existing database found ({existing_rows} rows), skipping seed (idempotent boot)")

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM budgets")
    budget_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM budget_categories")
    category_count = cur.fetchone()[0]
    print(f"budgets: {budget_count} rows | budget_categories: {category_count} rows")

    conn.close()
    print(f"budget-database ready at {DB_PATH}")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def row_to_dict(row):
    return dict(row) if row else None


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "budget-database"}), 200


# ---------------------------------------------------------------------------
# Budgets
# ---------------------------------------------------------------------------

@app.route("/api/budgets", methods=["POST"])
def create_budget():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    month = data.get("month")
    year = data.get("year")
    status = data.get("status", "active")

    if not user_id or month is None or year is None:
        return jsonify({"error": "user_id, month and year are required"}), 400
    if not (1 <= int(month) <= 12):
        return jsonify({"error": "month must be between 1 and 12"}), 400
    if status not in ("active", "archived"):
        return jsonify({"error": "status must be active or archived"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO budgets (user_id, month, year, status) VALUES (?, ?, ?, ?)",
        (user_id, month, year, status),
    )
    db.commit()
    new_budget = db.execute(
        "SELECT * FROM budgets WHERE budget_id = ?", (cur.lastrowid,)
    ).fetchone()
    return jsonify(row_to_dict(new_budget)), 201


@app.route("/api/budgets", methods=["GET"])
def list_budgets():
    user_id = request.args.get("user_id")
    db = get_db()
    if user_id:
        rows = db.execute(
            "SELECT * FROM budgets WHERE user_id = ? ORDER BY year DESC, month DESC",
            (user_id,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM budgets ORDER BY year DESC, month DESC"
        ).fetchall()
    return jsonify([row_to_dict(r) for r in rows]), 200


@app.route("/api/budgets/<int:budget_id>", methods=["GET"])
def get_budget(budget_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM budgets WHERE budget_id = ?", (budget_id,)
    ).fetchone()
    if row is None:
        return jsonify({"error": "Budget not found"}), 404
    return jsonify(row_to_dict(row)), 200


@app.route("/api/budgets/<int:budget_id>", methods=["PUT"])
def update_budget(budget_id):
    db = get_db()
    existing = db.execute(
        "SELECT * FROM budgets WHERE budget_id = ?", (budget_id,)
    ).fetchone()
    if existing is None:
        return jsonify({"error": "Budget not found"}), 404

    data = request.get_json(silent=True) or {}
    month = data.get("month") or existing["month"]
    year = data.get("year") or existing["year"]
    status = data.get("status") or existing["status"]

    if not (1 <= int(month) <= 12):
        return jsonify({"error": "month must be between 1 and 12"}), 400
    if status not in ("active", "archived"):
        return jsonify({"error": "status must be active or archived"}), 400

    db.execute(
        "UPDATE budgets SET month = ?, year = ?, status = ? WHERE budget_id = ?",
        (month, year, status, budget_id),
    )
    db.commit()
    updated = db.execute(
        "SELECT * FROM budgets WHERE budget_id = ?", (budget_id,)
    ).fetchone()
    return jsonify(row_to_dict(updated)), 200

@app.route("/api/budgets/<int:budget_id>", methods=["DELETE"])
def delete_budget(budget_id):
    user_id = request.args.get("user_id")
    db = get_db()
    existing = db.execute(
        "SELECT * FROM budgets WHERE budget_id = ?", (budget_id,)
    ).fetchone()
    if existing is None:
        return jsonify({"error": "Budget not found"}), 404
    if user_id and str(existing["user_id"]) != str(user_id):
        return jsonify({"error": "Budget not found or not owned by this user"}), 404

    db.execute("DELETE FROM budgets WHERE budget_id = ?", (budget_id,))
    db.commit()
    return jsonify({"message": f"Budget {budget_id} deleted"}), 200


# ---------------------------------------------------------------------------
# Budget Categories (nested under a budget)
# ---------------------------------------------------------------------------

@app.route("/api/budgets/<int:budget_id>/categories", methods=["POST"])
def create_category(budget_id):
    db = get_db()
    budget = db.execute(
        "SELECT 1 FROM budgets WHERE budget_id = ?", (budget_id,)
    ).fetchone()
    if budget is None:
        return jsonify({"error": "Budget not found"}), 404

    data = request.get_json(silent=True) or {}
    category_name = data.get("category_name")
    allocated_amount = data.get("allocated_amount")
    notes = data.get("notes")

    if not category_name or allocated_amount is None:
        return jsonify({"error": "category_name and allocated_amount are required"}), 400
    if float(allocated_amount) < 0:
        return jsonify({"error": "allocated_amount must be >= 0"}), 400

    cur = db.execute(
        "INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) "
        "VALUES (?, ?, ?, ?)",
        (budget_id, category_name, allocated_amount, notes),
    )
    db.commit()
    new_cat = db.execute(
        "SELECT * FROM budget_categories WHERE category_id = ?", (cur.lastrowid,)
    ).fetchone()
    return jsonify(row_to_dict(new_cat)), 201


@app.route("/api/budgets/<int:budget_id>/categories", methods=["GET"])
def list_categories(budget_id):
    db = get_db()
    budget = db.execute(
        "SELECT 1 FROM budgets WHERE budget_id = ?", (budget_id,)
    ).fetchone()
    if budget is None:
        return jsonify({"error": "Budget not found"}), 404

    rows = db.execute(
        "SELECT * FROM budget_categories WHERE budget_id = ?", (budget_id,)
    ).fetchall()
    return jsonify([row_to_dict(r) for r in rows]), 200


@app.route("/api/categories/<int:category_id>", methods=["GET"])
def get_category(category_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM budget_categories WHERE category_id = ?", (category_id,)
    ).fetchone()
    if row is None:
        return jsonify({"error": "Category not found"}), 404
    return jsonify(row_to_dict(row)), 200


@app.route("/api/categories/<int:category_id>", methods=["PUT"])
def update_category(category_id):
    db = get_db()
    existing = db.execute(
        "SELECT * FROM budget_categories WHERE category_id = ?", (category_id,)
    ).fetchone()
    if existing is None:
        return jsonify({"error": "Category not found"}), 404

    data = request.get_json(silent=True) or {}
    category_name = data.get("category_name", existing["category_name"])
    allocated_amount = data.get("allocated_amount", existing["allocated_amount"])
    notes = data.get("notes", existing["notes"])

    if float(allocated_amount) < 0:
        return jsonify({"error": "allocated_amount must be >= 0"}), 400

    db.execute(
        "UPDATE budget_categories SET category_name = ?, allocated_amount = ?, notes = ? "
        "WHERE category_id = ?",
        (category_name, allocated_amount, notes, category_id),
    )
    db.commit()
    updated = db.execute(
        "SELECT * FROM budget_categories WHERE category_id = ?", (category_id,)
    ).fetchone()
    return jsonify(row_to_dict(updated)), 200


@app.route("/api/categories/<int:category_id>", methods=["DELETE"])
def delete_category(category_id):
    db = get_db()
    existing = db.execute(
        "SELECT * FROM budget_categories WHERE category_id = ?", (category_id,)
    ).fetchone()
    if existing is None:
        return jsonify({"error": "Category not found"}), 404

    db.execute("DELETE FROM budget_categories WHERE category_id = ?", (category_id,))
    db.commit()
    return jsonify({"message": f"Category {category_id} deleted"}), 200


with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=6001)