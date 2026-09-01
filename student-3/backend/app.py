"""Business/API service for Yongjian Zhou's Income & Pay Schedule Manager."""

from __future__ import annotations

import calendar
import os
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import requests
from flask import Flask, Response, jsonify, request

from ai_service import AIServiceError, ask_ollama, check_ollama


MONEY = Decimal("0.01")


def money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def public_money(value: Decimal) -> float:
    return float(value.quantize(MONEY, rounding=ROUND_HALF_UP))


def parse_month(value: str | None) -> str:
    selected = value or date.today().strftime("%Y-%m")
    try:
        date.fromisoformat(f"{selected}-01")
    except ValueError as exc:
        raise ValueError("month must use YYYY-MM format") from exc
    return selected


def add_months(start: date, months: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate_payment_dates(start: date, frequency: str, count: int) -> list[date]:
    if frequency == "weekly":
        return [start + timedelta(days=7 * index) for index in range(count)]
    if frequency == "fortnightly":
        return [start + timedelta(days=14 * index) for index in range(count)]
    if frequency == "monthly":
        return [add_months(start, index) for index in range(count)]
    if frequency == "quarterly":
        return [add_months(start, 3 * index) for index in range(count)]
    if frequency == "annually":
        return [add_months(start, 12 * index) for index in range(count)]
    if frequency == "one-off":
        return [start]
    raise ValueError("Unsupported payment frequency")


def create_app(database_url: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DATABASE_SERVICE_URL"] = (
        database_url or os.getenv("DATABASE_SERVICE_URL", "http://student-3-database:6003")
    ).rstrip("/")

    def database_request(method: str, path: str, **kwargs) -> requests.Response:
        try:
            response = requests.request(
                method,
                f"{app.config['DATABASE_SERVICE_URL']}{path}",
                timeout=10,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Database service is unavailable: {exc}") from exc
        return response

    def database_json(method: str, path: str, **kwargs) -> tuple[Any, int]:
        response = database_request(method, path, **kwargs)
        if response.status_code == 204:
            return None, 204
        try:
            payload = response.json()
        except ValueError:
            payload = {"error": "Database service returned invalid JSON"}
        return payload, response.status_code

    def forward(method: str, path: str):
        kwargs: dict[str, Any] = {"params": request.args}
        if request.is_json:
            kwargs["json"] = request.get_json(silent=True)
        payload, status = database_json(method, path, **kwargs)
        if status == 204:
            return Response(status=204)
        return jsonify(payload), status

    def build_summary(month: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        schedule_payload, schedule_status = database_json(
            "GET", "/api/pay-schedules", params={"month": month}
        )
        if schedule_status != 200:
            raise RuntimeError(schedule_payload.get("error", "Could not load pay schedules"))
        source_payload, source_status = database_json("GET", "/api/income-sources")
        if source_status != 200:
            raise RuntimeError(source_payload.get("error", "Could not load income sources"))

        schedules = schedule_payload["items"]
        active_source_count = sum(1 for item in source_payload["items"] if item["active"])
        expected_total = Decimal("0")
        received_total = Decimal("0")
        received_expected_total = Decimal("0")
        outstanding_total = Decimal("0")
        counts = defaultdict(int)
        by_source: dict[int, dict[str, Any]] = {}

        for item in schedules:
            status = item["status"]
            counts[status] += 1
            expected = money(item["expected_amount"])
            if status != "cancelled":
                expected_total += expected
            if status == "received":
                actual = money(item["actual_amount"])
                received_total += actual
                received_expected_total += expected
            elif status in {"scheduled", "late"}:
                outstanding_total += expected

            source_bucket = by_source.setdefault(
                item["income_source_id"],
                {
                    "income_source_id": item["income_source_id"],
                    "source_name": item["source_name"],
                    "expected": Decimal("0"),
                    "received": Decimal("0"),
                },
            )
            if status != "cancelled":
                source_bucket["expected"] += expected
            if status == "received":
                source_bucket["received"] += money(item["actual_amount"])

        source_totals = [
            {
                **bucket,
                "expected": public_money(bucket["expected"]),
                "received": public_money(bucket["received"]),
            }
            for bucket in by_source.values()
        ]
        source_totals.sort(key=lambda item: item["received"], reverse=True)
        summary = {
            "month": month,
            "expected_total": public_money(expected_total),
            "received_total": public_money(received_total),
            "outstanding_total": public_money(outstanding_total),
            "variance": public_money(received_total - received_expected_total),
            "received_count": counts["received"],
            "scheduled_count": counts["scheduled"],
            "late_count": counts["late"],
            "cancelled_count": counts["cancelled"],
            "active_source_count": active_source_count,
            "by_source": source_totals,
        }
        return summary, schedules

    @app.get("/health")
    def health():
        database_health, status = database_json("GET", "/health")
        return jsonify(
            {
                "status": "healthy" if status == 200 else "degraded",
                "service": "student-3-backend",
                "database": database_health,
            }
        ), (200 if status == 200 else 503)

    @app.route("/api/income-sources", methods=["GET", "POST"])
    def income_sources():
        return forward(request.method, "/api/income-sources")

    @app.route("/api/income-sources/<int:source_id>", methods=["GET", "PUT", "DELETE"])
    def income_source(source_id: int):
        return forward(request.method, f"/api/income-sources/{source_id}")

    @app.route("/api/pay-schedules", methods=["GET", "POST"])
    def pay_schedules():
        return forward(request.method, "/api/pay-schedules")

    @app.route("/api/pay-schedules/<int:schedule_id>", methods=["GET", "PUT", "DELETE"])
    def pay_schedule(schedule_id: int):
        return forward(request.method, f"/api/pay-schedules/{schedule_id}")

    @app.get("/api/dashboard")
    def dashboard():
        selected_month = parse_month(request.args.get("month"))
        summary, schedules = build_summary(selected_month)
        return jsonify({"summary": summary, "schedules": schedules})

    @app.post("/api/pay-schedules/generate")
    def generate_pay_schedules():
        payload = request.get_json(silent=True) or {}
        try:
            source_id = int(payload.get("income_source_id"))
            count = int(payload.get("count", 3))
        except (TypeError, ValueError) as exc:
            raise ValueError("income_source_id and count must be integers") from exc
        if not 1 <= count <= 24:
            raise ValueError("count must be between 1 and 24")
        try:
            start = date.fromisoformat(str(payload.get("start_date", "")))
        except ValueError as exc:
            raise ValueError("start_date must use YYYY-MM-DD format") from exc

        source, source_status = database_json("GET", f"/api/income-sources/{source_id}")
        if source_status != 200:
            return jsonify(source), source_status
        dates = calculate_payment_dates(start, source["payment_frequency"], count)
        created: list[dict[str, Any]] = []
        for expected_date in dates:
            schedule, status = database_json(
                "POST",
                "/api/pay-schedules",
                json={
                    "income_source_id": source_id,
                    "expected_pay_date": expected_date.isoformat(),
                    "expected_amount": source["standard_amount"],
                    "status": "scheduled",
                    "notes": "Generated from income source frequency",
                },
            )
            if status != 201:
                return jsonify({"error": schedule.get("error", "Schedule generation failed"), "created": created}), status
            created.append(schedule)
        return jsonify({"items": created, "count": len(created)}), 201

    @app.get("/api/ai/status")
    def ai_status():
        result = check_ollama()
        return jsonify(result), (200 if result["available"] else 503)

    @app.post("/api/ai/analyse")
    def analyse_income():
        payload = request.get_json(silent=True) or {}
        selected_month = parse_month(payload.get("month"))
        summary, schedules = build_summary(selected_month)
        question = (
            "Summarise my income pattern for the selected month. Identify the main sources, "
            "received versus expected income, outstanding or late payments, and any clear variance."
        )
        answer = ask_ollama(question, {"summary": summary, "schedules": schedules})
        return jsonify({"answer": answer, "summary": summary, "month": selected_month})

    @app.post("/api/ai/chat")
    def ai_chat():
        payload = request.get_json(silent=True) or {}
        question = str(payload.get("message", "")).strip()
        if not question:
            raise ValueError("message is required")
        if len(question) > 2000:
            raise ValueError("message must be 2000 characters or fewer")
        selected_month = parse_month(payload.get("month"))
        summary, schedules = build_summary(selected_month)
        history = payload.get("history", [])
        if not isinstance(history, list):
            raise ValueError("history must be a list")
        answer = ask_ollama(
            question,
            {"summary": summary, "schedules": schedules},
            history=history,
        )
        return jsonify({"answer": answer, "month": selected_month})

    @app.errorhandler(ValueError)
    def handle_validation_error(error: ValueError):
        return jsonify({"error": str(error)}), 400

    @app.errorhandler(AIServiceError)
    def handle_ai_error(error: AIServiceError):
        return jsonify(
            {
                "error": str(error),
                "code": "AI_UNAVAILABLE",
                "hint": "Start Ollama and ensure the configured Qwen model is installed.",
            }
        ), 503

    @app.errorhandler(RuntimeError)
    def handle_dependency_error(error: RuntimeError):
        return jsonify({"error": str(error), "code": "DEPENDENCY_UNAVAILABLE"}), 503

    @app.errorhandler(404)
    def handle_unknown_route(_error):
        return jsonify({"error": "Route not found"}), 404

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5003, debug=False)
