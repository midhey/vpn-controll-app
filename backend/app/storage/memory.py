"""Хранилище в памяти.

Единственная точка, которую заменит PostgreSQL: сервисы ходят только через
методы этого класса, поэтому переход на SQLAlchemy — замена реализации методов,
а не переписывание сервисов. Данные живут до перезапуска процесса.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from typing import Any

from app.domain.models import (
    AuditLogEntry,
    Device,
    DeviceConfigIssue,
    DeviceStatus,
    ServerNode,
    Session,
    SetupJob,
    SetupJobEvent,
    SetupJobStatus,
    SupportContribution,
    SupportSettings,
    User,
)


class InMemoryStorage:
    def __init__(self) -> None:
        # Один лок на связки «проверил — изменил», растянутые через await
        # (выпуск устройства, взятие setup-джобы воркером).
        self.lock = asyncio.Lock()
        self._users: dict[str, User] = {}
        self._sessions: dict[str, Session] = {}  # ключ — token_hash
        self._server_nodes: dict[str, ServerNode] = {}
        self._devices: dict[str, Device] = {}
        self._issues: dict[str, DeviceConfigIssue] = {}  # ключ — device_id, живёт последний
        self._contributions: list[SupportContribution] = []
        self.support_settings = SupportSettings()
        self._setup_jobs: dict[str, SetupJob] = {}
        self._setup_events: dict[str, list[SetupJobEvent]] = {}
        self._setup_jobs_guard = threading.Lock()
        self._audit: list[AuditLogEntry] = []
        self._login_failures: dict[str, list[datetime]] = {}

    # --- users ---

    def add_user(self, user: User) -> None:
        self._users[user.id] = user

    def save_user(self, user: User) -> None:
        self._users[user.id] = user

    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def get_user_by_login(self, login: str) -> User | None:
        normalized = login.strip().lower()
        for user in self._users.values():
            if user.login == normalized:
                return user
        return None

    def list_users(self) -> list[User]:
        return sorted(self._users.values(), key=lambda u: u.created_at)

    def has_admin(self) -> bool:
        return any(u.role.value == "admin" for u in self._users.values())

    # --- sessions ---

    def add_session(self, session: Session) -> None:
        self._sessions[session.token_hash] = session

    def save_session(self, session: Session) -> None:
        self._sessions[session.token_hash] = session

    def get_session_by_token_hash(self, token_hash: str) -> Session | None:
        return self._sessions.get(token_hash)

    def revoke_sessions_for_user(self, user_id: str, at: datetime) -> None:
        for session in self._sessions.values():
            if session.user_id == user_id and session.revoked_at is None:
                session.revoked_at = at

    # --- server nodes ---

    def add_server_node(self, node: ServerNode) -> None:
        self._server_nodes[node.id] = node

    def save_server_node(self, node: ServerNode) -> None:
        self._server_nodes[node.id] = node

    def get_server_node(self, node_id: str) -> ServerNode | None:
        return self._server_nodes.get(node_id)

    def list_server_nodes(self) -> list[ServerNode]:
        return sorted(self._server_nodes.values(), key=lambda n: n.created_at)

    # --- devices ---

    def add_device(self, device: Device) -> None:
        self._devices[device.id] = device

    def save_device(self, device: Device) -> None:
        self._devices[device.id] = device

    def get_device(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def list_devices_for_user(self, user_id: str) -> list[Device]:
        return sorted(
            (d for d in self._devices.values() if d.user_id == user_id),
            key=lambda d: d.created_at,
            reverse=True,
        )

    def count_devices_toward_limit(self, user_id: str) -> int:
        """Считаем provisioning + active; revoked/failed лимит не занимают."""
        counted = {DeviceStatus.PROVISIONING, DeviceStatus.ACTIVE}
        return sum(
            1
            for d in self._devices.values()
            if d.user_id == user_id and d.status in counted
        )

    def count_active_devices_for_server(self, server_node_id: str) -> int:
        counted = {DeviceStatus.PROVISIONING, DeviceStatus.ACTIVE}
        return sum(
            1
            for d in self._devices.values()
            if d.server_node_id == server_node_id and d.status in counted
        )

    # --- device config issues ---

    def set_issue(self, issue: DeviceConfigIssue) -> None:
        self._issues[issue.device_id] = issue

    def save_issue(self, issue: DeviceConfigIssue) -> None:
        self._issues[issue.device_id] = issue

    def get_issue(self, device_id: str) -> DeviceConfigIssue | None:
        return self._issues.get(device_id)

    def drop_issue(self, device_id: str) -> None:
        self._issues.pop(device_id, None)

    # --- support ---

    def add_contribution(self, contribution: SupportContribution) -> None:
        self._contributions.append(contribution)

    def get_support_settings(self) -> SupportSettings:
        return self.support_settings

    def save_support_settings(self, settings: SupportSettings) -> None:
        self.support_settings = settings

    def list_contributions_for_user(self, user_id: str) -> list[SupportContribution]:
        return sorted(
            (c for c in self._contributions if c.user_id == user_id),
            key=lambda c: c.recorded_at,
            reverse=True,
        )

    # --- setup jobs ---

    def add_setup_job(self, job: SetupJob) -> None:
        self._setup_jobs[job.id] = job
        self._setup_events.setdefault(job.id, [])

    def save_setup_job(self, job: SetupJob) -> None:
        self._setup_jobs[job.id] = job
        self._setup_events.setdefault(job.id, [])

    def get_setup_job(self, job_id: str) -> SetupJob | None:
        return self._setup_jobs.get(job_id)

    def list_setup_jobs(self) -> list[SetupJob]:
        return sorted(self._setup_jobs.values(), key=lambda j: j.created_at, reverse=True)

    def _next_queued_setup_job(self) -> SetupJob | None:
        queued = [j for j in self._setup_jobs.values() if j.status == SetupJobStatus.QUEUED]
        queued.sort(key=lambda j: j.created_at)
        return queued[0] if queued else None

    def claim_next_setup_job(self, at: datetime, current_step: str) -> SetupJob | None:
        with self._setup_jobs_guard:
            job = self._next_queued_setup_job()
            if job is None:
                return None
            job.status = SetupJobStatus.CHECKING_SSH
            job.current_step = current_step
            job.started_at = at
            job.updated_at = at
            self.save_setup_job(job)
            return job

    def transition_setup_job(
        self,
        job_id: str,
        expected_statuses: set[SetupJobStatus],
        values: dict[str, Any],
    ) -> SetupJob | None:
        with self._setup_jobs_guard:
            job = self._setup_jobs.get(job_id)
            if job is None or job.status not in expected_statuses:
                return None
            for field_name, value in values.items():
                setattr(job, field_name, value)
            self.save_setup_job(job)
            return job

    def add_setup_event(self, event: SetupJobEvent) -> None:
        self._setup_events.setdefault(event.setup_job_id, []).append(event)

    def list_setup_events(self, job_id: str) -> list[SetupJobEvent]:
        return list(self._setup_events.get(job_id, []))

    # --- audit ---

    def add_audit_entry(self, entry: AuditLogEntry) -> None:
        self._audit.append(entry)

    def list_audit_entries(self, limit: int) -> list[AuditLogEntry]:
        return list(reversed(self._audit[-limit:]))

    # --- login rate limit ---

    def record_login_failure(self, key: str, at: datetime) -> None:
        self._login_failures.setdefault(key, []).append(at)

    def count_login_failures(self, key: str, since: datetime) -> int:
        attempts = self._login_failures.get(key, [])
        fresh = [a for a in attempts if a >= since]
        self._login_failures[key] = fresh  # заодно чистим старое
        return len(fresh)

    def clear_login_failures(self, key: str) -> None:
        self._login_failures.pop(key, None)
