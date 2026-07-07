"""Доменные модели.

Обычные dataclass'ы: поля повторяют таблицы из плана один-в-один, чтобы
при подключении PostgreSQL они переехали в SQLAlchemy-модели без переименований.
Все datetime — timezone-aware UTC (в БД станут timestamptz).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class DeviceStatus(str, Enum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"
    REVOKED = "revoked"
    FAILED = "failed"


class ServerStatus(str, Enum):
    DRAFT = "draft"
    SETUP_PENDING = "setup_pending"
    SETUP_RUNNING = "setup_running"
    ONLINE = "online"
    WARNING = "warning"
    OFFLINE = "offline"
    DISABLED = "disabled"
    SETUP_FAILED = "setup_failed"


class SetupJobStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    CHECKING_SSH = "checking_ssh"
    INSTALLING_AGENT = "installing_agent"
    INSTALLING_VPN = "installing_vpn"
    VERIFYING = "verifying"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self in {self.SUCCESS, self.FAILED, self.CANCELLED}


class AuthMethod(str, Enum):
    SSH_KEY = "ssh_key"
    PASSWORD = "password"


class EventLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(slots=True)
class User:
    id: str
    login: str  # хранится в нижнем регистре
    display_name: str
    role: UserRole
    password_hash: str
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    telegram_username: str | None = None
    # Лимит устройств: unlimited=True или limit=None означают «без лимита».
    device_limit: int | None = 3
    device_limit_unlimited: bool = False
    show_server_support: bool = True
    free_access: bool = False
    note: str | None = None
    created_by_user_id: str | None = None


@dataclass(slots=True)
class Session:
    id: str
    user_id: str
    token_hash: str
    created_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    user_agent: str | None = None
    ip_address: str | None = None
    revoked_at: datetime | None = None


@dataclass(slots=True)
class ServerNode:
    id: str
    name: str
    public_host: str
    agent_base_url: str
    created_at: datetime
    updated_at: datetime
    public_port: int | None = None
    region_note: str | None = None
    provider: str | None = None
    agent_key_id: str | None = None
    agent_secret_encrypted: str | None = None
    agent_allowed_ip_note: str | None = None
    status: ServerStatus = ServerStatus.DRAFT
    last_seen_at: datetime | None = None
    last_error: str | None = None
    last_status_payload: dict[str, Any] | None = None
    # Информационные поля: агент читает их из своего окружения на узле,
    # правка здесь узел не переконфигурирует.
    awg_container_name: str = "amnezia-awg2"
    awg_interface: str = "awg0"
    awg_config_path: str = "/opt/amnezia/awg/awg0.conf"
    clients_table_path: str = "/opt/amnezia/awg/clientsTable"
    is_available_for_new_devices: bool = True
    created_by_user_id: str | None = None


@dataclass(slots=True)
class Device:
    id: str
    user_id: str
    server_node_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    status: DeviceStatus = DeviceStatus.PROVISIONING
    public_key: str | None = None
    client_ip: str | None = None
    last_config_issued_at: datetime | None = None
    last_handshake_at: datetime | None = None
    transfer_received_label: str | None = None
    transfer_sent_label: str | None = None
    last_agent_sync_at: datetime | None = None
    revoked_at: datetime | None = None
    failure_message: str | None = None


@dataclass(slots=True)
class DeviceConfigIssue:
    """Одноразовый (по TTL) результат выпуска конфига: читается многократно
    до expires_at, потом недоступен — только перевыпуск."""

    id: str
    device_id: str
    issued_to_user_id: str
    created_at: datetime
    expires_at: datetime
    config_encrypted: str | None = None
    vpn_url_encrypted: str | None = None
    consumed_at: datetime | None = None  # первое чтение, только для аудита


@dataclass(slots=True)
class SupportContribution:
    id: str
    user_id: str
    amount: float  # в БД станет numeric(10, 2)
    currency: str
    recorded_by_user_id: str
    recorded_at: datetime
    created_at: datetime
    period_label: str | None = None
    comment: str | None = None


@dataclass(slots=True)
class SupportSettings:
    """Глобальные настройки «поддержки сервера» (синглтон)."""

    title: str = "Поддержка сервера"
    description: str = "Если хочется — можно поддержать VPS. Это добровольно и ни на что не влияет."
    sbp_phone: str | None = None
    bank_name: str | None = None
    extra_contact: str | None = None
    monthly_cost_amount: float | None = None
    reserve_amount: float | None = None
    is_enabled: bool = False
    updated_by_user_id: str | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class SetupJob:
    id: str
    created_by_user_id: str
    server_name: str
    host: str
    ssh_port: int
    ssh_username: str
    auth_method: AuthMethod
    created_at: datetime
    updated_at: datetime
    status: SetupJobStatus = SetupJobStatus.QUEUED
    # SSH-ключ/пароль, зашифрованные SecretBox; очищается на терминальном статусе.
    secret_encrypted: str | None = None
    region_note: str | None = None
    install_awg: bool = True
    available_for_new_devices: bool = True
    verify_before_install: bool = True
    current_step: str = "queued"
    error_message: str | None = None
    result_payload: dict[str, Any] | None = None
    server_node_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(slots=True)
class SetupJobEvent:
    id: str
    setup_job_id: str
    level: EventLevel
    step: str
    message: str
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AuditLogEntry:
    id: str
    action: str
    created_at: datetime
    actor_user_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    ip_address: str | None = None
    user_agent: str | None = None
