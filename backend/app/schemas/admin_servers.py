from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.models import ServerNode, ServerStatus


class AdminServerOut(BaseModel):
    id: str
    name: str
    public_host: str
    public_port: int | None = None
    region_note: str | None = None
    provider: str | None = None
    agent_base_url: str
    agent_key_id: str | None = None
    has_agent_secret: bool
    agent_allowed_ip_note: str | None = None
    status: ServerStatus
    last_seen_at: datetime | None = None
    last_error: str | None = None
    last_status_payload: dict[str, Any] | None = None
    awg_container_name: str
    awg_interface: str
    awg_config_path: str
    clients_table_path: str
    is_available_for_new_devices: bool
    active_device_count: int = 0
    created_at: datetime

    @classmethod
    def from_domain(cls, node: ServerNode, active_device_count: int = 0) -> AdminServerOut:
        return cls(
            id=node.id,
            name=node.name,
            public_host=node.public_host,
            public_port=node.public_port,
            region_note=node.region_note,
            provider=node.provider,
            agent_base_url=node.agent_base_url,
            agent_key_id=node.agent_key_id,
            has_agent_secret=node.agent_secret_encrypted is not None,
            agent_allowed_ip_note=node.agent_allowed_ip_note,
            status=node.status,
            last_seen_at=node.last_seen_at,
            last_error=node.last_error,
            last_status_payload=node.last_status_payload,
            awg_container_name=node.awg_container_name,
            awg_interface=node.awg_interface,
            awg_config_path=node.awg_config_path,
            clients_table_path=node.clients_table_path,
            is_available_for_new_devices=node.is_available_for_new_devices,
            active_device_count=active_device_count,
            created_at=node.created_at,
        )


class AdminServerCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    public_host: str = Field(min_length=1, max_length=255)
    agent_base_url: str = Field(min_length=1, max_length=255)
    public_port: int | None = Field(default=None, ge=1, le=65535)
    region_note: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=100)
    agent_key_id: str | None = Field(default=None, max_length=100)
    agent_secret: str | None = Field(default=None, max_length=500)
    agent_allowed_ip_note: str | None = Field(default=None, max_length=200)
    is_available_for_new_devices: bool = True


class AdminServerUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    public_host: str | None = Field(default=None, min_length=1, max_length=255)
    agent_base_url: str | None = Field(default=None, min_length=1, max_length=255)
    public_port: int | None = Field(default=None, ge=1, le=65535)
    region_note: str | None = Field(default=None, max_length=200)
    provider: str | None = Field(default=None, max_length=100)
    agent_key_id: str | None = Field(default=None, max_length=100)
    agent_secret: str | None = Field(default=None, max_length=500)
    agent_allowed_ip_note: str | None = Field(default=None, max_length=200)
    is_available_for_new_devices: bool | None = None
    awg_container_name: str | None = Field(default=None, max_length=100)
    awg_interface: str | None = Field(default=None, max_length=50)
    awg_config_path: str | None = Field(default=None, max_length=255)
    clients_table_path: str | None = Field(default=None, max_length=255)


class AgentPeerOut(BaseModel):
    """PeerView агента; latest_handshake/transfer_* — человекочитаемые метки."""

    public_key: str
    name: str | None = None
    allowed_ips_config: list[str] | None = None
    allowed_ips_runtime: list[str] | None = None
    in_config: bool = False
    in_runtime: bool = False
    in_clients_table: bool = False
    endpoint: str | None = None
    latest_handshake: str | None = None
    transfer_received: str | None = None
    transfer_sent: str | None = None
    user_data: dict[str, Any] | None = None
