"""Аудит действий. Секреты в metadata не пишутся — ответственность вызывающего."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.domain.models import AuditLogEntry
from app.storage.memory import InMemoryStorage


class AuditService:
    def __init__(self, storage: InMemoryStorage, clock: Callable[[], datetime]) -> None:
        self._storage = storage
        self._clock = clock

    def log(
        self,
        action: str,
        *,
        actor_user_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._storage.add_audit_entry(
            AuditLogEntry(
                id=str(uuid.uuid4()),
                action=action,
                created_at=self._clock(),
                actor_user_id=actor_user_id,
                target_type=target_type,
                target_id=target_id,
                metadata=metadata or {},
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )

    def list(self, limit: int = 100) -> list[AuditLogEntry]:
        return self._storage.list_audit_entries(limit)
