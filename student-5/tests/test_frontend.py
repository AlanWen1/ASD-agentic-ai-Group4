import os
import importlib.util

FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend")
)

FRONTEND_PATH = os.path.join(FRONTEND_DIR, "app.py")

spec = importlib.util.spec_from_file_location(
    "student5_frontend_app",
    FRONTEND_PATH
)

frontend_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frontend_app)

frontend_app.app.template_folder = os.path.join(
    FRONTEND_DIR,
    "templates"
)

frontend_app.app.static_folder = os.path.join(
    FRONTEND_DIR,
    "static"
)


def make_client():
    frontend_app.app.config["TESTING"] = True
    return frontend_app.app.test_client()


def test_frontend_home_page_loads():
    client = make_client()

    response = client.get("/")

    assert response.status_code == 200