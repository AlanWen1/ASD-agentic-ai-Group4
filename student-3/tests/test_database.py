from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "database" / "app.py"
SPEC = importlib.util.spec_from_file_location("student3_database_app", MODULE_PATH)
database_module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(database_module)


def make_client(tmp_path):
    app = database_module.create_app(str(tmp_path / "test-income.db"))
    app.config.update(TESTING=True)
    return app.test_client()


def test_seed_data_has_at_least_ten_rows_per_table(tmp_path):
    client = make_client(tmp_path)
    sources = client.get("/api/income-sources").get_json()
    schedules = client.get("/api/pay-schedules").get_json()
    assert sources["count"] >= 10
    assert schedules["count"] >= 10


def test_income_source_crud(tmp_path):
    client = make_client(tmp_path)
    created = client.post(
        "/api/income-sources",
        json={
            "source_name": "Test Contract",
            "income_type": "Freelance",
            "standard_amount": 250,
            "payment_frequency": "monthly",
            "active": True,
        },
    )
    assert created.status_code == 201
    source_id = created.get_json()["id"]

    fetched = client.get(f"/api/income-sources/{source_id}")
    assert fetched.get_json()["source_name"] == "Test Contract"

    updated = client.put(f"/api/income-sources/{source_id}", json={"standard_amount": 300})
    assert updated.status_code == 200
    assert updated.get_json()["standard_amount"] == 300

    deleted = client.delete(f"/api/income-sources/{source_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/income-sources/{source_id}").status_code == 404


def test_pay_schedule_crud_and_validation(tmp_path):
    client = make_client(tmp_path)
    source = client.post(
        "/api/income-sources",
        json={
            "source_name": "Test Salary",
            "income_type": "Salary",
            "standard_amount": 1000,
            "payment_frequency": "fortnightly",
            "active": True,
        },
    ).get_json()
    invalid = client.post(
        "/api/pay-schedules",
        json={
            "income_source_id": source["id"],
            "expected_pay_date": "2026-08-28",
            "expected_amount": 1000,
            "status": "received",
        },
    )
    assert invalid.status_code == 400

    created = client.post(
        "/api/pay-schedules",
        json={
            "income_source_id": source["id"],
            "expected_pay_date": "2026-08-28",
            "expected_amount": 1000,
            "status": "scheduled",
            "notes": "Test schedule",
        },
    )
    assert created.status_code == 201
    schedule_id = created.get_json()["id"]

    updated = client.put(
        f"/api/pay-schedules/{schedule_id}",
        json={
            "status": "received",
            "received_date": "2026-08-28",
            "actual_amount": 1020,
        },
    )
    assert updated.status_code == 200
    assert updated.get_json()["actual_amount"] == 1020
    assert client.delete(f"/api/pay-schedules/{schedule_id}").status_code == 204


def test_source_with_schedules_cannot_be_deleted(tmp_path):
    client = make_client(tmp_path)
    response = client.delete("/api/income-sources/1")
    assert response.status_code == 409
