"""Участники: админ создаёт и управляет, саморегистрации нет."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.core.errors import AppError, ErrorCode, not_found
from app.core.security import PasswordHasher
from app.domain.models import User, UserRole
from app.services.audit_service import AuditService
from app.storage.memory import InMemoryStorage

# Поля, которые админ может менять через PATCH.
_PATCHABLE_FIELDS = {
    "display_name",
    "telegram_username",
    "role",
    "device_limit",
    "device_limit_unlimited",
    "show_server_support",
    "free_access",
    "note",
}


class UserService:
    def __init__(
        self,
        storage: InMemoryStorage,
        hasher: PasswordHasher,
        audit: AuditService,
        clock: Callable[[], datetime],
    ) -> None:
        self._storage = storage
        self._hasher = hasher
        self._audit = audit
        self._clock = clock

    def get(self, user_id: str) -> User:
        user = self._storage.get_user(user_id)
        if user is None:
            raise not_found("Участник не найден")
        return user

    def list_with_device_counts(self) -> list[tuple[User, int]]:
        return [
            (user, self._storage.count_devices_toward_limit(user.id))
            for user in self._storage.list_users()
        ]

    def create(
        self,
        actor: User,
        *,
        login: str,
        display_name: str,
        password: str,
        role: UserRole = UserRole.USER,
        telegram_username: str | None = None,
        device_limit: int | None = 3,
        device_limit_unlimited: bool = False,
        show_server_support: bool = True,
        free_access: bool = False,
        note: str | None = None,
    ) -> User:
        normalized = login.strip().lower()
        if self._storage.get_user_by_login(normalized) is not None:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Логин уже занят", status=409)
        now = self._clock()
        user = User(
            id=str(uuid.uuid4()),
            login=normalized,
            display_name=display_name.strip(),
            role=role,
            password_hash=self._hasher.hash(password),
            created_at=now,
            updated_at=now,
            telegram_username=telegram_username,
            device_limit=device_limit,
            device_limit_unlimited=device_limit_unlimited,
            show_server_support=show_server_support,
            free_access=free_access,
            note=note,
            created_by_user_id=actor.id,
        )
        self._storage.add_user(user)
        self._audit.log(
            "user_created",
            actor_user_id=actor.id,
            target_type="user",
            target_id=user.id,
            metadata={"login": user.login, "role": user.role.value},
        )
        return user

    def update(self, actor: User, user_id: str, patch: dict[str, Any]) -> User:
        user = self.get(user_id)
        changed = []
        for field_name, value in patch.items():
            if field_name not in _PATCHABLE_FIELDS:
                continue
            if getattr(user, field_name) != value:
                setattr(user, field_name, value)
                changed.append(field_name)
        if changed:
            user.updated_at = self._clock()
            self._audit.log(
                "user_updated",
                actor_user_id=actor.id,
                target_type="user",
                target_id=user.id,
                metadata={"changed": changed},
            )
        return user

    def reset_password(self, actor: User, user_id: str, new_password: str) -> None:
        user = self.get(user_id)
        user.password_hash = self._hasher.hash(new_password)
        user.updated_at = self._clock()
        # Пароль сменился — старые сессии больше не доверяем.
        self._storage.revoke_sessions_for_user(user.id, self._clock())
        self._audit.log(
            "user_password_reset",
            actor_user_id=actor.id,
            target_type="user",
            target_id=user.id,
        )

    def set_active(self, actor: User, user_id: str, is_active: bool) -> User:
        user = self.get(user_id)
        if user.id == actor.id and not is_active:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Нельзя отключить самого себя", status=400)
        if user.is_active != is_active:
            user.is_active = is_active
            user.updated_at = self._clock()
            if not is_active:
                self._storage.revoke_sessions_for_user(user.id, self._clock())
            self._audit.log(
                "user_enabled" if is_active else "user_disabled",
                actor_user_id=actor.id,
                target_type="user",
                target_id=user.id,
            )
        return user
