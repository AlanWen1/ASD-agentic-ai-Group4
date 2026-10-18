
"""Automated endpoint tests for the Savings Goal Manager backend."""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "backend"),
)

import app as backend 


@pytest.fixture
def client(monkeypatch):
    """Create a test client authenticated as user 24."""
    monkeypatch.setattr(
        backend,
        "current_user",
        lambda: ({"id": 24}, None),
    )

    backend.app.config["TESTING"] = True
    return backend.app.test_client()


def test_get_goals_filters_out_other_users(client, monkeypatch):
    """The collection endpoint must only expose the signed-in user's goals."""
    database_records = [
        {
            "goal_id": 101,
            "user_id": 24,
            "goal_name": "New laptop",
            "target_amount": 1500,
            "current_amount": 600,
            "target_date": "2027-06-30",
        },
        {
            "goal_id": 102,
            "user_id": 75,
            "goal_name": "Holiday",
            "target_amount": 3000,
            "current_amount": 800,
            "target_date": "2027-08-30",
        },
    ]

    database_reply = Mock()
    database_reply.status_code = 200
    database_reply.json.return_value = database_records

    monkeypatch.setattr(
        backend.requests,
        "get",
        Mock(return_value=database_reply),
    )

    result = client.get("/goals")
    returned_goals = result.get_json()

    assert result.status_code == 200
    assert isinstance(returned_goals, list)
    assert [item["goal_id"] for item in returned_goals] == [101]
    assert returned_goals[0]["goal_name"] == "New laptop"


def test_get_goal_details_calculates_remaining_balance(client, monkeypatch):
    """The detail endpoint must calculate the amount still needed."""
    database_goal = {
        "goal_id": 205,
        "user_id": 24,
        "goal_name": "Driving lessons",
        "target_amount": 1200,
        "current_amount": 450,
        "target_date": "2027-11-30",
    }
    

    def database_response(url, **kwargs):
        response = Mock()
        response.status_code = 200
        response.json.return_value = (
            database_goal if url.endswith("/goals/205") else []
        )
        return response

    fake_get = Mock(side_effect=database_response)
    monkeypatch.setattr(backend.requests, "get", fake_get)

    result = client.get("/goals/205")
    details = result.get_json()

    assert result.status_code == 200
    assert details["goal_id"] == 205
    assert details["goal_name"] == "Driving lessons"
    assert details["remaining_amount"] == 750
    assert details["progress_percentage"] == pytest.approx(37.5)

    assert any(
        call.args and call.args[0].endswith("/goals/205")
        for call in fake_get.call_args_list
    )
