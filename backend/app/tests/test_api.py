"""Smoke-тесты API поверх in-memory хранилища и фейкового агента."""

from __future__ import annotations

import time

from app.tests.conftest import (
    ADMIN_LOGIN,
    ADMIN_PASSWORD,
    add_fake_server,
    create_user,
    login,
    login_admin,
)


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_logout_session(client):
    # Без сессии — 401 в едином формате ошибок.
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"

    login_admin(client)
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200
    assert response.json()["user"]["login"] == ADMIN_LOGIN

    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 200
    assert client.get("/api/v1/auth/session").status_code == 401


def test_login_wrong_password_and_rate_limit(client):
    for attempt in range(5):
        response = client.post(
            "/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": "wrong"}
        )
        assert response.status_code == 401
    response = client.post(
        "/api/v1/auth/login", json={"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_admin_creates_user_and_user_logs_in(client):
    login_admin(client)
    create_user(client, "dima", "dima-pass-1", device_limit=2)
    client.post("/api/v1/auth/logout")

    login(client, "dima", "dima-pass-1")
    response = client.get("/api/v1/me")
    assert response.json()["login"] == "dima"
    # Обычному участнику админка недоступна.
    assert client.get("/api/v1/admin/users").status_code == 403


def test_device_issue_flow_with_limit_and_revoke(client):
    login_admin(client)
    add_fake_server(client)
    create_user(client, "dima", "dima-pass-1", device_limit=2)
    client.post("/api/v1/auth/logout")
    login(client, "dima", "dima-pass-1")

    # Выпуск: конфиг и vpn_url приходят сразу.
    response = client.post("/api/v1/devices", json={"name": "iPhone 15"})
    assert response.status_code == 201, response.text
    created = response.json()
    device_id = created["device"]["id"]
    assert created["device"]["status"] == "active"
    assert created["issue_result"]["config"].startswith("[Interface]")
    assert created["issue_result"]["vpn_url"].startswith("vpn://")

    # Результат выпуска можно читать повторно, пока не истёк TTL.
    for _ in range(2):
        response = client.get(f"/api/v1/devices/{device_id}/issue-result")
        assert response.status_code == 200
        assert response.json()["config"].startswith("[Interface]")

    # Лимит: второе устройство ок, третье — device_limit_reached.
    assert client.post("/api/v1/devices", json={"name": "iPad"}).status_code == 201
    response = client.post("/api/v1/devices", json={"name": "MacBook"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "device_limit_reached"

    # Отзыв идемпотентен, после отзыва конфиг недоступен.
    assert client.delete(f"/api/v1/devices/{device_id}").json()["status"] == "revoked"
    assert client.delete(f"/api/v1/devices/{device_id}").status_code == 200
    assert client.get(f"/api/v1/devices/{device_id}/issue-result").status_code == 404
    # Лимит освободился.
    assert client.post("/api/v1/devices", json={"name": "MacBook"}).status_code == 201


def test_device_issue_without_servers_fails(client):
    login_admin(client)
    create_user(client, "dima", "dima-pass-1")
    client.post("/api/v1/auth/logout")
    login(client, "dima", "dima-pass-1")
    response = client.post("/api/v1/devices", json={"name": "iPhone"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "server_unavailable"


def test_foreign_device_is_hidden(client):
    login_admin(client)
    add_fake_server(client)
    create_user(client, "dima", "dima-pass-1")
    create_user(client, "katya", "katya-pass-1")
    client.post("/api/v1/auth/logout")

    login(client, "dima", "dima-pass-1")
    device_id = client.post("/api/v1/devices", json={"name": "iPhone"}).json()["device"]["id"]
    client.post("/api/v1/auth/logout")

    login(client, "katya", "katya-pass-1")
    assert client.get(f"/api/v1/devices/{device_id}").status_code == 404
    assert client.delete(f"/api/v1/devices/{device_id}").status_code == 404


def test_support_visibility_rules(client):
    login_admin(client)
    # Глобально выключено -> невидимо всем.
    create_user(client, "dima", "dima-pass-1")
    create_user(client, "mama", "mama-pass-1", free_access=True)
    client.post("/api/v1/auth/logout")

    login(client, "dima", "dima-pass-1")
    assert client.get("/api/v1/support").json() == {
        "visible": False,
        "title": None,
        "description": None,
        "sbp_phone": None,
        "bank_name": None,
        "extra_contact": None,
        "monthly_cost_amount": None,
        "reserve_amount": None,
    }
    client.post("/api/v1/auth/logout")

    # Админ включает поддержку глобально.
    login_admin(client)
    response = client.patch(
        "/api/v1/admin/support-settings",
        json={"is_enabled": True, "sbp_phone": "+7 900 000-00-00", "monthly_cost_amount": 500},
    )
    assert response.status_code == 200
    # И записывает взнос Диме.
    dima_id = next(
        u["id"] for u in client.get("/api/v1/admin/users").json() if u["login"] == "dima"
    )
    response = client.post(
        f"/api/v1/admin/users/{dima_id}/support-contributions",
        json={"amount": 500, "period_label": "июль 2026"},
    )
    assert response.status_code == 201
    client.post("/api/v1/auth/logout")

    # Обычный участник видит блок и свою историю.
    login(client, "dima", "dima-pass-1")
    view = client.get("/api/v1/support").json()
    assert view["visible"] is True
    assert view["sbp_phone"] == "+7 900 000-00-00"
    history = client.get("/api/v1/support/history").json()
    assert history["visible"] is True
    assert history["items"][0]["amount"] == 500
    client.post("/api/v1/auth/logout")

    # Free/family не видит ничего даже при включённой поддержке.
    login(client, "mama", "mama-pass-1")
    assert client.get("/api/v1/support").json()["visible"] is False
    assert client.get("/api/v1/support/history").json() == {"visible": False, "items": []}


def _wait_job(client, job_id: str, deadline_seconds: float = 5.0) -> dict:
    finished = {"success", "failed", "cancelled"}
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/admin/setup-jobs/{job_id}").json()
        if job["status"] in finished:
            return job
        time.sleep(0.02)
    raise AssertionError(f"setup job did not finish: {job}")


def test_setup_job_success_creates_online_server(client):
    login_admin(client)
    response = client.post(
        "/api/v1/admin/setup-jobs",
        json={
            "server_name": "Helsinki-VPS-2",
            "host": "95.217.10.42",
            "auth_method": "ssh_key",
            "secret": "PRIVATE-KEY",
            "region_note": "Финляндия",
        },
    )
    assert response.status_code == 201, response.text
    job = _wait_job(client, response.json()["id"])
    assert job["status"] == "success"
    assert job["server_node_id"]

    server = client.get(f"/api/v1/admin/servers/{job['server_node_id']}").json()
    assert server["status"] == "online"
    assert server["has_agent_secret"] is True

    events = client.get(f"/api/v1/admin/setup-jobs/{job['id']}/events").json()
    steps = [e["step"] for e in events]
    assert "checking_ssh" in steps and "success" in steps


def test_setup_job_failure_on_bad_host(client):
    login_admin(client)
    response = client.post(
        "/api/v1/admin/setup-jobs",
        json={
            "server_name": "Broken",
            "host": "fail.example.com",
            "auth_method": "password",
            "secret": "root-password",
        },
    )
    job = _wait_job(client, response.json()["id"])
    assert job["status"] == "failed"
    assert "SSH" in job["error_message"]


def test_audit_log_records_actions(client):
    login_admin(client)
    create_user(client, "dima", "dima-pass-1")
    entries = client.get("/api/v1/admin/audit-logs").json()
    actions = [e["action"] for e in entries]
    assert "login_success" in actions
    assert "user_created" in actions
