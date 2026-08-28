from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from decimal import Decimal
from datetime import date
import requests

from config import DATABASE_URL, OLLAMA_URL, OLLAMA_MODEL


app = Flask(__name__)
CORS(app)


def get_db():
    return psycopg2.connect(DATABASE_URL)


def serialize_bill(bill):
    if not bill:
        return None

    result = dict(bill)

    if isinstance(result.get("amount"), Decimal):
        result["amount"] = float(result["amount"])

    if isinstance(result.get("due_date"), date):
        result["due_date"] = result["due_date"].isoformat()

    if result.get("created_at"):
        result["created_at"] = result["created_at"].isoformat()

    if result.get("updated_at"):
        result["updated_at"] = result["updated_at"].isoformat()

    return result


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health():
    try:
        conn = get_db()
        conn.close()

        return jsonify({
            "status": "ok",
            "database": "connected",
            "ollama": OLLAMA_URL,
            "model": OLLAMA_MODEL
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


# ---------------------------------------------------------
# GET all bills
# ---------------------------------------------------------

@app.route("/api/bills", methods=["GET"])
def get_bills():

    conn = get_db()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            cur.execute("""
                SELECT *
                FROM bills
                ORDER BY due_date ASC
            """)

            bills = cur.fetchall()

        return jsonify([serialize_bill(bill) for bill in bills])

    finally:
        conn.close()


# ---------------------------------------------------------
# GET single bill
# ---------------------------------------------------------

@app.route("/api/bills/<int:bill_id>", methods=["GET"])
def get_bill(bill_id):

    conn = get_db()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            cur.execute(
                "SELECT * FROM bills WHERE id = %s",
                (bill_id,)
            )

            bill = cur.fetchone()

        if not bill:
            return jsonify({
                "error": "Bill not found"
            }), 404

        return jsonify(serialize_bill(bill))

    finally:
        conn.close()


# ---------------------------------------------------------
# CREATE bill
# ---------------------------------------------------------

@app.route("/api/bills", methods=["POST"])
def create_bill():

    data = request.get_json()

    required = [
        "name",
        "amount",
        "due_date",
        "frequency",
        "status"
    ]

    missing = [
        field for field in required
        if field not in data
    ]

    if missing:
        return jsonify({
            "error": "Missing fields",
            "fields": missing
        }), 400

    conn = get_db()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            cur.execute("""
                INSERT INTO bills
                    (name, amount, due_date, frequency, status)
                VALUES
                    (%s, %s, %s, %s, %s)
                RETURNING *
            """, (
                data["name"],
                data["amount"],
                data["due_date"],
                data["frequency"],
                data["status"]
            ))

            bill = cur.fetchone()

        conn.commit()

        return jsonify(serialize_bill(bill)), 201

    except Exception as e:
        conn.rollback()

        return jsonify({
            "error": str(e)
        }), 400

    finally:
        conn.close()


# ---------------------------------------------------------
# UPDATE bill
# ---------------------------------------------------------

@app.route("/api/bills/<int:bill_id>", methods=["PUT"])
def update_bill(bill_id):

    data = request.get_json()

    fields = [
        "name",
        "amount",
        "due_date",
        "frequency",
        "status"
    ]

    updates = []
    values = []

    for field in fields:

        if field in data:
            updates.append(f"{field} = %s")
            values.append(data[field])

    if not updates:
        return jsonify({
            "error": "No fields to update"
        }), 400

    updates.append("updated_at = CURRENT_TIMESTAMP")

    values.append(bill_id)

    conn = get_db()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            cur.execute(
                f"""
                UPDATE bills
                SET {", ".join(updates)}
                WHERE id = %s
                RETURNING *
                """,
                values
            )

            bill = cur.fetchone()

        if not bill:
            conn.rollback()

            return jsonify({
                "error": "Bill not found"
            }), 404

        conn.commit()

        return jsonify(serialize_bill(bill))

    finally:
        conn.close()


# ---------------------------------------------------------
# DELETE bill
# ---------------------------------------------------------

@app.route("/api/bills/<int:bill_id>", methods=["DELETE"])
def delete_bill(bill_id):

    conn = get_db()

    try:
        with conn.cursor() as cur:

            cur.execute(
                "DELETE FROM bills WHERE id = %s",
                (bill_id,)
            )

            deleted = cur.rowcount

        conn.commit()

        if deleted == 0:
            return jsonify({
                "error": "Bill not found"
            }), 404

        return jsonify({
            "message": "Bill deleted successfully"
        })

    finally:
        conn.close()


# ---------------------------------------------------------
# AI CONTEXT
# ---------------------------------------------------------

def get_bill_context():

    conn = get_db()

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            cur.execute("""
                SELECT
                    id,
                    name,
                    amount,
                    due_date,
                    frequency,
                    status
                FROM bills
                ORDER BY due_date ASC
            """)

            bills = cur.fetchall()

        return [serialize_bill(bill) for bill in bills]

    finally:
        conn.close()


def build_ai_prompt(question, bills):

    total = sum(
        float(bill["amount"])
        for bill in bills
    )

    pending = [
        bill for bill in bills
        if bill["status"].lower() != "paid"
    ]

    return f"""
You are the Bill Tracker AI assistant.

You have access to the application's current bill data.

Your job is to answer questions about these bills accurately.

Do not invent bills or financial information.

If the requested information is not available in the data,
say that it is not available.

Current total value of all bills:
${total:.2f}

Number of bills:
{len(bills)}

Number of unpaid/pending bills:
{len(pending)}

Bills:
{bills}

User question:
{question}

Give a concise and useful answer.
"""


# ---------------------------------------------------------
# AI CHAT
# ---------------------------------------------------------

@app.route("/api/chat", methods=["POST"])
def chat():

    data = request.get_json()

    question = data.get("message", "").strip()

    if not question:
        return jsonify({
            "error": "Message is required"
        }), 400

    bills = get_bill_context()

    prompt = build_ai_prompt(
        question,
        bills
    )

    try:

        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2
                }
            },
            timeout=120
        )

        response.raise_for_status()

        result = response.json()

        return jsonify({
            "response": result.get("response", ""),
            "model": OLLAMA_MODEL
        })

    except requests.exceptions.RequestException as e:

        return jsonify({
            "error": "Unable to connect to Ollama",
            "details": str(e)
        }), 503


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5004,
        debug=False
    )
