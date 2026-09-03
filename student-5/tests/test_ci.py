import os
import sys
import tempfile

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "database")
    )
)

import app as database_app


def setup_module():
    database_app.DATABASE = os.path.join(
        tempfile.gettempdir(),
        "test_savings_ci.db"
    )

    if os.path.exists(database_app.DATABASE):
        os.remove(database_app.DATABASE)

    database_app.create_database()
    database_app.seed_data()


def teardown_module():
    if os.path.exists(database_app.DATABASE):
        os.remove(database_app.DATABASE)


def test_seed_data_has_ten_goals():
    client = database_app.app.test_client()

    response = client.get("/goals")

    assert response.status_code == 200

    goals = response.get_json()

    assert len(goals) >= 10


def test_create_goal():
    client = database_app.app.test_client()

    response = client.post(
        "/goals",
        json={
            "user_id": 1,
            "goal_name": "CI Test Goal",
            "target_amount": 1000,
            "current_amount": 100,
            "target_date": "2027-12-31"
        }
    )

    assert response.status_code == 201

    data = response.get_json()

    assert data["message"] == "Savings goal created successfully"
    assert "goal_id" in data


def test_get_goals():
    client = database_app.app.test_client()

    response = client.get("/goals")

    assert response.status_code == 200
    assert isinstance(response.get_json(), list)