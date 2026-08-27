from flask import Flask, send_from_directory, request
import requests

app = Flask(__name__)

BACKEND_API_URL = "http://127.0.0.1:5005"


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


def render_goals():
    response = requests.get(f"{BACKEND_API_URL}/goals")

    if response.status_code != 200:
        return "<p>Could not load savings goals.</p>"

    goals = response.json()

    html = ""

    for goal in goals:
        html += f"""
        <div>
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

                    <label>User ID:</label>
                    <input
                        type="number"
                        name="user_id"
                        value="{goal["user_id"]}"
                        required>

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
            "user_id": int(request.form["user_id"]),
            "goal_name": request.form["goal_name"],
            "target_amount": float(request.form["target_amount"]),
            "current_amount": float(request.form["current_amount"]),
            "target_date": request.form["target_date"]
        }

        create_response = requests.post(
            f"{BACKEND_API_URL}/goals",
            json=data
        )

        if create_response.status_code != 201:
            return "<p>Could not create savings goal.</p>"

    return render_goals()


@app.route("/goals/<int:goal_id>", methods=["PUT"])
def update_goal(goal_id):
    data = {
        "user_id": int(request.form["user_id"]),
        "goal_name": request.form["goal_name"],
        "target_amount": float(request.form["target_amount"]),
        "current_amount": float(request.form["current_amount"]),
        "target_date": request.form["target_date"]
    }

    update_response = requests.put(
        f"{BACKEND_API_URL}/goals/{goal_id}",
        json=data
    )

    if update_response.status_code != 200:
        return "<p>Could not update savings goal.</p>"

    return render_goals()


@app.route("/goals/<int:goal_id>", methods=["DELETE"])
def delete_goal(goal_id):
    delete_response = requests.delete(
        f"{BACKEND_API_URL}/goals/{goal_id}"
    )

    if delete_response.status_code != 200:
        return "<p>Could not delete savings goal.</p>"

    return render_goals()


@app.route("/goals/<int:goal_id>/explanation", methods=["GET"])
def goal_explanation(goal_id):
    response = requests.get(
        f"{BACKEND_API_URL}/goals/{goal_id}/explanation"
    )

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3005, debug=True)