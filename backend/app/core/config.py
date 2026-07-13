"""Настройки приложения из переменных окружения."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from ipaddress import ip_network
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
    encryption_key: str | None = None
    setup_worker_enabled: bool = True
    setup_worker_poll_seconds: float = 0.5
    setup_step_delay_seconds: float = 1.2
    setup_runner: str = "stub"  # stub | deploy_script
    setup_deploy_script_path: str = "../agent/scripts/deploy-agent.sh"
    setup_agent_listen: str = "127.0.0.1:8090"
    setup_agent_base_url_template: str = "http://{host}:8090"
    setup_agent_allow_ips: list[str] = field(default_factory=list)
    setup_timeout_seconds: float = 600.0
    setup_allow_public_agent_access: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        if env is None:
            load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        env = dict(os.environ) if env is None else env
        app_env = env.get("APP_ENV", "local").strip() or "local"
        not_local = app_env != "local"
        settings = cls(
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
            encryption_key=env.get("ENCRYPTION_KEY") or None,
            setup_worker_enabled=_bool(env.get("SETUP_WORKER_ENABLED"), True),
            setup_worker_poll_seconds=float(env.get("SETUP_WORKER_POLL_SECONDS", "0.5")),
            setup_step_delay_seconds=float(env.get("SETUP_STEP_DELAY_SECONDS", "1.2")),
            setup_runner=env.get("SETUP_RUNNER", "stub").strip() or "stub",
            setup_deploy_script_path=(
                env.get("SETUP_DEPLOY_SCRIPT_PATH", "../agent/scripts/deploy-agent.sh").strip()
            ),
            setup_agent_listen=env.get("SETUP_AGENT_LISTEN", "127.0.0.1:8090").strip(),
            setup_agent_base_url_template=env.get(
                "SETUP_AGENT_BASE_URL_TEMPLATE", "http://{host}:8090"
            ).strip(),
            setup_agent_allow_ips=_csv(env.get("SETUP_AGENT_ALLOW_IPS"), []),
            setup_timeout_seconds=float(env.get("SETUP_TIMEOUT_SECONDS", "600")),
            setup_allow_public_agent_access=_bool(
                env.get("SETUP_ALLOW_PUBLIC_AGENT_ACCESS"), False
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        """Reject configurations that would silently turn a production install into a demo."""
        if self.agent_mode not in {"fake", "http"}:
            raise ValueError("AGENT_MODE must be fake or http")
        if self.setup_runner not in {"stub", "deploy_script"}:
            raise ValueError("SETUP_RUNNER must be stub or deploy_script")
        if self.setup_timeout_seconds <= 0:
            raise ValueError("SETUP_TIMEOUT_SECONDS must be positive")
        if "{host}" not in self.setup_agent_base_url_template:
            raise ValueError("SETUP_AGENT_BASE_URL_TEMPLATE must contain {host}")

        normalized_allow_ips: list[str] = []
        for value in self.setup_agent_allow_ips:
            try:
                network = ip_network(value, strict=False)
            except ValueError as exc:
                raise ValueError(
                    f"SETUP_AGENT_ALLOW_IPS contains invalid IP/CIDR: {value}"
                ) from exc
            if (
                self.app_env != "local"
                and network.prefixlen == 0
                and not self.setup_allow_public_agent_access
            ):
                raise ValueError(
                    "SETUP_AGENT_ALLOW_IPS must not allow the internet; set "
                    "SETUP_ALLOW_PUBLIC_AGENT_ACCESS=true only after an explicit risk review"
                )
            normalized_allow_ips.append(str(network))
        self.setup_agent_allow_ips = normalized_allow_ips

        if self.app_env == "local":
            return
        if self.agent_mode != "http":
            raise ValueError("AGENT_MODE=http is required outside APP_ENV=local")
        if not self.encryption_key:
            raise ValueError("ENCRYPTION_KEY is required outside APP_ENV=local")
        # Instantiate the box here so a malformed key fails before the app serves traffic.
        from app.core.security import FernetSecretBox

        FernetSecretBox(self.encryption_key)
        if self.setup_runner != "deploy_script":
            raise ValueError("SETUP_RUNNER=deploy_script is required outside APP_ENV=local")
        if not self.setup_agent_allow_ips:
            raise ValueError("SETUP_AGENT_ALLOW_IPS is required outside APP_ENV=local")


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
