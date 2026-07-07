"""Задачи установки VPS: очередь, шаги, события.

SSH-секрет хранится только зашифрованным и очищается на терминальном статусе,
поэтому «повторить» завершённую задачу нельзя — создаётся новая (фронт
пересобирает форму). Реальную установку выполняет воркер (пока — заглушка).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.core.errors import AppError, ErrorCode, not_found
from app.core.security import SecretBox
from app.domain.models import (
    AuthMethod,
    EventLevel,
    SetupJob,
    SetupJobEvent,
    SetupJobStatus,
    User,
)
from app.services.audit_service import AuditService
from app.storage.memory import InMemoryStorage

# Человеческие подписи шагов для UI.
STEP_LABELS = {
    SetupJobStatus.QUEUED: "В очереди",
    SetupJobStatus.CHECKING_SSH: "Проверяем SSH-подключение",
    SetupJobStatus.INSTALLING_AGENT: "Устанавливаем агент",
    SetupJobStatus.INSTALLING_VPN: "Устанавливаем VPN",
    SetupJobStatus.VERIFYING: "Проверяем узел",
    SetupJobStatus.SUCCESS: "Готово",
    SetupJobStatus.FAILED: "Ошибка",
    SetupJobStatus.CANCELLED: "Отменено",
}


class SetupJobService:
    def __init__(
        self,
        storage: InMemoryStorage,
        secret_box: SecretBox,
        audit: AuditService,
        clock: Callable[[], datetime],
    ) -> None:
        self._storage = storage
        self._secret_box = secret_box
        self._audit = audit
        self._clock = clock

    def create(
        self,
        actor: User,
        *,
        server_name: str,
        host: str,
        ssh_port: int,
        ssh_username: str,
        auth_method: AuthMethod,
        secret: str,
        region_note: str | None = None,
        install_awg: bool = True,
        available_for_new_devices: bool = True,
        verify_before_install: bool = True,
    ) -> SetupJob:
        if not secret.strip():
            raise AppError(
                ErrorCode.SECRET_REQUIRED,
                "Нужен SSH-ключ или пароль для подключения",
                status=400,
            )
        now = self._clock()
        job = SetupJob(
            id=str(uuid.uuid4()),
            created_by_user_id=actor.id,
            server_name=server_name.strip(),
            host=host.strip(),
            ssh_port=ssh_port,
            ssh_username=ssh_username.strip(),
            auth_method=auth_method,
            created_at=now,
            updated_at=now,
            secret_encrypted=self._secret_box.encrypt(secret),
            region_note=region_note,
            install_awg=install_awg,
            available_for_new_devices=available_for_new_devices,
            verify_before_install=verify_before_install,
            status=SetupJobStatus.QUEUED,
            current_step=STEP_LABELS[SetupJobStatus.QUEUED],
        )
        self._storage.add_setup_job(job)
        self.add_event(job, EventLevel.INFO, "queued", "Задача поставлена в очередь")
        self._audit.log(
            "setup_job_created",
            actor_user_id=actor.id,
            target_type="setup_job",
            target_id=job.id,
            metadata={"server_name": job.server_name, "host": job.host},
        )
        return job

    def get(self, job_id: str) -> SetupJob:
        job = self._storage.get_setup_job(job_id)
        if job is None:
            raise not_found("Задача установки не найдена")
        return job

    def list(self) -> list[SetupJob]:
        return self._storage.list_setup_jobs()

    def events(self, job_id: str) -> list[SetupJobEvent]:
        self.get(job_id)
        return self._storage.list_setup_events(job_id)

    def start(self, actor: User, job_id: str) -> SetupJob:
        """Создание сразу ставит в очередь; start оставлен для draft-задач."""
        job = self.get(job_id)
        if job.status.is_terminal:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Задача уже завершена — создай новую",
                status=409,
            )
        if job.status == SetupJobStatus.DRAFT:
            job.status = SetupJobStatus.QUEUED
            job.current_step = STEP_LABELS[SetupJobStatus.QUEUED]
            job.updated_at = self._clock()
            self._storage.save_setup_job(job)
            self.add_event(job, EventLevel.INFO, "queued", "Задача поставлена в очередь")
        return job

    def cancel(self, actor: User, job_id: str) -> SetupJob:
        job = self.get(job_id)
        if job.status.is_terminal:
            raise AppError(
                ErrorCode.VALIDATION_ERROR, "Задача уже завершена", status=409
            )
        now = self._clock()
        job.status = SetupJobStatus.CANCELLED
        job.current_step = STEP_LABELS[SetupJobStatus.CANCELLED]
        job.finished_at = now
        job.updated_at = now
        job.secret_encrypted = None
        self._storage.save_setup_job(job)
        self.add_event(job, EventLevel.WARNING, "cancelled", "Задача отменена")
        self._audit.log(
            "setup_job_cancelled",
            actor_user_id=actor.id,
            target_type="setup_job",
            target_id=job.id,
        )
        return job

    # --- методы для воркера ---

    def claim_next(self) -> SetupJob | None:
        job = self._storage.next_queued_setup_job()
        if job is not None:
            job.started_at = self._clock()
            self._storage.save_setup_job(job)
        return job

    def is_cancelled(self, job_id: str) -> bool:
        job = self._storage.get_setup_job(job_id)
        return job is None or job.status == SetupJobStatus.CANCELLED

    def set_step(self, job: SetupJob, status: SetupJobStatus, message: str) -> None:
        job.status = status
        job.current_step = STEP_LABELS[status]
        job.updated_at = self._clock()
        self._storage.save_setup_job(job)
        self.add_event(job, EventLevel.INFO, status.value, message)

    def add_event(
        self,
        job: SetupJob,
        level: EventLevel,
        step: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._storage.add_setup_event(
            SetupJobEvent(
                id=str(uuid.uuid4()),
                setup_job_id=job.id,
                level=level,
                step=step,
                message=message,
                created_at=self._clock(),
                metadata=metadata or {},
            )
        )

    def finish_success(self, job: SetupJob, server_node_id: str) -> None:
        now = self._clock()
        job.status = SetupJobStatus.SUCCESS
        job.current_step = STEP_LABELS[SetupJobStatus.SUCCESS]
        job.server_node_id = server_node_id
        job.finished_at = now
        job.updated_at = now
        job.secret_encrypted = None
        job.result_payload = {"server_node_id": server_node_id}
        self._storage.save_setup_job(job)
        self.add_event(job, EventLevel.INFO, "success", "Узел установлен и подключён")
        self._audit.log(
            "setup_job_succeeded",
            target_type="setup_job",
            target_id=job.id,
            metadata={"server_node_id": server_node_id},
        )

    def finish_failed(self, job: SetupJob, error_message: str) -> None:
        now = self._clock()
        job.status = SetupJobStatus.FAILED
        job.current_step = STEP_LABELS[SetupJobStatus.FAILED]
        job.error_message = error_message
        job.finished_at = now
        job.updated_at = now
        job.secret_encrypted = None
        self._storage.save_setup_job(job)
        self.add_event(job, EventLevel.ERROR, "failed", error_message)
        self._audit.log(
            "setup_job_failed",
            target_type="setup_job",
            target_id=job.id,
            metadata={"error": error_message},
        )
