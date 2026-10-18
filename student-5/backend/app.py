from flask import Flask, jsonify, request
import requests
from datetime import date
import os

from agent import run_agent_loop

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

AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
MCP_ENABLED = os.getenv("MCP_ENABLED", "true").lower() == "true"
RAG_ENABLED = os.getenv("RAG_ENABLED", "true").lower() == "true"


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
        f"{DATABASE_API_URL}/goals/{goal_id}",
        timeout=10
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
        f"{DATABASE_API_URL}/goals",
        timeout=10
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
        json=data,
        timeout=10
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
        json=data,
        timeout=10
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
        f"{DATABASE_API_URL}/goals/{goal_id}",
        timeout=10
    )

    return jsonify(
        response.json()
    ), response.status_code


@app.route(
    "/goals/<int:goal_id>/explanation",
    methods=["GET"]
)
def get_goal_explanation(goal_id):
    if not AI_ENABLED:
        return jsonify({
            "error": "AI Mode is disabled"
        }), 503

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
        },
        timeout=120
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
    user, error = current_user()

    if error:
        return error

    data = request.get_json()

    if not data or "message" not in data:
        return jsonify({
            "error": "Message is required"
        }), 400

    try:
        result = run_agent_loop(
            data["message"],
            user_id=user["id"]
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
# Release 1: shared MCP + RAG server access.
# ---------------------------------------------------------------------
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://host.docker.internal:5101").rstrip("/")


@app.route("/mcp/query", methods=["POST"])
def mcp_query():
    """Query the shared MCP server for the authenticated user's savings goals."""

    if not MCP_ENABLED:
        return jsonify({
            "error": "MCP is disabled"
        }), 503

    user, error = current_user()

    if error:
        return error

    from mcp_client import call_mcp_tool

    result = call_mcp_tool(
        "get_savings_goals",
        user_id=user["id"]
    )

    if isinstance(result, dict) and result.get("error"):
        return jsonify({
            "error": result["error"]
        }), 502

    if not isinstance(result, list):
        return jsonify({
            "error": "Unexpected response from MCP server"
        }), 502

    user_goals = [
        goal
        for goal in result
        if goal.get("user_id") == user["id"]
    ]

    return jsonify({
        "tool": "get_savings_goals",
        "goals": user_goals
    }), 200


@app.route("/rag/ask", methods=["POST"])
def rag_ask():
    """Ask the shared RAG server for a grounded answer."""

    if not RAG_ENABLED:
        return jsonify({
            "error": "RAG is disabled"
        }), 503

    user, error = current_user()

    if error:
        return error

    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()

    if not question:
        return jsonify({
            "error": "message is required"
        }), 400

    try:
        response = requests.post(
            f"{RAG_SERVER_URL}/answer_question",
            json={"query": question},
            timeout=20
        )
    except requests.RequestException as exc:
        return jsonify({
            "error": f"RAG server unavailable: {exc}"
        }), 502

    try:
        result = response.json()
    except ValueError:
        return jsonify({
            "error": "RAG server returned an invalid response"
        }), 502

    return jsonify(result), response.status_code



# Release 2: shared Planner / Worker / Reviewer workflow.
MULTI_AGENT_CONFIG = {
    "url": os.getenv(
        "MULTI_AGENT_URL",
        "http://host.docker.internal:5102"
    ).rstrip("/"),
    "api_key": os.getenv(
        "MULTI_AGENT_API_KEY",
        "local-dev-key-change-me"
    ),
    "enabled": os.getenv(
        "MULTI_AGENT_ENABLED", "true"
    ).strip().lower() in {"true", "1", "yes", "on"}
}


class MultiAgentGateway:
    """Handle communication with the shared Multi-Agent Server."""

    def __init__(self, config):
        self.base_url = config["url"]
        self.api_key = config["api_key"]
        self.enabled = config["enabled"]

    def request(self, method, endpoint, **options):
        if not self.enabled:
            return jsonify({
                "error": "Multi-Agent is disabled in this environment"
            }), 503

        try:
            response = requests.request(
                method,
                self.base_url + endpoint,
                headers={
                    "X-Multi-Agent-Key": self.api_key
                },
                timeout=2100,
                **options
            )
        except requests.RequestException as exc:
            return jsonify({
                "error": f"Multi-Agent Server unavailable: {exc}"
            }), 502

        try:
            result = response.json()
        except ValueError:
            result = {
                "error": "Multi-Agent Server returned invalid JSON"
            }

        return jsonify(result), response.status_code


multi_agent_gateway = MultiAgentGateway(MULTI_AGENT_CONFIG)


def prepare_savings_evidence(user_id):
    """Prepare savings-goal evidence for the shared workflow."""

    try:
        response = requests.get(
            f"{DATABASE_API_URL}/goals",
            timeout=10
        )
        response.raise_for_status()

        owned_goals = []

        for goal in response.json():
            if str(goal.get("user_id")) == str(user_id):
                owned_goals.append(
                    calculate_goal_fields(goal)
                )

        return {
            "source": "savings-database",
            "goals": owned_goals
        }
    except (requests.RequestException, ValueError) as exc:
        return {
            "source": "savings-database",
            "retrieval_error": str(exc),
            "goals": []
        }


@app.route("/multi-agent/run", methods=["POST"])
def create_multi_agent_workflow():
    """Start a savings-goal Multi-Agent workflow."""

    user, error = current_user()

    if error:
        return error

    data = request.get_json(silent=True) or {}

    task = str(
        data.get("task") or data.get("message") or ""
    ).strip()

    if not task:
        return jsonify({
            "error": "task is required"
        }), 400

    return multi_agent_gateway.request(
        "POST",
        "/runs",
        json={
            "module": "savings",
            "user_id": str(user["id"]),
            "task": task,
            "evidence": prepare_savings_evidence(user["id"])
        }
    )


@app.route("/multi-agent/runs", methods=["GET"])
def retrieve_multi_agent_workflows():
    """Retrieve the authenticated user's workflow history."""

    user, error = current_user()

    if error:
        return error

    return multi_agent_gateway.request(
        "GET",
        "/runs",
        params={
            "module": "savings",
            "user_id": str(user["id"])
        }
    )


@app.route(
    "/multi-agent/runs/<run_id>/decision",
    methods=["POST"]
)
def submit_multi_agent_decision(run_id):
    """Forward a human-review decision to the shared server."""

    user, error = current_user()

    if error:
        return error

    data = request.get_json(silent=True) or {}

    return multi_agent_gateway.request(
        "POST",
        f"/runs/{run_id}/decision",
        json={
            "module": "savings",
            "user_id": str(user["id"]),
            "decision": str(
                data.get("decision", "")
            ).strip().lower(),
            "feedback": str(
                data.get("feedback", "")
            ).strip()
        }
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5005,
        debug=False
    )
