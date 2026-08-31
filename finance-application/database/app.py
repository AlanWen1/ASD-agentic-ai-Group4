import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
DATABASE_PATH = os.environ.get("DATABASE_PATH", "/data/finance.db")
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "7"))


def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    with closing(get_db()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
            """
        )
        conn.commit()


def now_utc():
    return datetime.utcnow()


def iso(dt):
    return dt.isoformat(timespec="seconds") + "Z"


def clean_user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "email": row["email"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@app.get("/health")
def health():
    try:
        with closing(get_db()) as conn:
            conn.execute("SELECT 1").fetchone()
        return jsonify({"status": "ok", "service": "finance-database"})
    except sqlite3.Error as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500


@app.post("/users")
def create_user():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))

    if len(username) < 3:
        return jsonify({"error": "username must be at least 3 characters"}), 400
    if "@" not in email or len(email) < 5:
        return jsonify({"error": "a valid email is required"}), 400
    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400

    now = iso(now_utc())
    try:
        with closing(get_db()) as conn:
            cursor = conn.execute(
                """
                INSERT INTO users (username, email, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (username, email, generate_password_hash(password), now, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return jsonify(clean_user(row)), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "username or email is already registered"}), 409


@app.post("/auth/login")
def login():
    payload = request.get_json(silent=True) or {}
    identifier = str(payload.get("identifier", "")).strip().lower()
    password = str(payload.get("password", ""))

    with closing(get_db()) as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE lower(username) = ? OR lower(email) = ?",
            (identifier, identifier),
        ).fetchone()
        if not row or not check_password_hash(row["password_hash"], password):
            return jsonify({"error": "Invalid username/email or password"}), 401

        token = secrets.token_urlsafe(48)
        created = now_utc()
        expires = created + timedelta(days=SESSION_DAYS)
        conn.execute(
            "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (token, row["id"], iso(created), iso(expires)),
        )
        conn.commit()

    return jsonify({"token": token, "expires_at": iso(expires), "user": clean_user(row)})


@app.post("/auth/logout")
def logout():
    payload = request.get_json(silent=True) or {}
    token = str(payload.get("token", ""))
    if token:
        with closing(get_db()) as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
    return jsonify({"message": "Logged out"})


@app.get("/sessions/<token>")
def validate_session(token):
    with closing(get_db()) as conn:
        row = conn.execute(
            """
            SELECT u.*, s.expires_at
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not row:
            return jsonify({"error": "Invalid session"}), 401

        try:
            expires = datetime.fromisoformat(row["expires_at"].rstrip("Z"))
        except ValueError:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return jsonify({"error": "Invalid session"}), 401

        if expires <= now_utc():
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            return jsonify({"error": "Session expired"}), 401

    return jsonify({"user": clean_user(row), "expires_at": row["expires_at"]})


@app.get("/users/<int:user_id>")
def get_user(user_id):
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        return jsonify({"error": "User not found"}), 404
    return jsonify(clean_user(row))


@app.put("/users/<int:user_id>")
def update_user(user_id):
    payload = request.get_json(silent=True) or {}
    allowed = {"username", "email", "password"}
    changes = {key: payload[key] for key in allowed if key in payload}
    if not changes:
        return jsonify({"error": "At least one field is required"}), 400

    if "username" in changes:
        changes["username"] = str(changes["username"]).strip()
        if len(changes["username"]) < 3:
            return jsonify({"error": "username must be at least 3 characters"}), 400
    if "email" in changes:
        changes["email"] = str(changes["email"]).strip().lower()
        if "@" not in changes["email"]:
            return jsonify({"error": "a valid email is required"}), 400
    if "password" in changes:
        if len(str(changes["password"])) < 8:
            return jsonify({"error": "password must be at least 8 characters"}), 400
        changes["password_hash"] = generate_password_hash(str(changes.pop("password")))

    changes["updated_at"] = iso(now_utc())
    set_clause = ", ".join(f"{key} = ?" for key in changes)
    values = list(changes.values()) + [user_id]

    try:
        with closing(get_db()) as conn:
            cursor = conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({"error": "User not found"}), 404
            conn.commit()
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return jsonify(clean_user(row))
    except sqlite3.IntegrityError:
        return jsonify({"error": "username or email is already registered"}), 409


@app.delete("/users/<int:user_id>")
def delete_user(user_id):
    with closing(get_db()) as conn:
        cursor = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        if cursor.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "User not found"}), 404
        conn.commit()
    return jsonify({"message": "User deleted", "id": user_id})


@app.errorhandler(Exception)
def unhandled_error(exc):
    app.logger.exception("Unhandled finance database error")
    return jsonify({"error": "Internal server error"}), 500


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=6000)
