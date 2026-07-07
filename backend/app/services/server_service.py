"""VPS-узлы: инвентарь, здоровье, выбор узла для новых устройств."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.core.errors import AppError, ErrorCode, not_found
from app.core.security import SecretBox
from app.domain.models import ServerNode, ServerStatus, SetupJob, User
from app.services.agent_client import AgentClient
from app.services.audit_service import AuditService
from app.storage.memory import InMemoryStorage

# Статусы, при которых узел годится для выпуска новых устройств.
_SELECTABLE_STATUSES = {ServerStatus.ONLINE, ServerStatus.WARNING}

_PATCHABLE_FIELDS = {
    "name",
    "public_host",
    "public_port",
    "region_note",
    "provider",
    "agent_base_url",
    "agent_key_id",
    "agent_allowed_ip_note",
    "is_available_for_new_devices",
    "awg_container_name",
    "awg_interface",
    "awg_config_path",
    "clients_table_path",
}


class ServerService:
    def __init__(
        self,
        storage: InMemoryStorage,
        agent: AgentClient,
        secret_box: SecretBox,
        audit: AuditService,
        clock: Callable[[], datetime],
    ) -> None:
        self._storage = storage
        self._agent = agent
        self._secret_box = secret_box
        self._audit = audit
        self._clock = clock

    def get(self, node_id: str) -> ServerNode:
        node = self._storage.get_server_node(node_id)
        if node is None:
            raise not_found("Сервер не найден")
        return node

    def list_all(self) -> list[ServerNode]:
        return self._storage.list_server_nodes()

    def list_available(self) -> list[ServerNode]:
        return [
            node
            for node in self._storage.list_server_nodes()
            if node.is_available_for_new_devices and node.status in _SELECTABLE_STATUSES
        ]

    def pick_for_new_device(self) -> ServerNode | None:
        """Наименее загруженный из доступных узлов."""
        candidates = self.list_available()
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda n: self._storage.count_active_devices_for_server(n.id),
        )

    def ensure_selectable(self, node: ServerNode) -> None:
        if not node.is_available_for_new_devices or node.status not in _SELECTABLE_STATUSES:
            raise AppError(
                ErrorCode.SERVER_UNAVAILABLE,
                "Этот сервер сейчас недоступен для новых устройств",
                status=503,
            )

    def create_manual(
        self,
        actor: User,
        *,
        name: str,
        public_host: str,
        agent_base_url: str,
        public_port: int | None = None,
        region_note: str | None = None,
        provider: str | None = None,
        agent_key_id: str | None = None,
        agent_secret: str | None = None,
        agent_allowed_ip_note: str | None = None,
        is_available_for_new_devices: bool = True,
    ) -> ServerNode:
        """Ручное добавление узла, где агент уже развёрнут.

        Узел создаётся в статусе draft: до первого успешного health-check
        он не участвует в выпуске устройств.
        """
        now = self._clock()
        node = ServerNode(
            id=str(uuid.uuid4()),
            name=name.strip(),
            public_host=public_host.strip(),
            agent_base_url=agent_base_url.strip().rstrip("/"),
            created_at=now,
            updated_at=now,
            public_port=public_port,
            region_note=region_note,
            provider=provider,
            agent_key_id=agent_key_id,
            agent_secret_encrypted=(
                self._secret_box.encrypt(agent_secret) if agent_secret else None
            ),
            agent_allowed_ip_note=agent_allowed_ip_note,
            is_available_for_new_devices=is_available_for_new_devices,
            created_by_user_id=actor.id,
        )
        self._storage.add_server_node(node)
        self._audit.log(
            "server_created",
            actor_user_id=actor.id,
            target_type="server_node",
            target_id=node.id,
            metadata={"name": node.name},
        )
        return node

    def create_from_setup(
        self, job: SetupJob, *, agent_base_url: str, agent_key_id: str, agent_secret: str
    ) -> ServerNode:
        """Узел из успешной setup-джобы; воркер затем прогоняет health-check."""
        now = self._clock()
        node = ServerNode(
            id=str(uuid.uuid4()),
            name=job.server_name,
            public_host=job.host,
            agent_base_url=agent_base_url,
            created_at=now,
            updated_at=now,
            region_note=job.region_note,
            agent_key_id=agent_key_id,
            agent_secret_encrypted=self._secret_box.encrypt(agent_secret),
            status=ServerStatus.SETUP_RUNNING,
            is_available_for_new_devices=job.available_for_new_devices,
            created_by_user_id=job.created_by_user_id,
        )
        self._storage.add_server_node(node)
        return node

    def update(self, actor: User, node_id: str, patch: dict[str, Any]) -> ServerNode:
        node = self.get(node_id)
        changed = []
        for field_name, value in patch.items():
            if field_name == "agent_secret":
                node.agent_secret_encrypted = (
                    self._secret_box.encrypt(value) if value else None
                )
                changed.append("agent_secret")
                continue
            if field_name not in _PATCHABLE_FIELDS:
                continue
            if getattr(node, field_name) != value:
                setattr(node, field_name, value)
                changed.append(field_name)
        if changed:
            node.updated_at = self._clock()
            self._audit.log(
                "server_updated",
                actor_user_id=actor.id,
                target_type="server_node",
                target_id=node.id,
                metadata={"changed": changed},
            )
        return node

    def set_disabled(self, actor: User, node_id: str, disabled: bool) -> ServerNode:
        node = self.get(node_id)
        now = self._clock()
        if disabled:
            node.status = ServerStatus.DISABLED
        elif node.status == ServerStatus.DISABLED:
            # После включения статус неизвестен до health-check.
            node.status = ServerStatus.DRAFT
        node.updated_at = now
        self._audit.log(
            "server_disabled" if disabled else "server_enabled",
            actor_user_id=actor.id,
            target_type="server_node",
            target_id=node.id,
        )
        return node

    async def health_check(
        self, node_id: str, *, actor_user_id: str | None = None
    ) -> ServerNode:
        node = self.get(node_id)
        previous_status = node.status
        now = self._clock()
        try:
            await self._agent.health(node)
            status_payload = await self._agent.status(node)
        except AppError as exc:
            if exc.code == ErrorCode.SECRET_REQUIRED:
                raise
            if node.status != ServerStatus.DISABLED:
                node.status = ServerStatus.OFFLINE
            node.last_error = exc.message
            node.updated_at = now
            self._audit.log(
                "agent_call_failed",
                actor_user_id=actor_user_id,
                target_type="server_node",
                target_id=node.id,
                metadata={"code": exc.code.value, "details": exc.details},
            )
            return node

        node.last_seen_at = now
        node.last_status_payload = status_payload
        node.last_error = None
        if node.status != ServerStatus.DISABLED:
            warnings = status_payload.get("warnings") or []
            running = bool(status_payload.get("container_running"))
            node.status = (
                ServerStatus.ONLINE if running and not warnings else ServerStatus.WARNING
            )
        node.updated_at = now
        if node.status != previous_status:
            self._audit.log(
                "server_status_changed",
                actor_user_id=actor_user_id,
                target_type="server_node",
                target_id=node.id,
                metadata={"from": previous_status.value, "to": node.status.value},
            )
        return node

    async def agent_peers(self, node_id: str) -> list[dict[str, Any]]:
        return await self._agent.peers(self.get(node_id))
