"""Настройки приложения из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv


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
    database_url: str | None = None
    db_host: str | None = None
    db_port: int = 5432
    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None
    db_sslmode: str = "require"
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
        if env is None:
            load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        env = dict(os.environ) if env is None else env
        app_env = env.get("APP_ENV", "local").strip() or "local"
        not_local = app_env != "local"
        return cls(
            app_env=app_env,
            database_url=_build_database_url(env),
            db_host=env.get("DB_HOST") or None,
            db_port=int(env.get("DB_PORT") or "5432"),
            db_name=env.get("DB_NAME") or None,
            db_user=env.get("DB_USER") or None,
            db_password=env.get("DB_PASSWORD") or None,
            db_sslmode=env.get("DB_SSLMODE") or "require",
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


def _build_database_url(env: dict[str, str]) -> str | None:
    direct_url = _normalize_database_url(env.get("DATABASE_URL"))
    if direct_url is not None:
        return _with_sslmode(direct_url, env.get("DB_SSLMODE") or "require")
    host = env.get("DB_HOST")
    name = env.get("DB_NAME")
    user = env.get("DB_USER")
    password = env.get("DB_PASSWORD")
    if not host and not name and not user and not password:
        return None
    if not all([host, name, user, password]):
        missing = [
            key
            for key in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD")
            if not env.get(key)
        ]
        raise ValueError("Для подключения к БД не хватает: " + ", ".join(missing))
    return (
        "postgresql+psycopg://"
        f"{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{int(env.get('DB_PORT') or '5432')}"
        f"/{quote(name, safe='')}"
        f"?sslmode={quote(env.get('DB_SSLMODE') or 'require', safe='')}"
    )


def _normalize_database_url(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    value = value.strip()
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql+asyncpg://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql+asyncpg://")
    return value


def _with_sslmode(database_url: str, sslmode: str) -> str:
    parts = urlsplit(database_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("sslmode", sslmode)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
