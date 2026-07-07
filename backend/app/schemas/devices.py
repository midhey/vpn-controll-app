from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.models import Device, DeviceStatus


class DeviceOut(BaseModel):
    id: str
    name: str
    status: DeviceStatus
    server_node_id: str
    server_name: str | None = None
    client_ip: str | None = None
    public_key: str | None = None
    created_at: datetime
    last_config_issued_at: datetime | None = None
    last_handshake_at: datetime | None = None
    transfer_received_label: str | None = None
    transfer_sent_label: str | None = None
    revoked_at: datetime | None = None
    failure_message: str | None = None

    @classmethod
    def from_domain(cls, device: Device, server_name: str | None = None) -> DeviceOut:
        return cls(
            id=device.id,
            name=device.name,
            status=device.status,
            server_node_id=device.server_node_id,
            server_name=server_name,
            client_ip=device.client_ip,
            public_key=device.public_key,
            created_at=device.created_at,
            last_config_issued_at=device.last_config_issued_at,
            last_handshake_at=device.last_handshake_at,
            transfer_received_label=device.transfer_received_label,
            transfer_sent_label=device.transfer_sent_label,
            revoked_at=device.revoked_at,
            failure_message=device.failure_message,
        )


class DeviceCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    server_node_id: str | None = None


class IssueResultOut(BaseModel):
    device_id: str
    config: str
    vpn_url: str | None = None
    expires_at: datetime


class DeviceCreateOut(BaseModel):
    device: DeviceOut
    issue_result: IssueResultOut
