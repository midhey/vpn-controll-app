"""Фоновая установка VPS без передачи секретов в argv или логи."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import tempfile
from collections.abc import Awaitable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

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
    """A safe, administrator-facing setup error (never include a credential)."""


@dataclass(frozen=True, slots=True)
class AgentCredentials:
    key_id: str
    secret: str
    base_url: str


class SetupRunner(Protocol):
    async def check_ssh(
        self, job: SetupJob, credentials: AgentCredentials, ssh_secret: str
    ) -> None: ...

    async def install_agent(
        self, job: SetupJob, credentials: AgentCredentials, ssh_secret: str
    ) -> None: ...

    async def install_vpn(
        self, job: SetupJob, credentials: AgentCredentials, ssh_secret: str
    ) -> None: ...


class StubSetupRunner:
    """Local-demo runner. Production validation prohibits selecting it."""

    def __init__(self, step_delay_seconds: float) -> None:
        self._delay = step_delay_seconds

    async def check_ssh(
        self, job: SetupJob, credentials: AgentCredentials, ssh_secret: str
    ) -> None:
        await asyncio.sleep(self._delay)
        if "fail" in job.host:
            raise SetupStepError(f"Не удалось подключиться по SSH к {job.host} (имитация)")

    async def install_agent(
        self, job: SetupJob, credentials: AgentCredentials, ssh_secret: str
    ) -> None:
        await asyncio.sleep(self._delay)

    async def install_vpn(
        self, job: SetupJob, credentials: AgentCredentials, ssh_secret: str
    ) -> None:
        await asyncio.sleep(self._delay)


class DeployScriptSetupRunner:
    """Runs deploy-agent.sh with credentials held only in process environment.

    SSH passwords and the agent HMAC secret are passed as environment variables;
    SSH keys use a temporary ``0600`` file deleted in ``finally``.  The deploy
    script receives only environment *variable names*, so neither secret appears
    in subprocess arguments, job events, audit records, or exception text.
    """

    _ssh_password_env = "VPN_AGENT_DEPLOY_SSH_PASSWORD"
    _hmac_secret_env = "VPN_AGENT_DEPLOY_HMAC_SECRET"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        path = Path(settings.setup_deploy_script_path)
        self._script_path = (
            path if path.is_absolute() else Path(__file__).resolve().parents[2] / path
        )

    def build_command(
        self,
        job: SetupJob,
        credentials: AgentCredentials,
        *,
        phase: str = "install",
        identity_file: str | None = None,
    ) -> list[str]:
        command = [
            "/bin/bash",
            str(self._script_path),
            "--user",
            job.ssh_username,
            "--host",
            job.host,
            "--ssh-port",
            str(job.ssh_port),
        ]
        if job.auth_method.value == "ssh_key":
            if identity_file is None:
                raise SetupStepError("Не удалось подготовить временный SSH-ключ")
            command.extend(["--identity-file", identity_file])
        else:
            command.extend(["--password-env", self._ssh_password_env])
            if job.ssh_username != "root":
                command.append("--reuse-password-for-sudo")
        if phase == "preflight":
            command.append("--preflight-only")
        elif phase == "inspect":
            command.append("--inspect-only")
        elif phase == "install":
            command.extend(
                [
                    "--install-service",
                    "--service-name",
                    "vpn-agent",
                    "--listen",
                    self._settings.setup_agent_listen,
                    "--endpoint-host",
                    job.host,
                    "--hmac-key-id",
                    credentials.key_id,
                    "--hmac-secret-env",
                    self._hmac_secret_env,
                    "--allow-ip",
                    ",".join(self._settings.setup_agent_allow_ips) or "ssh-source",
                    "--skip-inspect",
                ]
            )
        else:
            raise ValueError(f"unknown deploy phase: {phase}")
        return command

    async def check_ssh(
        self, job: SetupJob, credentials: AgentCredentials, ssh_secret: str
    ) -> None:
        await self._run_script(job, credentials, ssh_secret, phase="preflight")

    async def install_agent(
        self, job: SetupJob, credentials: AgentCredentials, ssh_secret: str
    ) -> None:
        await self._run_script(job, credentials, ssh_secret, phase="install")

    async def install_vpn(
        self, job: SetupJob, credentials: AgentCredentials, ssh_secret: str
    ) -> None:
        await self._run_script(job, credentials, ssh_secret, phase="inspect")

    async def _run_script(
        self,
        job: SetupJob,
        credentials: AgentCredentials,
        ssh_secret: str,
        *,
        phase: str,
    ) -> None:
        identity_path: str | None = None
        env = os.environ.copy()
        env.pop(self._ssh_password_env, None)
        env.pop(self._hmac_secret_env, None)
        if phase == "install":
            env[self._hmac_secret_env] = credentials.secret
        try:
            if job.auth_method.value == "ssh_key":
                fd, identity_path = tempfile.mkstemp(prefix="vpn-agent-", suffix=".key")
                try:
                    os.fchmod(fd, 0o600)
                    with os.fdopen(fd, "w", encoding="utf-8") as key_file:
                        key_file.write(ssh_secret)
                except Exception:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
                    raise
            else:
                env[self._ssh_password_env] = ssh_secret

            command = self.build_command(
                job, credentials, phase=phase, identity_file=identity_path
            )
            if not self._script_path.is_file():
                raise SetupStepError("Скрипт установки агента не найден")
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                start_new_session=True,
            )
            communicate_task = asyncio.create_task(process.communicate())
            try:
                _, stderr = await asyncio.wait_for(
                    asyncio.shield(communicate_task),
                    timeout=self._settings.setup_timeout_seconds,
                )
            except TimeoutError as exc:
                await self._terminate_process_group(process, communicate_task)
                raise SetupStepError("Время операции установки истекло") from exc
            except asyncio.CancelledError:
                await self._terminate_process_group(process, communicate_task)
                raise
            if process.returncode != 0:
                # stderr could contain provider-specific data; preserve only a safe diagnostic.
                logger.warning(
                    "deploy script failed for setup job %s with exit code %s (%d stderr bytes)",
                    job.id,
                    process.returncode,
                    len(stderr),
                )
                messages = {
                    "preflight": "Не удалось выполнить SSH preflight",
                    "install": "Не удалось установить агент на VPS",
                    "inspect": "Не удалось проверить VPN-окружение",
                }
                raise SetupStepError(messages[phase])
        finally:
            env.pop(self._ssh_password_env, None)
            env.pop(self._hmac_secret_env, None)
            if identity_path:
                try:
                    os.remove(identity_path)
                except FileNotFoundError:
                    pass

    @staticmethod
    async def _terminate_process_group(
        process: asyncio.subprocess.Process,
        communicate_task: asyncio.Task[tuple[bytes, bytes]],
    ) -> None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            # deploy-agent.sh may spend up to its 10s SSH ConnectTimeout in EXIT cleanup.
            await asyncio.wait_for(asyncio.shield(communicate_task), timeout=15)
            return
        except TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        await communicate_task


class SetupWorker:
    def __init__(
        self,
        storage: InMemoryStorage,
        jobs: SetupJobService,
        servers: ServerService,
        agent: AgentClient,
        runner: SetupRunner,
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
            except asyncio.CancelledError:
                self._jobs.finish_failed(job.id, "Установка прервана остановкой воркера")
                raise
            except Exception:
                logger.exception("setup job %s crashed", job.id)
                self._jobs.finish_failed(job.id, "Внутренняя ошибка установки")

    async def _run_job(self, job: SetupJob) -> None:
        ssh_secret = self._jobs.get_ephemeral_ssh_secret(job.id)
        if ssh_secret is None:
            self._jobs.finish_failed(
                job.id,
                "SSH-пароль больше недоступен; создай новую задачу и введи пароль заново",
            )
            return
        credentials = AgentCredentials(
            key_id=generate_agent_key_id(),
            secret=generate_agent_secret(),
            base_url=self._settings.setup_agent_base_url_template.format(host=job.host).rstrip("/"),
        )
        try:
            preflight_performed = job.verify_before_install
            if job.verify_before_install:
                completed, _ = await self._run_cancellable(
                    job.id, self._runner.check_ssh(job, credentials, ssh_secret)
                )
                if not completed:
                    return
            else:
                self._jobs.add_event(
                    job,
                    EventLevel.WARNING,
                    SetupJobStatus.CHECKING_SSH.value,
                    "SSH preflight пропущен по настройке",
                )

            job = self._jobs.set_step(
                job.id,
                {SetupJobStatus.CHECKING_SSH},
                SetupJobStatus.INSTALLING_AGENT,
                STEP_START_MESSAGES[SetupJobStatus.INSTALLING_AGENT],
            )
            if job is None:
                return
            if preflight_performed:
                self._jobs.add_event(
                    job,
                    EventLevel.INFO,
                    SetupJobStatus.CHECKING_SSH.value,
                    "SSH preflight успешно выполнен",
                )
            completed, _ = await self._run_cancellable(
                job.id, self._runner.install_agent(job, credentials, ssh_secret)
            )
            if not completed:
                return

            if job.install_awg:
                next_job = self._jobs.set_step(
                    job.id,
                    {SetupJobStatus.INSTALLING_AGENT},
                    SetupJobStatus.INSTALLING_VPN,
                    STEP_START_MESSAGES[SetupJobStatus.INSTALLING_VPN],
                )
                if next_job is None:
                    return
                self._jobs.add_event(
                    next_job,
                    EventLevel.INFO,
                    SetupJobStatus.INSTALLING_AGENT.value,
                    "Агент установлен",
                )
                job = next_job
                completed, _ = await self._run_cancellable(
                    job.id, self._runner.install_vpn(job, credentials, ssh_secret)
                )
                if not completed:
                    return
                next_job = self._jobs.set_step(
                    job.id,
                    {SetupJobStatus.INSTALLING_VPN},
                    SetupJobStatus.VERIFYING,
                    "Проверяем доступность агента",
                )
                if next_job is None:
                    return
                self._jobs.add_event(
                    next_job,
                    EventLevel.INFO,
                    SetupJobStatus.INSTALLING_VPN.value,
                    "VPN-окружение проверено",
                )
                job = next_job
            else:
                next_job = self._jobs.set_step(
                    job.id,
                    {SetupJobStatus.INSTALLING_AGENT},
                    SetupJobStatus.VERIFYING,
                    "Проверяем доступность агента",
                )
                if next_job is None:
                    return
                self._jobs.add_event(
                    next_job,
                    EventLevel.INFO,
                    SetupJobStatus.INSTALLING_AGENT.value,
                    "Агент установлен",
                )
                self._jobs.add_event(
                    next_job,
                    EventLevel.INFO,
                    SetupJobStatus.INSTALLING_VPN.value,
                    "Проверка VPN-окружения пропущена по настройке",
                )
                job = next_job
            node = self._servers.create_from_setup(
                job,
                agent_base_url=credentials.base_url,
                agent_key_id=credentials.key_id,
                agent_secret=credentials.secret,
            )
            completed, checked = await self._run_cancellable(
                job.id, self._servers.health_check(node.id)
            )
            if not completed:
                return
            if checked.status.value not in {"online", "warning"}:
                last_error = checked.last_error or "нет ответа"
                raise SetupStepError(f"Агент установлен, но health-check не прошёл: {last_error}")
            finished = self._jobs.finish_success(job.id, node.id)
            if finished is not None:
                self._servers.activate_after_setup(
                    node.id, available=job.available_for_new_devices
                )
        except SetupStepError as exc:
            self._jobs.finish_failed(job.id, str(exc))
        except AppError as exc:
            self._jobs.finish_failed(job.id, exc.message)
        finally:
            self._jobs.forget_ephemeral_ssh_secret(job.id)

    async def _run_cancellable(
        self, job_id: str, operation: Awaitable[Any]
    ) -> tuple[bool, Any]:
        task = asyncio.ensure_future(operation)
        poll_seconds = max(0.05, min(self._settings.setup_worker_poll_seconds, 0.5))
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=poll_seconds)
                if task in done:
                    return True, await task
                if self._jobs.get(job_id).status == SetupJobStatus.CANCELLED:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                    return False, None
        except asyncio.CancelledError:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise


STEP_START_MESSAGES = {
    SetupJobStatus.CHECKING_SSH: "Проверяем SSH-подключение",
    SetupJobStatus.INSTALLING_AGENT: "Устанавливаем агент",
    SetupJobStatus.INSTALLING_VPN: "Проверяем VPN-окружение",
}
