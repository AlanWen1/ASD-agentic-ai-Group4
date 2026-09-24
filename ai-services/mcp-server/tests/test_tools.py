import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools


def _mock_response(json_body, status_code=200):
    return MagicMock(
        status_code=status_code,
        json=lambda: json_body,
        raise_for_status=lambda: None,
    )


@patch("tools.requests.get")
def test_get_expenses_calls_expense_db_with_user_id(mock_get):
    mock_get.return_value = _mock_response([{"id": 1, "amount": 12.5}])

    result = tools.get_expenses(1)

    assert result == [{"id": 1, "amount": 12.5}]
    called_url = mock_get.call_args.args[0]
    assert called_url == f"{tools.EXPENSE_DB_URL}/expenses"
    assert mock_get.call_args.kwargs["params"] == {"user_id": 1}


@patch("tools.requests.get")
def test_get_expenses_forwards_category_id_filter(mock_get):
    mock_get.return_value = _mock_response([])

    tools.get_expenses(1, category_id=3)

    assert mock_get.call_args.kwargs["params"] == {"user_id": 1, "category_id": 3}


def test_get_expenses_requires_user_id():
    assert tools.get_expenses(None) == {"error": "user_id is required"}


@patch("tools.requests.get")
def test_get_categories_calls_expense_db(mock_get):
    mock_get.return_value = _mock_response([{"id": 1, "name": "Groceries"}])

    result = tools.get_categories(1)

    assert result == [{"id": 1, "name": "Groceries"}]
    assert mock_get.call_args.args[0] == f"{tools.EXPENSE_DB_URL}/categories"


@patch("tools.requests.get")
def test_get_bills_calls_bill_db(mock_get):
    mock_get.return_value = _mock_response([{"id": 1, "status": "Pending"}])

    result = tools.get_bills(1)

    assert result == [{"id": 1, "status": "Pending"}]
    assert mock_get.call_args.args[0] == f"{tools.BILL_DB_URL}/bills"


@patch("tools.requests.get")
def test_get_bills_summary_calls_bill_db_summary(mock_get):
    mock_get.return_value = _mock_response({"bill_count": 2, "total_amount": 100.0})

    result = tools.get_bills_summary(1)

    assert result["bill_count"] == 2
    assert mock_get.call_args.args[0] == f"{tools.BILL_DB_URL}/summary"


@patch("tools.requests.get")
def test_get_income_sources_calls_income_db(mock_get):
    mock_get.return_value = _mock_response({"items": [], "count": 0})

    result = tools.get_income_sources(1)

    assert result == {"items": [], "count": 0}
    assert mock_get.call_args.args[0] == f"{tools.INCOME_DB_URL}/api/income-sources"


@patch("tools.requests.get")
def test_get_pay_schedules_calls_income_db(mock_get):
    mock_get.return_value = _mock_response({"items": [], "count": 0})

    tools.get_pay_schedules(1)

    assert mock_get.call_args.args[0] == f"{tools.INCOME_DB_URL}/api/pay-schedules"


@patch("tools.requests.get")
def test_get_savings_goals_does_not_filter_by_user(mock_get):
    mock_get.return_value = _mock_response([{"id": 1, "goal_name": "Trip"}])

    result = tools.get_savings_goals(user_id=42)

    assert result == [{"id": 1, "goal_name": "Trip"}]
    assert mock_get.call_args.args[0] == f"{tools.SAVINGS_DB_URL}/goals"
    # user_id must NOT be sent upstream — the real /goals endpoint has no such param.
    assert mock_get.call_args.kwargs.get("params") is None


@patch("tools.requests.get")
def test_get_budgets_uses_x_user_id_header_not_query_param(mock_get):
    mock_get.return_value = _mock_response([{"id": 1, "month": 9}])

    result = tools.get_budgets(7)

    assert result == [{"id": 1, "month": 9}]
    assert mock_get.call_args.args[0] == f"{tools.BUDGET_BACKEND_URL}/api/budgets"
    assert mock_get.call_args.kwargs["headers"] == {"X-User-Id": "7"}


def test_get_budgets_requires_user_id():
    assert tools.get_budgets(None) == {"error": "user_id is required"}


@patch("tools.requests.get")
def test_get_returns_structured_error_on_connection_failure(mock_get):
    mock_get.side_effect = tools.requests.RequestException("connection refused")

    result = tools.get_expenses(1)

    assert "error" in result
    assert "Could not reach" in result["error"]


@patch("tools.requests.get")
def test_get_returns_structured_error_on_http_error_status(mock_get):
    mock_get.return_value = _mock_response({"error": "user_id is required"}, status_code=400)

    result = tools.get_bills(1)

    assert result == {"error": "user_id is required", "status_code": 400}
