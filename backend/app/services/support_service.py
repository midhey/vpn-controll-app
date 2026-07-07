"""«Поддержка сервера»: дружеская история взносов, не платежи.

Никаких долгов, сроков и автоотключений. Видимость для участника:
глобально включено И включено у участника И участник не free/family.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.domain.models import SupportContribution, SupportSettings, User
from app.services.audit_service import AuditService
from app.services.user_service import UserService
from app.storage.memory import InMemoryStorage

_SETTINGS_PATCHABLE = {
    "title",
    "description",
    "sbp_phone",
    "bank_name",
    "extra_contact",
    "monthly_cost_amount",
    "reserve_amount",
    "is_enabled",
}


class SupportService:
    def __init__(
        self,
        storage: InMemoryStorage,
        users: UserService,
        audit: AuditService,
        clock: Callable[[], datetime],
    ) -> None:
        self._storage = storage
        self._users = users
        self._audit = audit
        self._clock = clock

    def visible_for(self, user: User) -> bool:
        settings = self._storage.get_support_settings()
        return settings.is_enabled and user.show_server_support and not user.free_access

    def view_for(self, user: User) -> dict[str, Any]:
        if not self.visible_for(user):
            return {"visible": False}
        settings = self._storage.get_support_settings()
        return {
            "visible": True,
            "title": settings.title,
            "description": settings.description,
            "sbp_phone": settings.sbp_phone,
            "bank_name": settings.bank_name,
            "extra_contact": settings.extra_contact,
            "monthly_cost_amount": settings.monthly_cost_amount,
            "reserve_amount": settings.reserve_amount,
        }

    def history_for(self, user: User) -> tuple[bool, list[SupportContribution]]:
        if not self.visible_for(user):
            return False, []
        return True, self._storage.list_contributions_for_user(user.id)

    def list_for_user_admin(self, user_id: str) -> list[SupportContribution]:
        self._users.get(user_id)  # 404, если участника нет
        return self._storage.list_contributions_for_user(user_id)

    def record(
        self,
        actor: User,
        user_id: str,
        *,
        amount: float,
        currency: str = "RUB",
        period_label: str | None = None,
        comment: str | None = None,
    ) -> SupportContribution:
        user = self._users.get(user_id)
        now = self._clock()
        contribution = SupportContribution(
            id=str(uuid.uuid4()),
            user_id=user.id,
            amount=amount,
            currency=currency,
            recorded_by_user_id=actor.id,
            recorded_at=now,
            created_at=now,
            period_label=period_label,
            comment=comment,
        )
        self._storage.add_contribution(contribution)
        self._audit.log(
            "support_contribution_recorded",
            actor_user_id=actor.id,
            target_type="user",
            target_id=user.id,
            metadata={"amount": amount, "currency": currency, "period": period_label},
        )
        return contribution

    def get_settings(self) -> SupportSettings:
        return self._storage.get_support_settings()

    def update_settings(self, actor: User, patch: dict[str, Any]) -> SupportSettings:
        settings = self._storage.get_support_settings()
        changed = []
        for field_name, value in patch.items():
            if field_name not in _SETTINGS_PATCHABLE:
                continue
            if getattr(settings, field_name) != value:
                setattr(settings, field_name, value)
                changed.append(field_name)
        if changed:
            settings.updated_by_user_id = actor.id
            settings.updated_at = self._clock()
            self._storage.save_support_settings(settings)
            self._audit.log(
                "support_settings_updated",
                actor_user_id=actor.id,
                target_type="support_settings",
                metadata={"changed": changed},
            )
        return settings
