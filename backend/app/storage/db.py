from __future__ import annotations

import asyncio
from dataclasses import fields
from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select

from app.db.models import (
    AuditLogEntryRow,
    DeviceConfigIssueRow,
    DeviceRow,
    LoginFailureRow,
    ServerNodeRow,
    SessionRow,
    SetupJobEventRow,
    SetupJobRow,
    SupportContributionRow,
    SupportSettingsRow,
    UserRow,
)
from app.db.session import Database
from app.domain.models import (
    AuditLogEntry,
    AuthMethod,
    Device,
    DeviceConfigIssue,
    DeviceStatus,
    EventLevel,
    ServerNode,
    ServerStatus,
    Session,
    SetupJob,
    SetupJobEvent,
    SetupJobStatus,
    SupportContribution,
    SupportSettings,
    User,
    UserRole,
)


class DatabaseStorage:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.lock = asyncio.Lock()

    # --- users ---

    def add_user(self, user: User) -> None:
        self.save_user(user)

    def save_user(self, user: User) -> None:
        with self.database.session() as session:
            session.merge(_user_row(user))

    def get_user(self, user_id: str) -> User | None:
        with self.database.session() as session:
            row = session.get(UserRow, user_id)
            return _user(row) if row else None

    def get_user_by_login(self, login: str) -> User | None:
        normalized = login.strip().lower()
        with self.database.session() as session:
            row = session.scalar(select(UserRow).where(UserRow.login == normalized))
            return _user(row) if row else None

    def list_users(self) -> list[User]:
        with self.database.session() as session:
            rows = session.scalars(select(UserRow).order_by(UserRow.created_at)).all()
            return [_user(row) for row in rows]

    def has_admin(self) -> bool:
        with self.database.session() as session:
            count = session.scalar(
                select(func.count()).select_from(UserRow).where(UserRow.role == "admin")
            )
            return bool(count)

    # --- sessions ---

    def add_session(self, session: Session) -> None:
        self.save_session(session)

    def save_session(self, item: Session) -> None:
        with self.database.session() as session:
            session.merge(_session_row(item))

    def get_session_by_token_hash(self, token_hash: str) -> Session | None:
        with self.database.session() as session:
            row = session.scalar(select(SessionRow).where(SessionRow.token_hash == token_hash))
            return _session(row) if row else None

    def revoke_sessions_for_user(self, user_id: str, at: datetime) -> None:
        with self.database.session() as session:
            rows = session.scalars(
                select(SessionRow).where(
                    SessionRow.user_id == user_id,
                    SessionRow.revoked_at.is_(None),
                )
            ).all()
            for row in rows:
                row.revoked_at = at

    # --- server nodes ---

    def add_server_node(self, node: ServerNode) -> None:
        self.save_server_node(node)

    def save_server_node(self, node: ServerNode) -> None:
        with self.database.session() as session:
            session.merge(_server_node_row(node))

    def get_server_node(self, node_id: str) -> ServerNode | None:
        with self.database.session() as session:
            row = session.get(ServerNodeRow, node_id)
            return _server_node(row) if row else None

    def list_server_nodes(self) -> list[ServerNode]:
        with self.database.session() as session:
            rows = session.scalars(
                select(ServerNodeRow).order_by(ServerNodeRow.created_at)
            ).all()
            return [_server_node(row) for row in rows]

    # --- devices ---

    def add_device(self, device: Device) -> None:
        self.save_device(device)

    def save_device(self, device: Device) -> None:
        with self.database.session() as session:
            session.merge(_device_row(device))

    def get_device(self, device_id: str) -> Device | None:
        with self.database.session() as session:
            row = session.get(DeviceRow, device_id)
            return _device(row) if row else None

    def list_devices_for_user(self, user_id: str) -> list[Device]:
        with self.database.session() as session:
            rows = session.scalars(
                select(DeviceRow)
                .where(DeviceRow.user_id == user_id)
                .order_by(DeviceRow.created_at.desc())
            ).all()
            return [_device(row) for row in rows]

    def count_devices_toward_limit(self, user_id: str) -> int:
        counted = [DeviceStatus.PROVISIONING.value, DeviceStatus.ACTIVE.value]
        with self.database.session() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(DeviceRow)
                    .where(DeviceRow.user_id == user_id, DeviceRow.status.in_(counted))
                )
                or 0
            )

    def count_active_devices_for_server(self, server_node_id: str) -> int:
        counted = [DeviceStatus.PROVISIONING.value, DeviceStatus.ACTIVE.value]
        with self.database.session() as session:
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(DeviceRow)
                    .where(
                        DeviceRow.server_node_id == server_node_id,
                        DeviceRow.status.in_(counted),
                    )
                )
                or 0
            )

    # --- device config issues ---

    def set_issue(self, issue: DeviceConfigIssue) -> None:
        self.save_issue(issue)

    def save_issue(self, issue: DeviceConfigIssue) -> None:
        with self.database.session() as session:
            old = session.scalar(
                select(DeviceConfigIssueRow).where(
                    DeviceConfigIssueRow.device_id == issue.device_id
                )
            )
            if old and old.id != issue.id:
                session.delete(old)
                session.flush()
            session.merge(_issue_row(issue))

    def get_issue(self, device_id: str) -> DeviceConfigIssue | None:
        with self.database.session() as session:
            row = session.scalar(
                select(DeviceConfigIssueRow).where(DeviceConfigIssueRow.device_id == device_id)
            )
            return _issue(row) if row else None

    def drop_issue(self, device_id: str) -> None:
        with self.database.session() as session:
            session.execute(
                delete(DeviceConfigIssueRow).where(
                    DeviceConfigIssueRow.device_id == device_id
                )
            )

    # --- support ---

    @property
    def support_settings(self) -> SupportSettings:
        return self.get_support_settings()

    def get_support_settings(self) -> SupportSettings:
        with self.database.session() as session:
            row = _ensure_support_settings_row(session)
            return _support_settings(row)

    def save_support_settings(self, settings: SupportSettings) -> None:
        with self.database.session() as session:
            session.merge(_support_settings_row(settings))

    def add_contribution(self, contribution: SupportContribution) -> None:
        with self.database.session() as session:
            session.merge(_contribution_row(contribution))

    def list_contributions_for_user(self, user_id: str) -> list[SupportContribution]:
        with self.database.session() as session:
            rows = session.scalars(
                select(SupportContributionRow)
                .where(SupportContributionRow.user_id == user_id)
                .order_by(SupportContributionRow.recorded_at.desc())
            ).all()
            return [_contribution(row) for row in rows]

    # --- setup jobs ---

    def add_setup_job(self, job: SetupJob) -> None:
        self.save_setup_job(job)

    def save_setup_job(self, job: SetupJob) -> None:
        with self.database.session() as session:
            session.merge(_setup_job_row(job))

    def get_setup_job(self, job_id: str) -> SetupJob | None:
        with self.database.session() as session:
            row = session.get(SetupJobRow, job_id)
            return _setup_job(row) if row else None

    def list_setup_jobs(self) -> list[SetupJob]:
        with self.database.session() as session:
            rows = session.scalars(
                select(SetupJobRow).order_by(SetupJobRow.created_at.desc())
            ).all()
            return [_setup_job(row) for row in rows]

    def next_queued_setup_job(self) -> SetupJob | None:
        with self.database.session() as session:
            row = session.scalar(
                select(SetupJobRow)
                .where(SetupJobRow.status == SetupJobStatus.QUEUED.value)
                .order_by(SetupJobRow.created_at)
                .limit(1)
            )
            return _setup_job(row) if row else None

    def add_setup_event(self, event: SetupJobEvent) -> None:
        with self.database.session() as session:
            session.merge(_setup_event_row(event))

    def list_setup_events(self, job_id: str) -> list[SetupJobEvent]:
        with self.database.session() as session:
            rows = session.scalars(
                select(SetupJobEventRow)
                .where(SetupJobEventRow.setup_job_id == job_id)
                .order_by(SetupJobEventRow.created_at)
            ).all()
            return [_setup_event(row) for row in rows]

    # --- audit ---

    def add_audit_entry(self, entry: AuditLogEntry) -> None:
        with self.database.session() as session:
            session.merge(_audit_row(entry))

    def list_audit_entries(self, limit: int) -> list[AuditLogEntry]:
        with self.database.session() as session:
            rows = session.scalars(
                select(AuditLogEntryRow)
                .order_by(AuditLogEntryRow.created_at.desc())
                .limit(limit)
            ).all()
            return [_audit(row) for row in rows]

    # --- login rate limit ---

    def record_login_failure(self, key: str, at: datetime) -> None:
        with self.database.session() as session:
            session.add(LoginFailureRow(key=key, attempted_at=at))

    def count_login_failures(self, key: str, since: datetime) -> int:
        with self.database.session() as session:
            session.execute(delete(LoginFailureRow).where(LoginFailureRow.attempted_at < since))
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(LoginFailureRow)
                    .where(LoginFailureRow.key == key)
                )
                or 0
            )

    def clear_login_failures(self, key: str) -> None:
        with self.database.session() as session:
            session.execute(delete(LoginFailureRow).where(LoginFailureRow.key == key))


def _user(row: UserRow) -> User:
    return User(
        id=row.id,
        login=row.login,
        display_name=row.display_name,
        role=UserRole(row.role),
        password_hash=row.password_hash,
        created_at=row.created_at,
        updated_at=row.updated_at,
        is_active=row.is_active,
        telegram_username=row.telegram_username,
        device_limit=row.device_limit,
        device_limit_unlimited=row.device_limit_unlimited,
        show_server_support=row.show_server_support,
        free_access=row.free_access,
        note=row.note,
        created_by_user_id=row.created_by_user_id,
    )


def _user_row(user: User) -> UserRow:
    return UserRow(**{**_dataclass_values(user), "role": user.role.value})


def _session(row: SessionRow) -> Session:
    return Session(**_row_dict(row, SessionRow))


def _session_row(item: Session) -> SessionRow:
    return SessionRow(**_dataclass_values(item))


def _server_node(row: ServerNodeRow) -> ServerNode:
    values = _row_dict(row, ServerNodeRow)
    values["status"] = ServerStatus(values["status"])
    return ServerNode(**values)


def _server_node_row(node: ServerNode) -> ServerNodeRow:
    return ServerNodeRow(**{**_dataclass_values(node), "status": node.status.value})


def _device(row: DeviceRow) -> Device:
    values = _row_dict(row, DeviceRow)
    values["status"] = DeviceStatus(values["status"])
    return Device(**values)


def _device_row(device: Device) -> DeviceRow:
    return DeviceRow(**{**_dataclass_values(device), "status": device.status.value})


def _issue(row: DeviceConfigIssueRow) -> DeviceConfigIssue:
    return DeviceConfigIssue(**_row_dict(row, DeviceConfigIssueRow))


def _issue_row(issue: DeviceConfigIssue) -> DeviceConfigIssueRow:
    return DeviceConfigIssueRow(**_dataclass_values(issue))


def _contribution(row: SupportContributionRow) -> SupportContribution:
    return SupportContribution(**_row_dict(row, SupportContributionRow))


def _contribution_row(item: SupportContribution) -> SupportContributionRow:
    return SupportContributionRow(**_dataclass_values(item))


def _support_settings(row: SupportSettingsRow) -> SupportSettings:
    values = _row_dict(row, SupportSettingsRow)
    values.pop("id", None)
    return SupportSettings(**values)


def _support_settings_row(settings: SupportSettings) -> SupportSettingsRow:
    return SupportSettingsRow(id=1, **_dataclass_values(settings))


def _setup_job(row: SetupJobRow) -> SetupJob:
    values = _row_dict(row, SetupJobRow)
    values["status"] = SetupJobStatus(values["status"])
    values["auth_method"] = AuthMethod(values["auth_method"])
    return SetupJob(**values)


def _setup_job_row(job: SetupJob) -> SetupJobRow:
    values = {
        **_dataclass_values(job),
        "status": job.status.value,
        "auth_method": job.auth_method.value,
    }
    return SetupJobRow(**values)


def _setup_event(row: SetupJobEventRow) -> SetupJobEvent:
    return SetupJobEvent(
        id=row.id,
        setup_job_id=row.setup_job_id,
        level=EventLevel(row.level),
        step=row.step,
        message=row.message,
        created_at=row.created_at,
        metadata=row.event_metadata or {},
    )


def _setup_event_row(event: SetupJobEvent) -> SetupJobEventRow:
    return SetupJobEventRow(
        id=event.id,
        setup_job_id=event.setup_job_id,
        level=event.level.value,
        step=event.step,
        message=event.message,
        created_at=event.created_at,
        event_metadata=event.metadata,
    )


def _audit(row: AuditLogEntryRow) -> AuditLogEntry:
    return AuditLogEntry(
        id=row.id,
        action=row.action,
        created_at=row.created_at,
        actor_user_id=row.actor_user_id,
        target_type=row.target_type,
        target_id=row.target_id,
        metadata=row.entry_metadata or {},
        ip_address=row.ip_address,
        user_agent=row.user_agent,
    )


def _audit_row(entry: AuditLogEntry) -> AuditLogEntryRow:
    return AuditLogEntryRow(
        id=entry.id,
        action=entry.action,
        created_at=entry.created_at,
        actor_user_id=entry.actor_user_id,
        target_type=entry.target_type,
        target_id=entry.target_id,
        entry_metadata=entry.metadata,
        ip_address=entry.ip_address,
        user_agent=entry.user_agent,
    )


def _ensure_support_settings_row(session: Any) -> SupportSettingsRow:
    row = session.get(SupportSettingsRow, 1)
    if row is None:
        row = _support_settings_row(SupportSettings())
        session.add(row)
        session.flush()
    return row


def _row_dict(row: Any, model: type) -> dict[str, Any]:
    return {column.name: getattr(row, column.key) for column in model.__table__.columns}


def _dataclass_values(item: Any) -> dict[str, Any]:
    return {field.name: getattr(item, field.name) for field in fields(item)}
