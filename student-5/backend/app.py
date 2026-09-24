from flask import Flask, jsonify, request
import requests
from datetime import date
import os

from agent import run_agent_loop
from mcp_client import call_mcp_tool

app = Flask(__name__)

DATABASE_API_URL = os.getenv(
    "DATABASE_API_URL",
    "http://127.0.0.1:6005"
).rstrip("/")

AUTH_DATABASE_URL = os.getenv(
    "AUTH_DATABASE_URL",
    "http://finance-database:6000"
).rstrip("/")

OLLAMA_API_URL = os.getenv(
    "OLLAMA_API_URL",
    "http://127.0.0.1:11434/api/generate"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:0.5b"
)


def current_user():
    header = request.headers.get("Authorization", "")

    token = (
        header[7:].strip()
        if header.lower().startswith("bearer ")
        else ""
    )

    if not token:
        return None, (
            jsonify({"error": "Authentication required"}),
            401
        )

    try:
        response = requests.get(
            f"{AUTH_DATABASE_URL}/sessions/{token}",
            timeout=10
        )
    except requests.RequestException:
        return None, (
            jsonify({
                "error": "Authentication service unavailable"
            }),
            503
        )

    if response.status_code != 200:
        return None, (
            jsonify({
                "error": "Invalid or expired session"
            }),
            401
        )

    try:
        user = response.json()["user"]
    except (KeyError, TypeError, ValueError):
        return None, (
            jsonify({
                "error": "Authentication service returned invalid data"
            }),
            503
        )

    return user, None


def calculate_goal_fields(goal):
    target_amount = goal["target_amount"]
    current_amount = goal["current_amount"]

    if target_amount > 0:
        progress_percentage = (
            current_amount / target_amount
        ) * 100
    else:
        progress_percentage = 0

    remaining_amount = max(
        target_amount - current_amount,
        0
    )

    target_date = date.fromisoformat(
        goal["target_date"]
    )

    today = date.today()

    months_remaining = (
        (target_date.year - today.year) * 12
        + (target_date.month - today.month)
    )

    if months_remaining > 0:
        required_monthly_contribution = (
            remaining_amount / months_remaining
        )
    else:
        required_monthly_contribution = remaining_amount

    goal["progress_percentage"] = round(
        progress_percentage,
        2
    )

    goal["remaining_amount"] = round(
        remaining_amount,
        2
    )

    goal["required_monthly_contribution"] = round(
        required_monthly_contribution,
        2
    )

    return goal


def get_owned_goal(goal_id, user_id):
    response = requests.get(
        f"{DATABASE_API_URL}/goals/{goal_id}"
    )

    if response.status_code == 404:
        return None, (
            jsonify({
                "error": "Savings goal not found"
            }),
            404
        )

    if response.status_code != 200:
        return None, (
            jsonify({
                "error": "Could not retrieve savings goal"
            }),
            500
        )

    goal = response.json()

    if goal.get("user_id") != user_id:
        return None, (
            jsonify({
                "error": "Savings goal not found"
            }),
            404
        )

    return goal, None


@app.route("/goals", methods=["GET"])
def get_goals():
    user, error = current_user()

    if error:
        return error

    response = requests.get(
        f"{DATABASE_API_URL}/goals"
    )

    if response.status_code != 200:
        return jsonify({
            "error": "Could not retrieve savings goals"
        }), 500

    goals = response.json()

    user_goals = [
        goal
        for goal in goals
        if goal.get("user_id") == user["id"]
    ]

    for goal in user_goals:
        calculate_goal_fields(goal)

    return jsonify(user_goals)


@app.route("/goals/<int:goal_id>", methods=["GET"])
def get_goal(goal_id):
    user, error = current_user()

    if error:
        return error

    goal, error = get_owned_goal(
        goal_id,
        user["id"]
    )

    if error:
        return error

    calculate_goal_fields(goal)

    return jsonify(goal)


@app.route("/goals", methods=["POST"])
def create_goal():
    user, error = current_user()

    if error:
        return error

    data = request.get_json(silent=True) or {}

    data["user_id"] = user["id"]

    response = requests.post(
        f"{DATABASE_API_URL}/goals",
        json=data
    )

    return jsonify(
        response.json()
    ), response.status_code


@app.route("/goals/<int:goal_id>", methods=["PUT"])
def update_goal(goal_id):
    user, error = current_user()

    if error:
        return error

    goal, error = get_owned_goal(
        goal_id,
        user["id"]
    )

    if error:
        return error

    data = request.get_json(silent=True) or {}

    data["user_id"] = user["id"]

    response = requests.put(
        f"{DATABASE_API_URL}/goals/{goal_id}",
        json=data
    )

    return jsonify(
        response.json()
    ), response.status_code


@app.route("/goals/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id):
    user, error = current_user()

    if error:
        return error

    goal, error = get_owned_goal(
        goal_id,
        user["id"]
    )

    if error:
        return error

    response = requests.delete(
        f"{DATABASE_API_URL}/goals/{goal_id}"
    )

    return jsonify(
        response.json()
    ), response.status_code


@app.route(
    "/goals/<int:goal_id>/explanation",
    methods=["GET"]
)
def get_goal_explanation(goal_id):
    user, error = current_user()

    if error:
        return error

    goal, error = get_owned_goal(
        goal_id,
        user["id"]
    )

    if error:
        return error

    target_amount = goal["target_amount"]
    current_amount = goal["current_amount"]

    if target_amount > 0:
        progress_percentage = (
            current_amount / target_amount
        ) * 100
    else:
        progress_percentage = 0

    remaining_amount = max(
        target_amount - current_amount,
        0
    )

    target_date = date.fromisoformat(
        goal["target_date"]
    )

    today = date.today()

    months_remaining = (
        (target_date.year - today.year) * 12
        + (target_date.month - today.month)
    )

    if months_remaining > 0:
        required_monthly_contribution = (
            remaining_amount / months_remaining
        )
    else:
        required_monthly_contribution = remaining_amount

    prompt = f"""
You are a helpful budgeting assistant.

All the numbers below have ALREADY been calculated correctly. Do not
recalculate anything, do not invent new numbers, and do not invent any
dates other than the target date given below.

Goal name: {goal["goal_name"]}
Target amount: ${target_amount:.2f}
Current amount: ${current_amount:.2f}
Progress: {progress_percentage:.2f}%
Remaining amount: ${remaining_amount:.2f}
Target date: {goal["target_date"]}
Required monthly contribution: ${required_monthly_contribution:.2f}

Task: restate the numbers above in 2-3 short, plain-language sentences,
as if explaining them to the user. Do not show any arithmetic or
step-by-step working. Do not provide investment or financial product
advice.
"""

    ollama_response = requests.post(
        OLLAMA_API_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1
            }
        }
    )

    if ollama_response.status_code != 200:
        return jsonify({
            "error": "Could not generate AI explanation"
        }), 500

    explanation = ollama_response.json()["response"]

    return jsonify({
        "goal_id": goal_id,
        "goal_name": goal["goal_name"],
        "explanation": explanation
    })


@app.route("/agent", methods=["POST"])
def savings_agent():
    data = request.get_json()

    if not data or "message" not in data:
        return jsonify({
            "error": "Message is required"
        }), 400

    try:
        result = run_agent_loop(
            data["message"]
        )

        return jsonify(result)

    except requests.RequestException:
        return jsonify({
            "error": "Could not communicate with the AI service"
        }), 500

    except Exception as error:
        return jsonify({
            "error": str(error)
        }), 500


# ---------------------------------------------------------------------
# Release 1: shared MCP + RAG server access. Note: the Savings Goal
# Manager's own /goals endpoint does not currently filter by user (a
# known pre-existing gap - see get_savings_goals in tools.py's docstring
# on the shared MCP server), so user_id here is optional, matching that.
# ---------------------------------------------------------------------
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://host.docker.internal:5101").rstrip("/")


@app.route("/api/mcp/query", methods=["POST"])
def mcp_query():
    """Call the shared MCP server's get_savings_goals tool."""
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    kwargs = {"user_id": user_id} if user_id is not None else {}
    result = call_mcp_tool("get_savings_goals", **kwargs)
    status_code = 502 if isinstance(result, dict) and "error" in result else 200
    return jsonify({"tool": "get_savings_goals", "result": result}), status_code


@app.route("/api/rag/ask", methods=["POST"])
def rag_ask():
    """Forward a free-text question to the shared RAG server for a
    grounded answer with citations and a confidence category."""
    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()
    if not question:
        return jsonify({"error": "message is required"}), 400

    try:
        response = requests.post(
            f"{RAG_SERVER_URL}/answer_question",
            json={"query": question},
            timeout=20,
        )
        return jsonify(response.json()), response.status_code
    except requests.exceptions.RequestException as exc:
        return jsonify({"error": f"RAG server unavailable: {exc}"}), 502


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5005,
        debug=True
    )