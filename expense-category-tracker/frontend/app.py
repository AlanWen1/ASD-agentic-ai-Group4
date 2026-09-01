from flask import Flask, render_template, request
import requests
import os

app = Flask(__name__)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://expense-backend:5002")


@app.route("/")
def index():
    expenses = requests.get(f"{BACKEND_URL}/api/expenses").json()
    categories = requests.get(f"{BACKEND_URL}/api/categories").json()
    return render_template("index.html", expenses=expenses, categories=categories)


@app.route("/expenses", methods=["POST"])
def add_expense():
    data = {
        "amount": float(request.form["amount"]),
        "description": request.form["description"],
        "merchant": request.form.get("merchant", ""),
        "category_id": request.form.get("category_id") or None,
        "date": request.form["date"],
    }
    requests.post(f"{BACKEND_URL}/api/expenses", json=data)
    expenses = requests.get(f"{BACKEND_URL}/api/expenses").json()
    return render_template("partials/expense_list.html", expenses=expenses)


@app.route("/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    requests.delete(f"{BACKEND_URL}/api/expenses/{expense_id}")
    expenses = requests.get(f"{BACKEND_URL}/api/expenses").json()
    return render_template("partials/expense_list.html", expenses=expenses)


@app.route("/expenses/suggest-category", methods=["POST"])
def suggest_category():
    description = request.form.get("description", "")
    merchant = request.form.get("merchant", "")
    try:
        result = requests.post(
            f"{BACKEND_URL}/api/expenses/suggest-category",
            json={"description": description, "merchant": merchant},
            timeout=30,
        ).json()
        category = result.get("category", "Other")
    except requests.exceptions.RequestException:
        category = "Other"
    return f"AI suggests: <strong>{category}</strong>"


@app.route("/categories")
def categories_page():
    categories = requests.get(f"{BACKEND_URL}/api/categories").json()
    return render_template("categories.html", categories=categories)


@app.route("/categories", methods=["POST"])
def add_category():
    data = {"name": request.form["name"], "type": request.form.get("type", "Discretionary")}
    requests.post(f"{BACKEND_URL}/api/categories", json=data)
    categories = requests.get(f"{BACKEND_URL}/api/categories").json()
    return render_template("partials/category_list.html", categories=categories)


@app.route("/categories/<int:cat_id>", methods=["DELETE"])
def delete_category(cat_id):
    requests.delete(f"{BACKEND_URL}/api/categories/{cat_id}")
    categories = requests.get(f"{BACKEND_URL}/api/categories").json()
    return render_template("partials/category_list.html", categories=categories)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3002, debug=True)
