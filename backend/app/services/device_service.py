"""Устройства: выпуск и отзыв VPN-конфигов, одноразовые результаты выпуска."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode, not_found
from app.core.security import SecretBox
from app.domain.models import (
    Device,
    DeviceConfigIssue,
    DeviceStatus,
    User,
    UserRole,
)
from app.services.agent_client import AgentClient
from app.services.audit_service import AuditService
from app.services.server_service import ServerService
from app.storage.memory import InMemoryStorage


class DeviceService:
    def __init__(
        self,
        storage: InMemoryStorage,
        servers: ServerService,
        agent: AgentClient,
        secret_box: SecretBox,
        settings: Settings,
        audit: AuditService,
        clock: Callable[[], datetime],
    ) -> None:
        self._storage = storage
        self._servers = servers
        self._agent = agent
        self._secret_box = secret_box
        self._settings = settings
        self._audit = audit
        self._clock = clock

    def list_for_user(self, user_id: str) -> list[Device]:
        return self._storage.list_devices_for_user(user_id)

    def get_for_actor(self, actor: User, device_id: str) -> Device:
        device = self._storage.get_device(device_id)
        # Чужие устройства выглядят как несуществующие — не раскрываем id.
        if device is None or (device.user_id != actor.id and actor.role != UserRole.ADMIN):
            raise not_found("Устройство не найдено")
        return device

    def server_name(self, device: Device) -> str | None:
        node = self._storage.get_server_node(device.server_node_id)
        return node.name if node else None

    async def create(
        self,
        user: User,
        *,
        name: str,
        server_node_id: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[Device, dict[str, Any]]:
        """Алгоритм из плана: лимит -> выбор узла -> provisioning -> агент -> active."""
        async with self._storage.lock:
            self._enforce_limit(user)
            if server_node_id is not None:
                node = self._servers.get(server_node_id)
                self._servers.ensure_selectable(node)
            else:
                picked = self._servers.pick_for_new_device()
                if picked is None:
                    raise AppError(
                        ErrorCode.SERVER_UNAVAILABLE,
                        "Сейчас нет доступного сервера — попробуй позже",
                        status=503,
                    )
                node = picked

            now = self._clock()
            device = Device(
                id=str(uuid.uuid4()),
                user_id=user.id,
                server_node_id=node.id,
                name=name.strip(),
                created_at=now,
                updated_at=now,
            )
            self._storage.add_device(device)
            try:
                result = await self._agent.issue_peer(
                    node,
                    name=f"{user.display_name} — {device.name}",
                    endpoint_host=node.public_host,
                    metadata={"backend_device_id": device.id},
                )
            except AppError as exc:
                device.status = DeviceStatus.FAILED
                device.failure_message = exc.message
                device.updated_at = self._clock()
                self._audit.log(
                    "device_issue_failed",
                    actor_user_id=user.id,
                    target_type="device",
                    target_id=device.id,
                    metadata={"code": exc.code.value, "server_node_id": node.id},
                    ip_address=ip,
                    user_agent=user_agent,
                )
                raise

            now = self._clock()
            device.public_key = result.public_key
            device.client_ip = result.client_ip
            device.status = DeviceStatus.ACTIVE
            device.last_config_issued_at = now
            device.updated_at = now
            issue = DeviceConfigIssue(
                id=str(uuid.uuid4()),
                device_id=device.id,
                issued_to_user_id=user.id,
                created_at=now,
                expires_at=now + timedelta(minutes=self._settings.issue_result_ttl_minutes),
                config_encrypted=self._secret_box.encrypt(result.config),
                vpn_url_encrypted=self._secret_box.encrypt(result.vpn_url),
            )
            self._storage.set_issue(issue)
            self._audit.log(
                "device_issued",
                actor_user_id=user.id,
                target_type="device",
                target_id=device.id,
                metadata={"server_node_id": node.id},
                ip_address=ip,
                user_agent=user_agent,
            )
            return device, {
                "device_id": device.id,
                "config": result.config,
                "vpn_url": result.vpn_url,
                "expires_at": issue.expires_at,
            }

    async def revoke(
        self,
        actor: User,
        device_id: str,
        *,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> Device:
        async with self._storage.lock:
            device = self.get_for_actor(actor, device_id)
            if device.status == DeviceStatus.REVOKED:
                return device  # идемпотентно
            node = self._storage.get_server_node(device.server_node_id)
            if device.public_key and node is not None:
                try:
                    await self._agent.revoke_peer(node, device.public_key)
                except AppError as exc:
                    # Узел недоступен — не отзываем локально, пусть повторят.
                    if exc.code == ErrorCode.AGENT_UNAVAILABLE:
                        raise
                    # agent_rejected (например, пир уже удалён) — продолжаем.
            now = self._clock()
            device.status = DeviceStatus.REVOKED
            device.revoked_at = now
            device.updated_at = now
            self._storage.drop_issue(device.id)
            self._audit.log(
                "device_revoked",
                actor_user_id=actor.id,
                target_type="device",
                target_id=device.id,
                metadata={"owner_user_id": device.user_id},
                ip_address=ip,
                user_agent=user_agent,
            )
            return device

    def issue_result(self, actor: User, device_id: str) -> dict[str, Any]:
        device = self.get_for_actor(actor, device_id)
        issue = self._storage.get_issue(device.id)
        if issue is None or not issue.config_encrypted:
            raise not_found("Результат выпуска недоступен — выпусти конфиг заново")
        now = self._clock()
        if issue.expires_at <= now:
            self._storage.drop_issue(device.id)
            raise AppError(
                ErrorCode.ISSUE_RESULT_EXPIRED,
                "Срок действия истёк — выпусти конфиг заново",
                status=404,
            )
        if issue.consumed_at is None:
            issue.consumed_at = now  # только аудит, повторные чтения разрешены
        return {
            "device_id": device.id,
            "config": self._secret_box.decrypt(issue.config_encrypted),
            "vpn_url": (
                self._secret_box.decrypt(issue.vpn_url_encrypted)
                if issue.vpn_url_encrypted
                else None
            ),
            "expires_at": issue.expires_at,
        }

    def _enforce_limit(self, user: User) -> None:
        # unlimited=True или limit=None означают «без лимита».
        if user.device_limit_unlimited or user.device_limit is None:
            return
        used = self._storage.count_devices_toward_limit(user.id)
        if used >= user.device_limit:
            raise AppError(
                ErrorCode.DEVICE_LIMIT_REACHED,
                "Лимит устройств закончился",
                status=409,
                details={"used": used, "limit": user.device_limit},
            )
