from flask import Flask, jsonify, request
import requests
from datetime import date

app = Flask(__name__)

DATABASE_API_URL = "http://127.0.0.1:6005"

OLLAMA_API_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:0.5b"


@app.route("/goals", methods=["GET"])
def get_goals():
    response = requests.get(f"{DATABASE_API_URL}/goals")

    if response.status_code != 200:
        return jsonify({"error": "Could not retrieve savings goals"}), 500

    goals = response.json()

    for goal in goals:
        target_amount = goal["target_amount"]
        current_amount = goal["current_amount"]

        if target_amount > 0:
            progress_percentage = (current_amount / target_amount) * 100
        else:
            progress_percentage = 0

        remaining_amount = max(target_amount - current_amount, 0)

        target_date = date.fromisoformat(goal["target_date"])
        today = date.today()

        months_remaining = (
            (target_date.year - today.year) * 12
            + (target_date.month - today.month)
        )

        if months_remaining > 0:
            required_monthly_contribution = remaining_amount / months_remaining
        else:
            required_monthly_contribution = remaining_amount

        goal["progress_percentage"] = round(progress_percentage, 2)
        goal["remaining_amount"] = round(remaining_amount, 2)
        goal["required_monthly_contribution"] = round(
            required_monthly_contribution, 2
        )

    return jsonify(goals)


@app.route("/goals/<int:goal_id>", methods=["GET"])
def get_goal(goal_id):
    response = requests.get(f"{DATABASE_API_URL}/goals/{goal_id}")

    if response.status_code == 404:
        return jsonify({"error": "Savings goal not found"}), 404

    if response.status_code != 200:
        return jsonify({"error": "Could not retrieve savings goal"}), 500

    goal = response.json()

    target_amount = goal["target_amount"]
    current_amount = goal["current_amount"]

    if target_amount > 0:
        progress_percentage = (current_amount / target_amount) * 100
    else:
        progress_percentage = 0

    remaining_amount = max(target_amount - current_amount, 0)

    target_date = date.fromisoformat(goal["target_date"])
    today = date.today()

    months_remaining = (
        (target_date.year - today.year) * 12
        + (target_date.month - today.month)
    )

    if months_remaining > 0:
        required_monthly_contribution = remaining_amount / months_remaining
    else:
        required_monthly_contribution = remaining_amount

    goal["progress_percentage"] = round(progress_percentage, 2)
    goal["remaining_amount"] = round(remaining_amount, 2)
    goal["required_monthly_contribution"] = round(
        required_monthly_contribution, 2
    )

    return jsonify(goal)


@app.route("/goals", methods=["POST"])
def create_goal():
    data = request.get_json()

    response = requests.post(
        f"{DATABASE_API_URL}/goals",
        json=data
    )

    return jsonify(response.json()), response.status_code


@app.route("/goals/<int:goal_id>", methods=["PUT"])
def update_goal(goal_id):
    data = request.get_json()

    response = requests.put(
        f"{DATABASE_API_URL}/goals/{goal_id}",
        json=data
    )

    return jsonify(response.json()), response.status_code


@app.route("/goals/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id):
    response = requests.delete(
        f"{DATABASE_API_URL}/goals/{goal_id}"
    )

    return jsonify(response.json()), response.status_code


@app.route("/goals/<int:goal_id>/explanation", methods=["GET"])
def get_goal_explanation(goal_id):
    response = requests.get(f"{DATABASE_API_URL}/goals/{goal_id}")

    if response.status_code == 404:
        return jsonify({"error": "Savings goal not found"}), 404

    if response.status_code != 200:
        return jsonify({"error": "Could not retrieve savings goal"}), 500

    goal = response.json()

    target_amount = goal["target_amount"]
    current_amount = goal["current_amount"]

    if target_amount > 0:
        progress_percentage = (current_amount / target_amount) * 100
    else:
        progress_percentage = 0

    remaining_amount = max(target_amount - current_amount, 0)

    target_date = date.fromisoformat(goal["target_date"])
    today = date.today()

    months_remaining = (
        (target_date.year - today.year) * 12
        + (target_date.month - today.month)
    )

    if months_remaining > 0:
        required_monthly_contribution = remaining_amount / months_remaining
    else:
        required_monthly_contribution = remaining_amount

    prompt = f"""
You are a helpful budgeting assistant.

Explain this savings goal in simple language.

Goal name: {goal["goal_name"]}
Target amount: ${target_amount:.2f}
Current amount: ${current_amount:.2f}
Progress: {progress_percentage:.2f}%
Remaining amount: ${remaining_amount:.2f}
Target date: {goal["target_date"]}
Required monthly contribution: ${required_monthly_contribution:.2f}

Keep the explanation short and easy to understand.
Do not provide investment or financial product advice.
"""

    ollama_response = requests.post(
        OLLAMA_API_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False
        }
    )

    if ollama_response.status_code != 200:
        return jsonify({"error": "Could not generate AI explanation"}), 500

    explanation = ollama_response.json()["response"]

    return jsonify({
        "goal_id": goal_id,
        "goal_name": goal["goal_name"],
        "explanation": explanation
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, debug=True)