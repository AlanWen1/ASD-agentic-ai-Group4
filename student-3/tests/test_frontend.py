from __future__ import annotations

import importlib.util
from pathlib import Path


FRONTEND_DIR = Path(__file__).parents[1] / "frontend"
SPEC = importlib.util.spec_from_file_location("student3_frontend_app", FRONTEND_DIR / "app.py")
frontend_module = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(frontend_module)


def test_frontend_home_contains_crud_and_ai_chat():
    app = frontend_module.create_app("http://backend.test")
    app.config.update(TESTING=True)
    response = app.test_client().get("/")
    page = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Income & Pay Schedule Manager" in page
    assert "Income sources" in page
    assert "Pay schedules" in page
    assert "AI Income Assistant" in page


def test_frontend_health():
    app = frontend_module.create_app("http://backend.test")
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json()["service"] == "student-3-frontend"
