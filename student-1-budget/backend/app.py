import os
import sqlite3
import requests
from flask import Flask, request, jsonify, g
from flask_cors import CORS
from agent import run_agent_loop

app = Flask(__name__)
CORS(app)

@app.route("/api/agent/chat", methods=["POST"])
def agent_chat():
    student_id = request.headers.get("X-User-Id")
    if not student_id:
        return jsonify({"error": "X-User-Id header required"}), 400

    body = request.get_json(silent=True) or {}
    user_message = body.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "message is required"}), 400

    try:
        result = run_agent_loop(user_message, student_id)
        return jsonify(result), 200
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Could not reach Ollama. Is it running on localhost:11434?"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "..", "database", "budget_manager.db"))

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def get_user_id():
    """Release 0 scope: trust the X-User-Id header, no validation
    against a central user store yet (pending team auth decision)."""
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        return None, (jsonify({"error": "Missing X-User-Id header"}), 401)
    return user_id, None


def row_to_dict(row):
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Budgets CRUD
# ---------------------------------------------------------------------------

@app.route("/api/budgets", methods=["POST"])
def create_budget():
    user_id, err = get_user_id()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    month = data.get("month")
    year = data.get("year")
    status = data.get("status", "active")

    if month is None or year is None:
        return jsonify({"error": "month and year are required"}), 400
    if not (1 <= int(month) <= 12):
        return jsonify({"error": "month must be between 1 and 12"}), 400
    if status not in ("active", "archived"):
        return jsonify({"error": "status must be active or archived"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO budgets (student_id, month, year, status) VALUES (?, ?, ?, ?)",
        (user_id, month, year, status),
    )
    db.commit()

    new_budget = db.execute(
        "SELECT * FROM budgets WHERE budget_id = ?", (cur.lastrowid,)
    ).fetchone()
    return jsonify(row_to_dict(new_budget)), 201


@app.route("/api/budgets", methods=["GET"])
def list_budgets():
    user_id, err = get_user_id()
    if err:
        return err

    db = get_db()
    rows = db.execute(
        "SELECT * FROM budgets WHERE student_id = ? ORDER BY year DESC, month DESC",
        (user_id,),
    ).fetchall()
    return jsonify([row_to_dict(r) for r in rows]), 200


@app.route("/api/budgets/<int:budget_id>", methods=["GET"])
def get_budget(budget_id):
    user_id, err = get_user_id()
    if err:
        return err

    db = get_db()
    row = db.execute(
        "SELECT * FROM budgets WHERE budget_id = ? AND student_id = ?",
        (budget_id, user_id),
    ).fetchone()
    if row is None:
        return jsonify({"error": "Budget not found"}), 404
    return jsonify(row_to_dict(row)), 200


@app.route("/api/budgets/<int:budget_id>", methods=["PUT"])
def update_budget(budget_id):
    user_id, err = get_user_id()
    if err:
        return err

    db = get_db()
    existing = db.execute(
        "SELECT * FROM budgets WHERE budget_id = ? AND student_id = ?",
        (budget_id, user_id),
    ).fetchone()
    if existing is None:
        return jsonify({"error": "Budget not found"}), 404

    data = request.get_json(silent=True) or {}
    month = data.get("month", existing["month"])
    year = data.get("year", existing["year"])
    status = data.get("status", existing["status"])

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
    user_id, err = get_user_id()
    if err:
        return err

    db = get_db()
    existing = db.execute(
        "SELECT * FROM budgets WHERE budget_id = ? AND student_id = ?",
        (budget_id, user_id),
    ).fetchone()
    if existing is None:
        return jsonify({"error": "Budget not found"}), 404

    db.execute("DELETE FROM budgets WHERE budget_id = ?", (budget_id,))
    db.commit()
    return jsonify({"message": f"Budget {budget_id} deleted"}), 200


# ---------------------------------------------------------------------------
# Budget Categories CRUD (nested under a budget)
# ---------------------------------------------------------------------------

def _budget_owned_by_user(db, budget_id, user_id):
    return db.execute(
        "SELECT 1 FROM budgets WHERE budget_id = ? AND student_id = ?",
        (budget_id, user_id),
    ).fetchone() is not None


@app.route("/api/budgets/<int:budget_id>/categories", methods=["POST"])
def create_category(budget_id):
    user_id, err = get_user_id()
    if err:
        return err

    db = get_db()
    if not _budget_owned_by_user(db, budget_id, user_id):
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
    user_id, err = get_user_id()
    if err:
        return err

    db = get_db()
    if not _budget_owned_by_user(db, budget_id, user_id):
        return jsonify({"error": "Budget not found"}), 404

    rows = db.execute(
        "SELECT * FROM budget_categories WHERE budget_id = ?", (budget_id,)
    ).fetchall()
    return jsonify([row_to_dict(r) for r in rows]), 200


@app.route("/api/categories/<int:category_id>", methods=["PUT"])
def update_category(category_id):
    user_id, err = get_user_id()
    if err:
        return err

    db = get_db()
    existing = db.execute(
        "SELECT bc.* FROM budget_categories bc "
        "JOIN budgets b ON bc.budget_id = b.budget_id "
        "WHERE bc.category_id = ? AND b.student_id = ?",
        (category_id, user_id),
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
    user_id, err = get_user_id()
    if err:
        return err

    db = get_db()
    existing = db.execute(
        "SELECT bc.* FROM budget_categories bc "
        "JOIN budgets b ON bc.budget_id = b.budget_id "
        "WHERE bc.category_id = ? AND b.student_id = ?",
        (category_id, user_id),
    ).fetchone()
    if existing is None:
        return jsonify({"error": "Category not found"}), 404

    db.execute("DELETE FROM budget_categories WHERE category_id = ?", (category_id,))
    db.commit()
    return jsonify({"message": f"Category {category_id} deleted"}), 200


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "budget-manager-backend"}), 200


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
