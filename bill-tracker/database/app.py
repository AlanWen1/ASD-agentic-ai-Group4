import os
import sqlite3
from contextlib import closing
from datetime import date, datetime

from flask import Flask, jsonify, request

app = Flask(__name__)

DATABASE_PATH = os.environ.get("DATABASE_PATH", "/data/bills.db")
ALLOWED_FREQUENCIES = {"Weekly", "Monthly", "Quarterly", "Yearly", "One-time"}
ALLOWED_STATUSES = {"Pending", "Paid", "Overdue"}


def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    with closing(get_db()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount >= 0),
                due_date TEXT NOT NULL,
                frequency TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def row_to_dict(row):
    return dict(row) if row else None


def validate_bill_payload(payload, partial=False):
    if not isinstance(payload, dict):
        return "JSON object expected"

    required = {"name", "amount", "due_date", "frequency", "status"}
    if not partial:
        missing = required - payload.keys()
        if missing:
            return f"Missing fields: {', '.join(sorted(missing))}"

    if "name" in payload and (not isinstance(payload["name"], str) or not payload["name"].strip()):
        return "name must be a non-empty string"

    if "amount" in payload:
        try:
            amount = float(payload["amount"])
            if amount < 0:
                return "amount must be >= 0"
        except (TypeError, ValueError):
            return "amount must be a number"

    if "due_date" in payload:
        try:
            datetime.strptime(str(payload["due_date"]), "%Y-%m-%d")
        except ValueError:
            return "due_date must use YYYY-MM-DD format"

    if "frequency" in payload and payload["frequency"] not in ALLOWED_FREQUENCIES:
        return f"frequency must be one of: {', '.join(sorted(ALLOWED_FREQUENCIES))}"

    if "status" in payload and payload["status"] not in ALLOWED_STATUSES:
        return f"status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}"

    return None


@app.get("/health")
def health():
    try:
        with closing(get_db()) as conn:
            conn.execute("SELECT 1").fetchone()
        return jsonify({"status": "ok", "service": "database"})
    except sqlite3.Error as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500


@app.get("/bills")
def list_bills():
    with closing(get_db()) as conn:
        rows = conn.execute("SELECT * FROM bills ORDER BY due_date ASC, id ASC").fetchall()
    return jsonify([row_to_dict(row) for row in rows])


@app.get("/bills/<int:bill_id>")
def get_bill(bill_id):
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
    if not row:
        return jsonify({"error": "Bill not found"}), 404
    return jsonify(row_to_dict(row))


@app.post("/bills")
def create_bill():
    payload = request.get_json(silent=True)
    error = validate_bill_payload(payload or {})
    if error:
        return jsonify({"error": error}), 400

    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    values = (
        payload["name"].strip(),
        float(payload["amount"]),
        str(payload["due_date"]),
        payload["frequency"],
        payload["status"],
        now,
        now,
    )
    with closing(get_db()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO bills (name, amount, due_date, frequency, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        conn.commit()
        row = conn.execute("SELECT * FROM bills WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return jsonify(row_to_dict(row)), 201


@app.put("/bills/<int:bill_id>")
def update_bill(bill_id):
    payload = request.get_json(silent=True)
    error = validate_bill_payload(payload or {}, partial=True)
    if error:
        return jsonify({"error": error}), 400

    allowed = ["name", "amount", "due_date", "frequency", "status"]
    changes = {key: payload[key] for key in allowed if key in payload}
    if not changes:
        return jsonify({"error": "At least one editable field is required"}), 400
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    if "amount" in changes:
        changes["amount"] = float(changes["amount"])

    changes["updated_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    set_clause = ", ".join(f"{key} = ?" for key in changes)
    values = list(changes.values()) + [bill_id]

    with closing(get_db()) as conn:
        cursor = conn.execute(f"UPDATE bills SET {set_clause} WHERE id = ?", values)
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "Bill not found"}), 404
        conn.commit()
        row = conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
    return jsonify(row_to_dict(row))


@app.delete("/bills/<int:bill_id>")
def delete_bill(bill_id):
    with closing(get_db()) as conn:
        cursor = conn.execute("DELETE FROM bills WHERE id = ?", (bill_id,))
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "Bill not found"}), 404
        conn.commit()
    return jsonify({"message": "Bill deleted", "id": bill_id})


@app.errorhandler(Exception)
def unhandled_error(exc):
    app.logger.exception("Unhandled database-service error")
    return jsonify({"error": "Internal server error"}), 500


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6004)
