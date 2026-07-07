from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

ADMIN_LOGIN = "midhey"
ADMIN_PASSWORD = "admin-pass-123"


def make_settings(**overrides) -> Settings:
    defaults = dict(
        app_env="local",
        first_admin_login=ADMIN_LOGIN,
        first_admin_password=ADMIN_PASSWORD,
        csrf_enabled=False,
        cookie_secure=False,
        setup_worker_enabled=True,
        setup_worker_poll_seconds=0.01,
        setup_step_delay_seconds=0.0,
    )
    defaults.update(overrides)
    return Settings(**defaults)


@pytest.fixture()
def client():
    app = create_app(make_settings())
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, login_name: str, password: str) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"login": login_name, "password": password}
    )
    assert response.status_code == 200, response.text


def login_admin(client: TestClient) -> None:
    login(client, ADMIN_LOGIN, ADMIN_PASSWORD)


def add_fake_server(client: TestClient, name: str = "Helsinki-1") -> str:
    """Добавляет узел с фейковым агентом и прогоняет health-check до online."""
    response = client.post(
        "/api/v1/admin/servers",
        json={
            "name": name,
            "public_host": "203.0.113.10",
            "agent_base_url": f"http://{name.lower()}:8090",
            "agent_key_id": "backend-test",
            "agent_secret": "test-agent-secret",
        },
    )
    assert response.status_code == 201, response.text
    server_id = response.json()["id"]
    response = client.post(f"/api/v1/admin/servers/{server_id}/health-check")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "online"
    return server_id


def create_user(client: TestClient, login_name: str, password: str, **fields) -> dict:
    payload = {
        "login": login_name,
        "display_name": login_name.title(),
        "password": password,
        **fields,
    }
    response = client.post("/api/v1/admin/users", json=payload)
    assert response.status_code == 201, response.text
    return response.json()
