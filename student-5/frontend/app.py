from flask import Flask, render_template, request
from markupsafe import escape
import requests
import os

app = Flask(__name__)

BACKEND_API_URL = os.getenv(
    "BACKEND_API_URL",
    "http://127.0.0.1:5005"
).rstrip("/")


def auth_headers():
    headers = {}

    authorization = request.headers.get("Authorization")

    if authorization:
        headers["Authorization"] = authorization

    return headers


@app.route("/")
def index():
    return render_template("index.html")


def render_goals():
    response = requests.get(
        f"{BACKEND_API_URL}/goals",
        headers=auth_headers()
    )

    if response.status_code == 401:
        return "<p>Authentication required.</p>"

    if response.status_code != 200:
        return "<p>Could not load savings goals.</p>"

    goals = response.json()

    html = ""

    for goal in goals:
        html += f"""
        <div class="goal-card">
            <h3>{goal["goal_name"]}</h3>

            <p>Target: ${goal["target_amount"]:.2f}</p>
            <p>Saved: ${goal["current_amount"]:.2f}</p>
            <p>Progress: {goal["progress_percentage"]:.2f}%</p>
            <p>Remaining: ${goal["remaining_amount"]:.2f}</p>
            <p>Required monthly contribution: ${goal["required_monthly_contribution"]:.2f}</p>

            <button
                hx-get="/goals/{goal["goal_id"]}/explanation"
                hx-target="#explanation-{goal["goal_id"]}"
                hx-swap="innerHTML">
                AI Explanation
            </button>

            <div id="explanation-{goal["goal_id"]}"></div>

            <details>
                <summary>Edit</summary>

                <form
                    hx-put="/goals/{goal["goal_id"]}"
                    hx-target="#goals"
                    hx-swap="innerHTML">

                    <label>Goal Name:</label>
                    <input
                        type="text"
                        name="goal_name"
                        value="{goal["goal_name"]}"
                        required>

                    <label>Target Amount:</label>
                    <input
                        type="number"
                        name="target_amount"
                        step="0.01"
                        value="{goal["target_amount"]}"
                        required>

                    <label>Current Amount:</label>
                    <input
                        type="number"
                        name="current_amount"
                        step="0.01"
                        value="{goal["current_amount"]}"
                        required>

                    <label>Target Date:</label>
                    <input
                        type="date"
                        name="target_date"
                        value="{goal["target_date"]}"
                        required>

                    <button type="submit">Save Changes</button>
                </form>
            </details>

            <button
                class="danger"
                hx-delete="/goals/{goal["goal_id"]}"
                hx-target="#goals"
                hx-swap="innerHTML">
                Delete
            </button>
        </div>
        """

    return html


@app.route("/goals", methods=["GET", "POST"])
def goals():
    if request.method == "POST":
        data = {
            "goal_name": request.form["goal_name"],
            "target_amount": float(request.form["target_amount"]),
            "current_amount": float(request.form["current_amount"]),
            "target_date": request.form["target_date"]
        }

        create_response = requests.post(
            f"{BACKEND_API_URL}/goals",
            json=data,
            headers=auth_headers()
        )

        if create_response.status_code == 401:
            return "<p>Authentication required.</p>"

        if create_response.status_code != 201:
            return "<p>Could not create savings goal.</p>"

    return render_goals()


@app.route("/goals/<int:goal_id>", methods=["PUT"])
def update_goal(goal_id):
    data = {
        "goal_name": request.form["goal_name"],
        "target_amount": float(request.form["target_amount"]),
        "current_amount": float(request.form["current_amount"]),
        "target_date": request.form["target_date"]
    }

    update_response = requests.put(
        f"{BACKEND_API_URL}/goals/{goal_id}",
        json=data,
        headers=auth_headers()
    )

    if update_response.status_code == 401:
        return "<p>Authentication required.</p>"

    if update_response.status_code != 200:
        return "<p>Could not update savings goal.</p>"

    return render_goals()


@app.route("/goals/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id):
    delete_response = requests.delete(
        f"{BACKEND_API_URL}/goals/{goal_id}",
        headers=auth_headers()
    )

    if delete_response.status_code == 401:
        return "<p>Authentication required.</p>"

    if delete_response.status_code != 200:
        return "<p>Could not delete savings goal.</p>"

    return render_goals()


@app.route("/goals/<int:goal_id>/explanation", methods=["GET"])
def goal_explanation(goal_id):
    response = requests.get(
        f"{BACKEND_API_URL}/goals/{goal_id}/explanation",
        headers=auth_headers()
    )

    if response.status_code == 401:
        return "<p>Authentication required.</p>"

    if response.status_code == 404:
        return "<p>Savings goal not found.</p>"

    if response.status_code != 200:
        return "<p>Could not generate AI explanation.</p>"

    data = response.json()

    return f"""
    <div>
        <strong>AI Explanation:</strong>
        <p>{data["explanation"]}</p>
    </div>
    """


@app.route("/mcp-query", methods=["POST"])
def mcp_query():
    """Query the Student 5 backend through the shared MCP server."""
    try:
        response = requests.post(
            f"{BACKEND_API_URL}/mcp/query",
            headers=auth_headers(),
            timeout=30
        )
    except requests.RequestException:
        return "<p>Could not connect to the MCP backend.</p>"

    if response.status_code == 401:
        return "<p>Authentication required.</p>"

    if response.status_code == 502:
        return "<p>The shared MCP server is unavailable.</p>"

    if response.status_code != 200:
        return "<p>Could not retrieve savings goals through MCP.</p>"

    try:
        data = response.json()
    except ValueError:
        return "<p>Invalid response from the MCP backend.</p>"

    if data.get("error"):
        return f"<p>Error: {escape(data['error'])}</p>"

    goals = data.get("goals", [])

    if not goals:
        return "<p>No savings goals found.</p>"

    items = "".join(
        f"<li>{escape(goal.get('goal_name', ''))} — "
        f"target ${goal.get('target_amount', 0):.2f}, "
        f"saved ${goal.get('current_amount', 0):.2f}</li>"
        for goal in goals
    )

    return f"<ul>{items}</ul>"


@app.route("/rag-ask", methods=["POST"])
def rag_ask():
    """Ask the Student 5 backend for a grounded RAG answer."""
    message = request.form.get("rag_message", "").strip()

    if not message:
        return "<p>Please enter a question.</p>"

    try:
        response = requests.post(
            f"{BACKEND_API_URL}/rag/ask",
            json={"message": message},
            headers=auth_headers(),
            timeout=60
        )
    except requests.RequestException:
        return "<p>Could not reach the RAG backend.</p>"

    if response.status_code == 401:
        return "<p>Authentication required.</p>"

    if response.status_code != 200:
        return "<p>Could not get a RAG response.</p>"

    try:
        data = response.json()
    except ValueError:
        return "<p>The RAG backend returned an invalid response.</p>"

    if data.get("error"):
        return f"<p>{escape(data['error'])}</p>"

    answer = escape(data.get("answer", "No answer generated."))
    citations = data.get("citations") or []
    confidence = escape(data.get("confidence_category", ""))

    citations_html = ""
    if citations:
        citations_html = (
            f"<p><em>Sources: "
            f"{escape(', '.join(citations))}</em></p>"
        )

    confidence_html = ""
    if confidence:
        confidence_html = f"<p><strong>Confidence:</strong> {confidence}</p>"

    return f"""
    <div>
        {confidence_html}
        <p>{answer}</p>
        {citations_html}
    </div>
    """


@app.route("/chat", methods=["POST"])
def chat():
    message = request.form.get("message", "").strip()

    if not message:
        return "<p>Please enter a message.</p>"

    try:
        response = requests.post(
            f"{BACKEND_API_URL}/agent",
            json={"message": message},
            headers=auth_headers(),
            timeout=120
        )
    except requests.RequestException:
        return "<p>Could not connect to the AI assistant.</p>"

    if response.status_code == 401:
        return "<p>Authentication required.</p>"

    if response.status_code != 200:
        return "<p>Could not get a response from the AI assistant.</p>"

    data = response.json()
    answer = escape(data.get("answer", "No response generated."))

    return f"""
    <div class="chat-message assistant-message">
        <strong>Savings Assistant:</strong>
        <p>{answer}</p>
    </div>
    """

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=3005,
        debug=True
    )