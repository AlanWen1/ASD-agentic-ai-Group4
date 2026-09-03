import os

import requests
from flask import Flask, render_template, request, redirect, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://expense-backend:5002")
# Where to send people to sign in — the shared Finance Application login.
FINANCE_URL = os.environ.get("FINANCE_URL", "http://localhost:3000")

TOKEN_KEY = "finance_token"


@app.before_request
def capture_token_from_url():
    """
    Finance Application links here as .../?token=<session token>.
    Grab it once, store it in our own session, then redirect to the
    clean URL so the token doesn't stay visible/bookmarked.
    """
    incoming = request.args.get("token")
    if not incoming:
        return None
    session[TOKEN_KEY] = incoming
    clean_args = request.args.to_dict()
    clean_args.pop("token", None)
    query = ("?" + "&".join(f"{k}={v}" for k, v in clean_args.items())) if clean_args else ""
    return redirect(request.path + query)


def signed_in():
    return bool(session.get(TOKEN_KEY))


def auth_headers():
    token = session.get(TOKEN_KEY)
    return {"Authorization": f"Bearer {token}"} if token else {}


def api_get(path, **kwargs):
    return requests.get(f"{BACKEND_URL}{path}", headers=auth_headers(), **kwargs)


def api_post(path, **kwargs):
    return requests.post(f"{BACKEND_URL}{path}", headers=auth_headers(), **kwargs)


def api_delete(path, **kwargs):
    return requests.delete(f"{BACKEND_URL}{path}", headers=auth_headers(), **kwargs)


def gate(error=None):
    return render_template("gate.html", finance_url=FINANCE_URL, error=error)


def session_expired():
    """Call when the backend says the token is invalid/expired."""
    session.pop(TOKEN_KEY, None)
    return gate("Your session expired. Please sign in again.")


@app.route("/")
def index():
    if not signed_in():
        return gate()
    try:
        expenses_resp = api_get("/api/expenses")
        categories_resp = api_get("/api/categories")
    except requests.exceptions.RequestException:
        return gate("Could not reach the expense service, please try again.")

    if expenses_resp.status_code == 401 or categories_resp.status_code == 401:
        return session_expired()

    return render_template(
        "index.html",
        expenses=expenses_resp.json(),
        categories=categories_resp.json(),
        finance_url=FINANCE_URL,
    )


@app.route("/expenses", methods=["POST"])
def add_expense():
    if not signed_in():
        return gate()
    data = {
        "amount": float(request.form["amount"]),
        "description": request.form["description"],
        "merchant": request.form.get("merchant", ""),
        "category_id": request.form.get("category_id") or None,
        "date": request.form["date"],
    }
    resp = api_post("/api/expenses", json=data)
    if resp.status_code == 401:
        return session_expired()
    expenses = api_get("/api/expenses").json()
    return render_template("partials/expense_list.html", expenses=expenses)


@app.route("/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    if not signed_in():
        return gate()
    resp = api_delete(f"/api/expenses/{expense_id}")
    if resp.status_code == 401:
        return session_expired()
    expenses = api_get("/api/expenses").json()
    return render_template("partials/expense_list.html", expenses=expenses)


@app.route("/expenses/suggest-category", methods=["POST"])
def suggest_category():
    if not signed_in():
        return gate()
    description = request.form.get("description", "")
    merchant = request.form.get("merchant", "")
    try:
        result = api_post(
            "/api/expenses/suggest-category",
            json={"description": description, "merchant": merchant},
            timeout=30,
        ).json()
        category = result.get("category", "Other")
    except requests.exceptions.RequestException:
        category = "Other"
    return f"AI suggests: <strong>{category}</strong>"


@app.route("/categories")
def categories_page():
    if not signed_in():
        return gate()
    resp = api_get("/api/categories")
    if resp.status_code == 401:
        return session_expired()
    return render_template("categories.html", categories=resp.json(), finance_url=FINANCE_URL)


@app.route("/categories", methods=["POST"])
def add_category():
    if not signed_in():
        return gate()
    data = {"name": request.form["name"], "type": request.form.get("type", "Discretionary")}
    resp = api_post("/api/categories", json=data)
    if resp.status_code == 401:
        return session_expired()
    categories = api_get("/api/categories").json()
    return render_template("partials/category_list.html", categories=categories)


@app.route("/categories/<int:cat_id>", methods=["DELETE"])
def delete_category(cat_id):
    if not signed_in():
        return gate()
    resp = api_delete(f"/api/categories/{cat_id}")
    if resp.status_code == 401:
        return session_expired()
    categories = api_get("/api/categories").json()
    return render_template("partials/category_list.html", categories=categories)


@app.route("/logout")
def logout():
    session.pop(TOKEN_KEY, None)
    return redirect(FINANCE_URL)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3002, debug=True)
