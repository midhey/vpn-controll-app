"""Задачи установки VPS: очередь, шаги, события.

SSH-секрет никогда не попадает в модель job или постоянное хранилище. Он живёт
только в памяти процесса до завершения установки. После рестарта backend такую
задачу продолжить нельзя — администратор создаёт новую и вводит пароль заново.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.core.errors import AppError, ErrorCode, not_found
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
    SetupJobStatus.DRAFT: "Черновик",
    SetupJobStatus.QUEUED: "В очереди",
    SetupJobStatus.CHECKING_SSH: "Проверяем SSH-подключение",
    SetupJobStatus.INSTALLING_AGENT: "Устанавливаем агент",
    SetupJobStatus.INSTALLING_VPN: "Устанавливаем VPN",
    SetupJobStatus.VERIFYING: "Проверяем узел",
    SetupJobStatus.SUCCESS: "Готово",
    SetupJobStatus.FAILED: "Ошибка",
    SetupJobStatus.CANCELLED: "Отменено",
}

NON_TERMINAL_STATUSES = {
    SetupJobStatus.DRAFT,
    SetupJobStatus.QUEUED,
    SetupJobStatus.CHECKING_SSH,
    SetupJobStatus.INSTALLING_AGENT,
    SetupJobStatus.INSTALLING_VPN,
    SetupJobStatus.VERIFYING,
}


class SetupJobService:
    def __init__(
        self,
        storage: InMemoryStorage,
        audit: AuditService,
        clock: Callable[[], datetime],
        *,
        worker_enabled: bool,
    ) -> None:
        self._storage = storage
        self._audit = audit
        self._clock = clock
        self._worker_enabled = worker_enabled
        self._ephemeral_ssh_secrets: dict[str, str] = {}

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
        if not self._worker_enabled:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Воркер установки выключен; пароль не будет сохранён — включи "
                "SETUP_WORKER_ENABLED и создай задачу заново",
                status=409,
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
            secret_encrypted=None,
            region_note=region_note,
            install_awg=install_awg,
            available_for_new_devices=available_for_new_devices,
            verify_before_install=verify_before_install,
            status=SetupJobStatus.QUEUED,
            current_step=STEP_LABELS[SetupJobStatus.QUEUED],
        )
        self._ephemeral_ssh_secrets[job.id] = secret
        try:
            self._storage.add_setup_job(job)
        except Exception:
            self.forget_ephemeral_ssh_secret(job.id)
            raise
        self.add_event(
            job,
            EventLevel.INFO,
            job.status.value,
            "Задача поставлена в очередь; SSH-пароль хранится только в памяти процесса",
        )
        self._audit.log(
            "setup_job_created",
            actor_user_id=actor.id,
            target_type="setup_job",
            target_id=job.id,
            metadata={"server_name": job.server_name, "host": job.host},
        )
        return job

    def get_ephemeral_ssh_secret(self, job_id: str) -> str | None:
        return self._ephemeral_ssh_secrets.get(job_id)

    def forget_ephemeral_ssh_secret(self, job_id: str) -> None:
        self._ephemeral_ssh_secrets.pop(job_id, None)

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
        """Создание сразу ставит в очередь; повторный start ничего не сохраняет."""
        job = self.get(job_id)
        if not self._worker_enabled:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Воркер установки выключен; включи SETUP_WORKER_ENABLED, чтобы запустить задачу",
                status=409,
            )
        if job.status.is_terminal:
            raise AppError(
                ErrorCode.VALIDATION_ERROR,
                "Задача уже завершена — создай новую",
                status=409,
            )
        if job.status == SetupJobStatus.DRAFT:
            raise AppError(
                ErrorCode.SECRET_REQUIRED,
                "SSH-пароль не хранится; создай новую задачу и введи пароль заново",
                status=409,
            )
        return job

    def cancel(self, actor: User, job_id: str) -> SetupJob:
        self.get(job_id)
        now = self._clock()
        job = self._storage.transition_setup_job(
            job_id,
            NON_TERMINAL_STATUSES,
            {
                "status": SetupJobStatus.CANCELLED,
                "current_step": STEP_LABELS[SetupJobStatus.CANCELLED],
                "finished_at": now,
                "updated_at": now,
                "secret_encrypted": None,
            },
        )
        if job is None:
            raise AppError(
                ErrorCode.VALIDATION_ERROR, "Задача уже завершена", status=409
            )
        self.forget_ephemeral_ssh_secret(job_id)
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
        now = self._clock()
        job = self._storage.claim_next_setup_job(
            now, STEP_LABELS[SetupJobStatus.CHECKING_SSH]
        )
        if job is not None:
            self.add_event(
                job,
                EventLevel.INFO,
                SetupJobStatus.CHECKING_SSH.value,
                "Подготовка SSH preflight",
            )
        return job

    def set_step(
        self,
        job_id: str,
        expected_statuses: set[SetupJobStatus],
        status: SetupJobStatus,
        message: str,
    ) -> SetupJob | None:
        job = self._storage.transition_setup_job(
            job_id,
            expected_statuses,
            {
                "status": status,
                "current_step": STEP_LABELS[status],
                "updated_at": self._clock(),
            },
        )
        if job is not None:
            self.add_event(job, EventLevel.INFO, status.value, message)
        return job

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

    def finish_success(self, job_id: str, server_node_id: str) -> SetupJob | None:
        now = self._clock()
        job = self._storage.transition_setup_job(
            job_id,
            {SetupJobStatus.VERIFYING},
            {
                "status": SetupJobStatus.SUCCESS,
                "current_step": STEP_LABELS[SetupJobStatus.SUCCESS],
                "server_node_id": server_node_id,
                "finished_at": now,
                "updated_at": now,
                "secret_encrypted": None,
                "result_payload": {"server_node_id": server_node_id},
            },
        )
        self.forget_ephemeral_ssh_secret(job_id)
        if job is None:
            return None
        self.add_event(job, EventLevel.INFO, "success", "Узел установлен и подключён")
        self._audit.log(
            "setup_job_succeeded",
            target_type="setup_job",
            target_id=job.id,
            metadata={"server_node_id": server_node_id},
        )
        return job

    def finish_failed(self, job_id: str, error_message: str) -> SetupJob | None:
        now = self._clock()
        job = self._storage.transition_setup_job(
            job_id,
            NON_TERMINAL_STATUSES,
            {
                "status": SetupJobStatus.FAILED,
                "current_step": STEP_LABELS[SetupJobStatus.FAILED],
                "error_message": error_message,
                "finished_at": now,
                "updated_at": now,
                "secret_encrypted": None,
            },
        )
        self.forget_ephemeral_ssh_secret(job_id)
        if job is None:
            return None
        self.add_event(job, EventLevel.ERROR, "failed", error_message)
        self._audit.log(
            "setup_job_failed",
            target_type="setup_job",
            target_id=job.id,
            metadata={"error": error_message},
        )
        return job
