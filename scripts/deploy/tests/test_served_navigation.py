"""A green deployment must not conceal stale localhost navigation assets."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("served_navigation_smoke", Path(__file__).parents[1] / "cloud_smoke.py")
smoke_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke_module)


@pytest.mark.parametrize("destination", ["http://localhost:3003/", "https://localhost:3003/",
    "http://127.0.0.1:3003/", "http://host.docker.internal:3003/"])
def test_rejects_stale_javascript_even_when_page_and_headers_are_valid(monkeypatch, destination):
    headers = {"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
               "Strict-Transport-Security": "max-age=31536000"}
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        content = f'link.href = "{destination}";' if url.endswith("/static/app.js") else '<a href="https://income.example.invalid/">Income</a>'
        return SimpleNamespace(status_code=200, headers=headers, text=content,
            content=content.encode(), raise_for_status=lambda: None)

    monkeypatch.setattr(smoke_module.requests, "get", get)
    smoke = smoke_module.Smoke({"frontends": {"finance": "https://finance.example.invalid"}})
    monkeypatch.setattr(smoke, "accounts", lambda: pytest.fail("Stale navigation must fail before creating accounts"))
    with pytest.raises(RuntimeError, match="local host destination"):
        smoke.run()
    assert calls == ["https://finance.example.invalid/", "https://finance.example.invalid/static/app.js"]
    assert smoke.log[0]["path"] == "/static/app.js"
    assert len(smoke.log[0]["sha256"]) == 64
