"""Фоновый воркер установки VPS.

MVP: асинхронный цикл в том же процессе, забирает задачи из очереди хранилища.
Реальную установку выполняет runner; сейчас это StubSetupRunner — имитация
шагов с задержками, чтобы фронт видел живые статусы. Реальный runner будет
запускать agent/scripts/deploy-agent.sh по SSH с флагами --listen/--allow-ip/
--hmac-key-id/--hmac-secret (см. план), интерфейс уже совпадает.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import generate_agent_key_id, generate_agent_secret
from app.domain.models import EventLevel, SetupJob, SetupJobStatus
from app.services.agent_client import AgentClient
from app.services.server_service import ServerService
from app.services.setup_job_service import SetupJobService
from app.storage.memory import InMemoryStorage

logger = logging.getLogger(__name__)


class SetupStepError(Exception):
    """Шаг установки провалился; message показывается админу."""


class StubSetupRunner:
    """Имитация установки. Хост, содержащий "fail", проваливает SSH-проверку —
    удобно демонстрировать экран ошибки."""

    def __init__(self, step_delay_seconds: float) -> None:
        self._delay = step_delay_seconds

    async def check_ssh(self, job: SetupJob) -> None:
        await asyncio.sleep(self._delay)
        if "fail" in job.host:
            raise SetupStepError(f"Не удалось подключиться по SSH к {job.host} (имитация)")

    async def install_agent(self, job: SetupJob) -> None:
        await asyncio.sleep(self._delay)

    async def install_vpn(self, job: SetupJob) -> None:
        await asyncio.sleep(self._delay)

    async def verify(self, job: SetupJob) -> None:
        await asyncio.sleep(self._delay)


class SetupWorker:
    def __init__(
        self,
        storage: InMemoryStorage,
        jobs: SetupJobService,
        servers: ServerService,
        agent: AgentClient,
        runner: StubSetupRunner,
        settings: Settings,
    ) -> None:
        self._storage = storage
        self._jobs = jobs
        self._servers = servers
        self._agent = agent
        self._runner = runner
        self._settings = settings
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop(), name="setup-worker")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            async with self._storage.lock:
                job = self._jobs.claim_next()
            if job is None:
                await asyncio.sleep(self._settings.setup_worker_poll_seconds)
                continue
            try:
                await self._run_job(job)
            except Exception:
                logger.exception("setup job %s crashed", job.id)
                self._jobs.finish_failed(job, "Внутренняя ошибка установки")

    async def _run_job(self, job: SetupJob) -> None:
        steps = [
            (SetupJobStatus.CHECKING_SSH, "SSH-подключение установлено", self._runner.check_ssh),
            (SetupJobStatus.INSTALLING_AGENT, "Агент установлен", self._runner.install_agent),
            (SetupJobStatus.INSTALLING_VPN, "VPN установлен", self._runner.install_vpn),
        ]
        try:
            for status, done_message, step in steps:
                if self._jobs.is_cancelled(job.id):
                    return
                if status == SetupJobStatus.INSTALLING_VPN and not job.install_awg:
                    self._jobs.add_event(
                        job, EventLevel.INFO, status.value, "Установка VPN пропущена по настройке"
                    )
                    continue
                self._jobs.set_step(job, status, STEP_START_MESSAGES[status])
                await step(job)
                self._jobs.add_event(job, EventLevel.INFO, status.value, done_message)

            if self._jobs.is_cancelled(job.id):
                return
            self._jobs.set_step(job, SetupJobStatus.VERIFYING, "Проверяем узел")
            await self._runner.verify(job)
            node = self._servers.create_from_setup(
                job,
                # Реальный деплой передаст скрипту --listen и построит URL из него.
                agent_base_url=f"http://{job.host}:8090",
                agent_key_id=generate_agent_key_id(),
                agent_secret=generate_agent_secret(),
            )
            checked = await self._servers.health_check(node.id)
            if checked.status.value not in {"online", "warning"}:
                last_error = checked.last_error or "нет ответа"
                raise SetupStepError(
                    f"Узел установлен, но health-check не прошёл: {last_error}"
                )
            self._jobs.finish_success(job, node.id)
        except SetupStepError as exc:
            self._jobs.finish_failed(job, str(exc))
        except AppError as exc:
            self._jobs.finish_failed(job, exc.message)


STEP_START_MESSAGES = {
    SetupJobStatus.CHECKING_SSH: "Проверяем SSH-подключение",
    SetupJobStatus.INSTALLING_AGENT: "Устанавливаем агент",
    SetupJobStatus.INSTALLING_VPN: "Устанавливаем VPN",
}
