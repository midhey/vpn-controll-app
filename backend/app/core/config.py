"""Настройки приложения из переменных окружения.

Скелет работает в памяти и не тянет pydantic-settings. При подключении БД
сюда добавятся DATABASE_URL, APP_SECRET_KEY и ENCRYPTION_KEY
(см. ../backend-fastapi-plan-for-claude.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(value: str | None, default: list[str]) -> list[str]:
    if value is None or value.strip() == "":
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    app_env: str = "local"
    session_cookie_name: str = "vca_session"
    session_ttl_days: int = 30
    issue_result_ttl_minutes: int = 15
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])
    csrf_enabled: bool = False
    cookie_secure: bool = False
    first_admin_login: str = "midhey"
    first_admin_password: str | None = None
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_minutes: int = 15
    agent_mode: str = "fake"  # fake | http
    setup_worker_enabled: bool = True
    setup_worker_poll_seconds: float = 0.5
    setup_step_delay_seconds: float = 1.2

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        env = dict(os.environ) if env is None else env
        app_env = env.get("APP_ENV", "local").strip() or "local"
        not_local = app_env != "local"
        return cls(
            app_env=app_env,
            session_cookie_name=env.get("SESSION_COOKIE_NAME", "vca_session"),
            session_ttl_days=int(env.get("SESSION_TTL_DAYS", "30")),
            issue_result_ttl_minutes=int(env.get("ISSUE_RESULT_TTL_MINUTES", "15")),
            cors_origins=_csv(env.get("CORS_ORIGINS"), ["http://localhost:5173"]),
            csrf_enabled=_bool(env.get("CSRF_ENABLED"), not_local),
            cookie_secure=_bool(env.get("COOKIE_SECURE"), not_local),
            first_admin_login=env.get("FIRST_ADMIN_LOGIN", "midhey"),
            first_admin_password=env.get("FIRST_ADMIN_PASSWORD") or None,
            login_rate_limit_attempts=int(env.get("LOGIN_RATE_LIMIT_ATTEMPTS", "5")),
            login_rate_limit_window_minutes=int(
                env.get("LOGIN_RATE_LIMIT_WINDOW_MINUTES", "15")
            ),
            agent_mode=env.get("AGENT_MODE", "fake"),
            setup_worker_enabled=_bool(env.get("SETUP_WORKER_ENABLED"), True),
            setup_worker_poll_seconds=float(env.get("SETUP_WORKER_POLL_SECONDS", "0.5")),
            setup_step_delay_seconds=float(env.get("SETUP_STEP_DELAY_SECONDS", "1.2")),
        )
