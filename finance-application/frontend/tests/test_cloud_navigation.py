import importlib.util
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("finance_frontend_navigation", Path(__file__).parents[1] / "app.py")
frontend = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = frontend
SPEC.loader.exec_module(frontend)


def test_cloud_home_uses_all_five_configured_module_urls(monkeypatch):
    for name in ("budget", "expense", "income", "bill", "savings"):
        monkeypatch.setenv(name.upper() + "_FRONTEND_URL", "https://" + name + ".example.test")
    response = frontend.app.test_client().get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert response.status_code == 200 and "http://localhost:" not in html
    for name in ("budget", "expense", "income", "bill", "savings"):
        assert 'data-base-url="https://' + name + '.example.test/"' in html


def test_frontend_adds_security_headers_for_cloud(monkeypatch):
    monkeypatch.setenv("APP_ENV", "cloud")
    response = frontend.app.test_client().get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "max-age" in response.headers["Strict-Transport-Security"]


def test_retains_upstream_url_environment_names(monkeypatch):
    monkeypatch.delenv("INCOME_FRONTEND_URL", raising=False)
    monkeypatch.setenv("INCOME_URL", "https://income.example.test")
    assert 'data-base-url="https://income.example.test/"' in frontend.app.test_client().get("/").get_data(as_text=True)
