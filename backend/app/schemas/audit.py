from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.domain.models import AuditLogEntry


class AuditLogOut(BaseModel):
    id: str
    action: str
    actor_user_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    metadata: dict[str, Any] = {}
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime

    @classmethod
    def from_domain(cls, entry: AuditLogEntry) -> AuditLogOut:
        return cls(
            id=entry.id,
            action=entry.action,
            actor_user_id=entry.actor_user_id,
            target_type=entry.target_type,
            target_id=entry.target_id,
            metadata=entry.metadata,
            ip_address=entry.ip_address,
            user_agent=entry.user_agent,
            created_at=entry.created_at,
        )
