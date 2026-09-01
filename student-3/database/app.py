"""Database API for Yongjian Zhou's Income & Pay Schedule Manager.

This service is the exclusive owner of the Student 3 SQLite schema. Other
services must use these HTTP endpoints and must never open the database file.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

from flask import Flask, current_app, jsonify, request


FREQUENCIES = {"weekly", "fortnightly", "monthly", "quarterly", "annually", "one-off"}
PAYMENT_STATUSES = {"scheduled", "received", "late", "cancelled"}

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS income_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    source_name TEXT NOT NULL,
    income_type TEXT NOT NULL,
    standard_amount REAL NOT NULL CHECK (standard_amount > 0),
    payment_frequency TEXT NOT NULL CHECK (
        payment_frequency IN ('weekly', 'fortnightly', 'monthly', 'quarterly', 'annually', 'one-off')
    ),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pay_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    income_source_id INTEGER NOT NULL,
    expected_pay_date TEXT NOT NULL,
    expected_amount REAL NOT NULL CHECK (expected_amount > 0),
    received_date TEXT,
    actual_amount REAL CHECK (actual_amount IS NULL OR actual_amount > 0),
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK (
        status IN ('scheduled', 'received', 'late', 'cancelled')
    ),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (income_source_id) REFERENCES income_sources(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_income_sources_active ON income_sources(active);
CREATE INDEX IF NOT EXISTS idx_pay_schedules_date ON pay_schedules(expected_pay_date);
CREATE INDEX IF NOT EXISTS idx_pay_schedules_source ON pay_schedules(income_source_id);
CREATE INDEX IF NOT EXISTS idx_pay_schedules_status ON pay_schedules(status);
"""

SEED_SOURCES = [
    ("UTS Student Assistant", "Salary", 920.00, "fortnightly", 1),
    ("Cafe Weekend Shift", "Salary", 480.00, "weekly", 1),
    ("Freelance Web Design", "Freelance", 750.00, "monthly", 1),
    ("Family Allowance", "Allowance", 500.00, "monthly", 1),
    ("UTS Equity Scholarship", "Scholarship", 1500.00, "quarterly", 1),
    ("Tutoring", "Freelance", 240.00, "fortnightly", 1),
    ("Photography Jobs", "Freelance", 400.00, "monthly", 0),
    ("Marketplace Sales", "Other", 180.00, "one-off", 1),
    ("Interest Income", "Other", 35.00, "monthly", 1),
    ("Room Sublet", "Rental", 620.00, "monthly", 0),
]

SEED_SCHEDULES = [
    (1, "2026-07-17", 920.00, "2026-07-17", 920.00, "received", "July fortnightly pay"),
    (1, "2026-07-31", 920.00, "2026-07-31", 920.00, "received", "July fortnightly pay"),
    (1, "2026-08-14", 920.00, "2026-08-14", 920.00, "received", "August fortnightly pay"),
    (1, "2026-08-28", 920.00, None, None, "scheduled", "Expected fortnightly pay"),
    (2, "2026-08-02", 480.00, "2026-08-02", 495.00, "received", "Included Sunday loading"),
    (2, "2026-08-09", 480.00, "2026-08-09", 480.00, "received", "Weekend shift"),
    (2, "2026-08-16", 480.00, "2026-08-16", 480.00, "received", "Weekend shift"),
    (2, "2026-08-23", 480.00, "2026-08-24", 480.00, "received", "Paid one day later"),
    (2, "2026-08-30", 480.00, None, None, "scheduled", "Expected weekend pay"),
    (3, "2026-08-10", 750.00, "2026-08-12", 700.00, "received", "Client milestone payment"),
    (4, "2026-08-01", 500.00, "2026-08-01", 500.00, "received", "Monthly allowance"),
    (5, "2026-08-05", 1500.00, "2026-08-05", 1500.00, "received", "Quarterly scholarship"),
    (6, "2026-08-07", 240.00, "2026-08-07", 240.00, "received", "Tutoring sessions"),
    (6, "2026-08-21", 240.00, None, None, "late", "Payment not yet received"),
    (8, "2026-08-18", 180.00, "2026-08-18", 175.00, "received", "Marketplace fee deducted"),
    (9, "2026-08-31", 35.00, None, None, "scheduled", "Monthly account interest"),
]


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(current_app.config["DATABASE_PATH"])
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_user_columns(connection: sqlite3.Connection) -> None:
    """Migrate databases created before shared authentication was added."""
    for table in ("income_sources", "pay_schedules"):
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if "user_id" not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN user_id INTEGER NOT NULL DEFAULT 1"
            )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_income_sources_user ON income_sources(user_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_pay_schedules_user ON pay_schedules(user_id)"
    )


def initialise_database(app: Flask) -> None:
    database_path = Path(app.config["DATABASE_PATH"])
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(SCHEMA)
        ensure_user_columns(connection)
        source_count = connection.execute("SELECT COUNT(*) FROM income_sources").fetchone()[0]
        if source_count == 0:
            connection.executemany(
                """
                INSERT INTO income_sources
                    (user_id, source_name, income_type, standard_amount, payment_frequency, active)
                VALUES (1, ?, ?, ?, ?, ?)
                """,
                SEED_SOURCES,
            )
        schedule_count = connection.execute("SELECT COUNT(*) FROM pay_schedules").fetchone()[0]
        # Schedule seeds reference the IDs created by the fresh source seed above.
        # Do not unexpectedly re-seed a user's deliberately emptied schedule table.
        if schedule_count == 0 and source_count == 0:
            connection.executemany(
                """
                INSERT INTO pay_schedules
                    (user_id, income_source_id, expected_pay_date, expected_amount, received_date,
                     actual_amount, status, notes)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?)
                """,
                SEED_SCHEDULES,
            )
        connection.commit()
    finally:
        connection.close()


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def parse_positive_amount(value: Any, field_name: str) -> float:
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a number") from exc
    if amount <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return amount


def parse_iso_date(value: Any, field_name: str, *, required: bool = True) -> str | None:
    if value in (None, "") and not required:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must use YYYY-MM-DD format")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format") from exc


def parse_boolean(value: Any, field_name: str) -> int:
    if isinstance(value, bool):
        return int(value)
    if value in (0, 1, "0", "1"):
        return int(value)
    raise ValueError(f"{field_name} must be true or false")


def validate_source(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    combined = {**(existing or {}), **payload}
    source_name = str(combined.get("source_name", "")).strip()
    income_type = str(combined.get("income_type", "")).strip()
    frequency = str(combined.get("payment_frequency", "")).strip().lower()
    if not source_name:
        raise ValueError("source_name is required")
    if not income_type:
        raise ValueError("income_type is required")
    if frequency not in FREQUENCIES:
        raise ValueError(f"payment_frequency must be one of: {', '.join(sorted(FREQUENCIES))}")
    return {
        "source_name": source_name,
        "income_type": income_type,
        "standard_amount": parse_positive_amount(combined.get("standard_amount"), "standard_amount"),
        "payment_frequency": frequency,
        "active": parse_boolean(combined.get("active", True), "active"),
    }


def validate_schedule(
    payload: dict[str, Any], existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    combined = {**(existing or {}), **payload}
    try:
        source_id = int(combined.get("income_source_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("income_source_id must be an integer") from exc
    if source_id <= 0:
        raise ValueError("income_source_id must be positive")
    status = str(combined.get("status", "scheduled")).strip().lower()
    if status not in PAYMENT_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(PAYMENT_STATUSES))}")
    received_date = parse_iso_date(combined.get("received_date"), "received_date", required=False)
    actual_raw = combined.get("actual_amount")
    actual_amount = None if actual_raw in (None, "") else parse_positive_amount(actual_raw, "actual_amount")
    if status == "received" and not received_date:
        raise ValueError("received_date is required when status is received")
    if status == "received" and actual_amount is None:
        raise ValueError("actual_amount is required when status is received")
    return {
        "income_source_id": source_id,
        "expected_pay_date": parse_iso_date(combined.get("expected_pay_date"), "expected_pay_date"),
        "expected_amount": parse_positive_amount(combined.get("expected_amount"), "expected_amount"),
        "received_date": received_date,
        "actual_amount": actual_amount,
        "status": status,
        "notes": str(combined.get("notes", "")).strip(),
    }


def required_user_id() -> int:
    try:
        user_id = int(request.args.get("user_id", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("user_id must be a positive integer") from exc
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id


def fetch_source(
    connection: sqlite3.Connection, source_id: int, user_id: int
) -> dict[str, Any] | None:
    return row_to_dict(
        connection.execute(
            "SELECT * FROM income_sources WHERE id = ? AND user_id = ?",
            (source_id, user_id),
        ).fetchone()
    )


def fetch_schedule(
    connection: sqlite3.Connection, schedule_id: int, user_id: int
) -> dict[str, Any] | None:
    return row_to_dict(
        connection.execute(
            "SELECT * FROM pay_schedules WHERE id = ? AND user_id = ?",
            (schedule_id, user_id),
        ).fetchone()
    )


def create_app(database_path: str | None = None) -> Flask:
    app = Flask(__name__)
    default_path = str(Path(__file__).resolve().parent / "data" / "student-3-income.db")
    app.config["DATABASE_PATH"] = database_path or os.getenv("DATABASE_PATH", default_path)
    initialise_database(app)

    @app.get("/health")
    def health():
        with closing(get_connection()) as connection:
            connection.execute("SELECT 1").fetchone()
        return jsonify({"status": "healthy", "service": "student-3-database"})

    @app.get("/api/income-sources")
    def list_income_sources():
        user_id = required_user_id()
        clauses: list[str] = ["user_id = ?"]
        values: list[Any] = [user_id]
        if request.args.get("active") in {"0", "1"}:
            clauses.append("active = ?")
            values.append(int(request.args["active"]))
        if request.args.get("income_type"):
            clauses.append("LOWER(income_type) = LOWER(?)")
            values.append(request.args["income_type"])
        if request.args.get("search"):
            clauses.append("LOWER(source_name) LIKE LOWER(?)")
            values.append(f"%{request.args['search'].strip()}%")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"SELECT * FROM income_sources{where} ORDER BY active DESC, source_name", values
            ).fetchall()
        return jsonify({"items": [dict(row) for row in rows], "count": len(rows)})

    @app.post("/api/income-sources")
    def create_income_source():
        user_id = required_user_id()
        payload = validate_source(request.get_json(silent=True) or {})
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO income_sources
                    (user_id, source_name, income_type, standard_amount, payment_frequency, active)
                VALUES (:user_id, :source_name, :income_type, :standard_amount,
                        :payment_frequency, :active)
                """,
                {**payload, "user_id": user_id},
            )
            connection.commit()
            created = fetch_source(connection, cursor.lastrowid, user_id)
        return jsonify(created), 201

    @app.get("/api/income-sources/<int:source_id>")
    def get_income_source(source_id: int):
        user_id = required_user_id()
        with closing(get_connection()) as connection:
            source = fetch_source(connection, source_id, user_id)
        if source is None:
            return jsonify({"error": "Income source not found"}), 404
        return jsonify(source)

    @app.put("/api/income-sources/<int:source_id>")
    def update_income_source(source_id: int):
        user_id = required_user_id()
        with closing(get_connection()) as connection:
            existing = fetch_source(connection, source_id, user_id)
            if existing is None:
                return jsonify({"error": "Income source not found"}), 404
            payload = validate_source(request.get_json(silent=True) or {}, existing)
            connection.execute(
                """
                UPDATE income_sources
                SET source_name = :source_name,
                    income_type = :income_type,
                    standard_amount = :standard_amount,
                    payment_frequency = :payment_frequency,
                    active = :active,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND user_id = :user_id
                """,
                {**payload, "id": source_id, "user_id": user_id},
            )
            connection.commit()
            updated = fetch_source(connection, source_id, user_id)
        return jsonify(updated)

    @app.delete("/api/income-sources/<int:source_id>")
    def delete_income_source(source_id: int):
        user_id = required_user_id()
        try:
            with closing(get_connection()) as connection:
                cursor = connection.execute(
                    "DELETE FROM income_sources WHERE id = ? AND user_id = ?",
                    (source_id, user_id),
                )
                connection.commit()
        except sqlite3.IntegrityError:
            return jsonify({"error": "Delete this source's pay schedules first, or mark the source inactive"}), 409
        if cursor.rowcount == 0:
            return jsonify({"error": "Income source not found"}), 404
        return "", 204

    @app.get("/api/pay-schedules")
    def list_pay_schedules():
        user_id = required_user_id()
        clauses: list[str] = ["p.user_id = ?"]
        values: list[Any] = [user_id]
        month = request.args.get("month", "").strip()
        if month:
            try:
                date.fromisoformat(f"{month}-01")
            except ValueError:
                return jsonify({"error": "month must use YYYY-MM format"}), 400
            clauses.append("substr(p.expected_pay_date, 1, 7) = ?")
            values.append(month)
        if request.args.get("status"):
            clauses.append("p.status = ?")
            values.append(request.args["status"].strip().lower())
        if request.args.get("income_source_id"):
            clauses.append("p.income_source_id = ?")
            values.append(request.args["income_source_id"])
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        query = f"""
            SELECT p.*, s.source_name, s.income_type, s.payment_frequency
            FROM pay_schedules p
            JOIN income_sources s
              ON s.id = p.income_source_id AND s.user_id = p.user_id
            {where}
            ORDER BY p.expected_pay_date, p.id
        """
        with closing(get_connection()) as connection:
            rows = connection.execute(query, values).fetchall()
        return jsonify({"items": [dict(row) for row in rows], "count": len(rows)})

    @app.post("/api/pay-schedules")
    def create_pay_schedule():
        user_id = required_user_id()
        payload = validate_schedule(request.get_json(silent=True) or {})
        with closing(get_connection()) as connection:
            if fetch_source(connection, payload["income_source_id"], user_id) is None:
                return jsonify({"error": "Income source not found"}), 400
            cursor = connection.execute(
                """
                INSERT INTO pay_schedules
                    (user_id, income_source_id, expected_pay_date, expected_amount, received_date,
                     actual_amount, status, notes)
                VALUES (:user_id, :income_source_id, :expected_pay_date, :expected_amount,
                        :received_date, :actual_amount, :status, :notes)
                """,
                {**payload, "user_id": user_id},
            )
            connection.commit()
            created = fetch_schedule(connection, cursor.lastrowid, user_id)
        return jsonify(created), 201

    @app.get("/api/pay-schedules/<int:schedule_id>")
    def get_pay_schedule(schedule_id: int):
        user_id = required_user_id()
        with closing(get_connection()) as connection:
            schedule = fetch_schedule(connection, schedule_id, user_id)
        if schedule is None:
            return jsonify({"error": "Pay schedule not found"}), 404
        return jsonify(schedule)

    @app.put("/api/pay-schedules/<int:schedule_id>")
    def update_pay_schedule(schedule_id: int):
        user_id = required_user_id()
        with closing(get_connection()) as connection:
            existing = fetch_schedule(connection, schedule_id, user_id)
            if existing is None:
                return jsonify({"error": "Pay schedule not found"}), 404
            payload = validate_schedule(request.get_json(silent=True) or {}, existing)
            if fetch_source(connection, payload["income_source_id"], user_id) is None:
                return jsonify({"error": "Income source not found"}), 400
            connection.execute(
                """
                UPDATE pay_schedules
                SET income_source_id = :income_source_id,
                    expected_pay_date = :expected_pay_date,
                    expected_amount = :expected_amount,
                    received_date = :received_date,
                    actual_amount = :actual_amount,
                    status = :status,
                    notes = :notes,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id AND user_id = :user_id
                """,
                {**payload, "id": schedule_id, "user_id": user_id},
            )
            connection.commit()
            updated = fetch_schedule(connection, schedule_id, user_id)
        return jsonify(updated)

    @app.delete("/api/pay-schedules/<int:schedule_id>")
    def delete_pay_schedule(schedule_id: int):
        user_id = required_user_id()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                "DELETE FROM pay_schedules WHERE id = ? AND user_id = ?",
                (schedule_id, user_id),
            )
            connection.commit()
        if cursor.rowcount == 0:
            return jsonify({"error": "Pay schedule not found"}), 404
        return "", 204

    @app.errorhandler(ValueError)
    def handle_validation_error(error: ValueError):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(404)
    def handle_unknown_route(_error):
        return jsonify({"error": "Route not found"}), 404

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6003, debug=False)
