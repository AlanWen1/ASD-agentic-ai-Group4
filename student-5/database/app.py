import sqlite3
import os
from flask import Flask, jsonify, request

DATABASE = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "savings.db")
)

app = Flask(__name__)


def create_database():
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS savings_goals (
            goal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            goal_name TEXT NOT NULL,
            target_amount REAL NOT NULL,
            current_amount REAL NOT NULL,
            target_date TEXT NOT NULL
        )
    """)

    connection.commit()
    connection.close()


def seed_data():
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM savings_goals")
    count = cursor.fetchone()[0]

    if count == 0:
        sample_goals = [
            (1, "Emergency Fund", 10000, 2500, "2027-06-30"),
            (1, "New Laptop", 2500, 800, "2026-12-01"),
            (1, "Holiday", 5000, 1200, "2027-03-01"),
            (2, "Car Deposit", 8000, 3000, "2027-08-15"),
            (2, "Wedding Fund", 15000, 4500, "2028-01-20"),
            (2, "Phone Upgrade", 1800, 600, "2026-11-30"),
            (3, "Home Deposit", 50000, 12000, "2030-12-31"),
            (3, "Gaming PC", 3500, 1500, "2027-02-28"),
            (3, "Course Fees", 4000, 2200, "2027-01-15"),
            (4, "Travel Fund", 7000, 900, "2027-09-01")
        ]

        cursor.executemany("""
            INSERT INTO savings_goals
            (user_id, goal_name, target_amount, current_amount, target_date)
            VALUES (?, ?, ?, ?, ?)
        """, sample_goals)

        connection.commit()

    connection.close()


@app.route("/goals", methods=["GET"])
def get_goals():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM savings_goals")
    goals = cursor.fetchall()

    connection.close()

    return jsonify([dict(goal) for goal in goals])


@app.route("/goals/<int:goal_id>", methods=["GET"])
def get_goal(goal_id):
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM savings_goals WHERE goal_id = ?",
        (goal_id,)
    )
    goal = cursor.fetchone()

    connection.close()

    if goal is None:
        return jsonify({"error": "Savings goal not found"}), 404

    return jsonify(dict(goal))


@app.route("/goals", methods=["POST"])
def create_goal():
    data = request.get_json()

    required_fields = [
        "user_id",
        "goal_name",
        "target_amount",
        "current_amount",
        "target_date"
    ]

    if not data or not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO savings_goals
        (user_id, goal_name, target_amount, current_amount, target_date)
        VALUES (?, ?, ?, ?, ?)
    """, (
        data["user_id"],
        data["goal_name"],
        data["target_amount"],
        data["current_amount"],
        data["target_date"]
    ))

    connection.commit()
    goal_id = cursor.lastrowid
    connection.close()

    return jsonify({
        "message": "Savings goal created successfully",
        "goal_id": goal_id
    }), 201


@app.route("/goals/<int:goal_id>", methods=["PUT"])
def update_goal(goal_id):
    data = request.get_json()

    required_fields = [
        "user_id",
        "goal_name",
        "target_amount",
        "current_amount",
        "target_date"
    ]

    if not data or not all(field in data for field in required_fields):
        return jsonify({"error": "Missing required fields"}), 400

    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM savings_goals WHERE goal_id = ?",
        (goal_id,)
    )
    goal = cursor.fetchone()

    if goal is None:
        connection.close()
        return jsonify({"error": "Savings goal not found"}), 404

    cursor.execute("""
        UPDATE savings_goals
        SET user_id = ?,
            goal_name = ?,
            target_amount = ?,
            current_amount = ?,
            target_date = ?
        WHERE goal_id = ?
    """, (
        data["user_id"],
        data["goal_name"],
        data["target_amount"],
        data["current_amount"],
        data["target_date"],
        goal_id
    ))

    connection.commit()
    connection.close()

    return jsonify({"message": "Savings goal updated successfully"})


@app.route("/goals/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id):
    connection = sqlite3.connect(DATABASE)
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM savings_goals WHERE goal_id = ?",
        (goal_id,)
    )
    goal = cursor.fetchone()

    if goal is None:
        connection.close()
        return jsonify({"error": "Savings goal not found"}), 404

    cursor.execute(
        "DELETE FROM savings_goals WHERE goal_id = ?",
        (goal_id,)
    )

    connection.commit()
    connection.close()

    return jsonify({"message": "Savings goal deleted successfully"})


if __name__ == "__main__":
    create_database()
    seed_data()
    app.run(host="0.0.0.0", port=6005, debug=True)