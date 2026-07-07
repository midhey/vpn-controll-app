"""Вход, выход и разбор сессий.

Сессии серверные: в куке живёт сырой токен, в хранилище — только его sha256.
Вход ограничен по частоте: N неудач за окно по логину или по IP -> 429.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, unauthorized
from app.core.security import (
    PasswordHasher,
    generate_session_token,
    hash_session_token,
)
from app.domain.models import Session, User
from app.services.audit_service import AuditService
from app.storage.memory import InMemoryStorage


class AuthService:
    def __init__(
        self,
        storage: InMemoryStorage,
        settings: Settings,
        hasher: PasswordHasher,
        audit: AuditService,
        clock: Callable[[], datetime],
    ) -> None:
        self._storage = storage
        self._settings = settings
        self._hasher = hasher
        self._audit = audit
        self._clock = clock

    def login(
        self, login: str, password: str, *, ip: str | None, user_agent: str | None
    ) -> tuple[User, str]:
        """Возвращает (пользователь, сырой токен для куки)."""
        login = login.strip().lower()
        now = self._clock()
        self._enforce_rate_limit(login, ip, now)

        user = self._storage.get_user_by_login(login)
        password_ok = user is not None and self._hasher.verify(password, user.password_hash)
        if user is None or not password_ok or not user.is_active:
            self._storage.record_login_failure(f"login:{login}", now)
            if ip:
                self._storage.record_login_failure(f"ip:{ip}", now)
            self._audit.log(
                "login_failed",
                metadata={"login": login},
                ip_address=ip,
                user_agent=user_agent,
            )
            # Единое сообщение: не раскрываем, что именно не так.
            raise unauthorized("Неверный логин или пароль")

        self._storage.clear_login_failures(f"login:{login}")
        token = generate_session_token()
        session = Session(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_session_token(token),
            created_at=now,
            expires_at=now + timedelta(days=self._settings.session_ttl_days),
            last_seen_at=now,
            user_agent=user_agent,
            ip_address=ip,
        )
        self._storage.add_session(session)
        self._audit.log(
            "login_success",
            actor_user_id=user.id,
            ip_address=ip,
            user_agent=user_agent,
        )
        return user, token

    def resolve_session(self, raw_token: str) -> User | None:
        session = self._storage.get_session_by_token_hash(hash_session_token(raw_token))
        now = self._clock()
        if session is None or session.revoked_at is not None or session.expires_at <= now:
            return None
        user = self._storage.get_user(session.user_id)
        if user is None or not user.is_active:
            return None
        session.last_seen_at = now
        self._storage.save_session(session)
        return user

    def logout(self, raw_token: str, *, ip: str | None, user_agent: str | None) -> None:
        session = self._storage.get_session_by_token_hash(hash_session_token(raw_token))
        if session is None or session.revoked_at is not None:
            return
        session.revoked_at = self._clock()
        self._storage.save_session(session)
        self._audit.log(
            "logout", actor_user_id=session.user_id, ip_address=ip, user_agent=user_agent
        )

    def _enforce_rate_limit(self, login: str, ip: str | None, now: datetime) -> None:
        since = now - timedelta(minutes=self._settings.login_rate_limit_window_minutes)
        attempts = self._storage.count_login_failures(f"login:{login}", since)
        if ip:
            attempts = max(attempts, self._storage.count_login_failures(f"ip:{ip}", since))
        if attempts >= self._settings.login_rate_limit_attempts:
            raise AppError(
                ErrorCode.RATE_LIMITED,
                "Слишком много попыток входа — подожди немного",
                status=429,
            )
