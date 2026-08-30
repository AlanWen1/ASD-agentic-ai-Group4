import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_home_requires_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_register_and_login(client):
    client.post(
        "/register",
        data={"username": "testuser", "password": "test123", "confirm_password": "test123"},
    )
    response = client.post(
        "/login",
        data={"username": "testuser", "password": "test123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Budget Manager" in response.data


def test_wrong_password_rejected(client):
    client.post(
        "/register",
        data={"username": "testuser2", "password": "test123", "confirm_password": "test123"},
    )
    response = client.post(
        "/login",
        data={"username": "testuser2", "password": "wrongpassword"},
        follow_redirects=True,
    )
    assert b"Invalid username or password" in response.data


def test_logout(client):
    client.post(
        "/register",
        data={"username": "testuser3", "password": "test123", "confirm_password": "test123"},
    )
    client.post("/login", data={"username": "testuser3", "password": "test123"})
    response = client.get("/logout", follow_redirects=True)
    assert b"Sign in" in response.data
