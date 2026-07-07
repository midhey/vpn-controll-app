from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.domain.models import AuthMethod, EventLevel, SetupJob, SetupJobEvent, SetupJobStatus


class SetupJobCreateIn(BaseModel):
    server_name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=255)
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_username: str = Field(default="root", min_length=1, max_length=64)
    auth_method: AuthMethod
    secret: str = Field(min_length=1, max_length=10_000)  # SSH-ключ или пароль
    region_note: str | None = Field(default=None, max_length=200)
    install_awg: bool = True
    available_for_new_devices: bool = True
    verify_before_install: bool = True


class SetupJobOut(BaseModel):
    """Секрет наружу не отдаётся никогда."""

    id: str
    status: SetupJobStatus
    current_step: str
    server_name: str
    host: str
    ssh_port: int
    ssh_username: str
    auth_method: AuthMethod
    region_note: str | None = None
    install_awg: bool
    available_for_new_devices: bool
    verify_before_install: bool
    error_message: str | None = None
    server_node_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def from_domain(cls, job: SetupJob) -> SetupJobOut:
        return cls(
            id=job.id,
            status=job.status,
            current_step=job.current_step,
            server_name=job.server_name,
            host=job.host,
            ssh_port=job.ssh_port,
            ssh_username=job.ssh_username,
            auth_method=job.auth_method,
            region_note=job.region_note,
            install_awg=job.install_awg,
            available_for_new_devices=job.available_for_new_devices,
            verify_before_install=job.verify_before_install,
            error_message=job.error_message,
            server_node_id=job.server_node_id,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class SetupJobEventOut(BaseModel):
    level: EventLevel
    step: str
    message: str
    metadata: dict[str, Any] = {}
    created_at: datetime

    @classmethod
    def from_domain(cls, event: SetupJobEvent) -> SetupJobEventOut:
        return cls(
            level=event.level,
            step=event.step,
            message=event.message,
            metadata=event.metadata,
            created_at=event.created_at,
        )
