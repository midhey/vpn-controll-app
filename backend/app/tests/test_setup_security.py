from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.core.config import Settings
from app.core.security import FernetSecretBox
from app.db.base import Base
from app.db.session import Database
from app.domain.models import AuthMethod, SetupJob, SetupJobStatus, User, UserRole
from app.main import build_container
from app.services.agent_client import AgentResponse, AgentTransport
from app.services.audit_service import AuditService
from app.storage.db import DatabaseStorage
from app.storage.memory import InMemoryStorage
from app.workers.setup_worker import (
    AgentCredentials,
    DeployScriptSetupRunner,
    SetupStepError,
)


def _job(*, auth_method: AuthMethod = AuthMethod.PASSWORD) -> SetupJob:
    now = datetime.now(UTC)
    return SetupJob(
        id="job-1",
        created_by_user_id="admin-1",
        server_name="node",
        host="203.0.113.10",
        ssh_port=22,
        ssh_username="root",
        auth_method=auth_method,
        created_at=now,
        updated_at=now,
        secret_encrypted=None,
    )


def _runner(script_path: Path, *, timeout: float = 1.0) -> DeployScriptSetupRunner:
    return DeployScriptSetupRunner(
        Settings(
            setup_runner="deploy_script",
            setup_agent_allow_ips=["10.0.0.5"],
            setup_deploy_script_path=str(script_path),
            setup_timeout_seconds=timeout,
        )
    )


def test_fernet_secret_box_round_trip() -> None:
    box = FernetSecretBox(Fernet.generate_key().decode())
    encrypted = box.encrypt("ssh-private-key")

    assert encrypted.startswith("fernet$")
    assert "ssh-private-key" not in encrypted
    assert box.decrypt(encrypted) == "ssh-private-key"


def test_production_rejects_fake_agent_before_startup() -> None:
    with pytest.raises(ValueError, match="AGENT_MODE=http"):
        Settings.from_env({"APP_ENV": "production", "AGENT_MODE": "fake"})


def test_production_rejects_missing_encryption_key() -> None:
    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        Settings.from_env(
            {
                "APP_ENV": "production",
                "AGENT_MODE": "http",
                "SETUP_RUNNER": "deploy_script",
                "SETUP_AGENT_ALLOW_IPS": "10.0.0.5",
            }
        )


def test_production_rejects_invalid_encryption_key() -> None:
    with pytest.raises(ValueError, match="valid Fernet key"):
        Settings.from_env(
            {
                "APP_ENV": "production",
                "AGENT_MODE": "http",
                "ENCRYPTION_KEY": "not-a-fernet-key",
                "SETUP_RUNNER": "deploy_script",
                "SETUP_AGENT_ALLOW_IPS": "10.0.0.5",
            }
        )


@pytest.mark.parametrize(
    "public_network",
    ["0.0.0.1/0", "0:0:0:0:0:0:0:0/0"],
)
def test_production_rejects_equivalent_public_allowlists(public_network: str) -> None:
    with pytest.raises(ValueError, match="must not allow the internet"):
        Settings.from_env(
            {
                "APP_ENV": "production",
                "AGENT_MODE": "http",
                "ENCRYPTION_KEY": Fernet.generate_key().decode(),
                "SETUP_RUNNER": "deploy_script",
                "SETUP_AGENT_ALLOW_IPS": public_network,
            }
        )


def test_allowlist_is_parsed_and_normalized() -> None:
    settings = Settings.from_env(
        {"APP_ENV": "local", "SETUP_AGENT_ALLOW_IPS": "10.0.0.5,2001:db8::5"}
    )

    assert settings.setup_agent_allow_ips == ["10.0.0.5/32", "2001:db8::5/128"]


def test_audit_redacts_secret_bearing_metadata() -> None:
    storage = InMemoryStorage()
    audit = AuditService(storage, lambda: None)  # type: ignore[arg-type]

    audit.log(
        "test",
        metadata={"ssh_secret": "private", "nested": {"vpn_url": "vpn://private"}},
    )

    assert audit.list()[0].metadata == {
        "ssh_secret": "[redacted]",
        "nested": {"vpn_url": "[redacted]"},
    }


def test_deploy_runner_never_places_credentials_in_argv() -> None:
    secret = "ssh-password-that-must-not-appear"
    hmac_secret = "agent-secret-that-must-not-appear"
    job = SetupJob(
        id="job-1",
        created_by_user_id="admin-1",
        server_name="node",
        host="203.0.113.10",
        ssh_port=22,
        ssh_username="root",
        auth_method=AuthMethod.PASSWORD,
        created_at=None,  # type: ignore[arg-type] - not used by command builder
        updated_at=None,  # type: ignore[arg-type] - not used by command builder
        secret_encrypted=None,
    )
    runner = DeployScriptSetupRunner(
        Settings(
            setup_runner="deploy_script",
            setup_agent_allow_ips=["10.0.0.5"],
            setup_deploy_script_path="../agent/scripts/deploy-agent.sh",
        )
    )

    command = runner.build_command(
        job, AgentCredentials(key_id="backend-test", secret=hmac_secret, base_url="http://node")
    )
    rendered = " ".join(command)

    assert secret not in rendered
    assert hmac_secret not in rendered
    assert "--password-env" in command
    assert "--hmac-secret-env" in command


def test_deploy_runner_detects_agent_allowlist_from_ssh_when_not_configured() -> None:
    runner = DeployScriptSetupRunner(Settings(setup_runner="deploy_script"))
    command = runner.build_command(
        _job(), AgentCredentials("backend-test", "hmac-secret", "http://node")
    )

    allow_ip_index = command.index("--allow-ip")
    assert command[allow_ip_index + 1] == "ssh-source"


def test_deploy_runner_uses_real_separate_phases(tmp_path: Path, monkeypatch) -> None:
    phase_log = tmp_path / "phases.log"
    script = tmp_path / "deploy.sh"
    script.write_text(
        "#!/bin/bash\n"
        "if [[ \"$*\" == *--preflight-only* || \"$*\" == *--inspect-only* ]]; then\n"
        "  [[ -z \"${VPN_AGENT_DEPLOY_HMAC_SECRET+x}\" ]] || exit 46\n"
        "fi\n"
        'printf "%s\\n" "$*" >> "$PHASE_LOG"\n',
        encoding="utf-8",
    )
    script.chmod(0o700)
    monkeypatch.setenv("PHASE_LOG", str(phase_log))
    monkeypatch.setenv("VPN_AGENT_DEPLOY_HMAC_SECRET", "ambient-secret")
    runner = _runner(script)
    job = _job()
    credentials = AgentCredentials("backend-test", "hmac-secret", "http://node")

    async def scenario() -> None:
        await runner.check_ssh(job, credentials, "ssh-secret")
        await runner.install_agent(job, credentials, "ssh-secret")
        await runner.install_vpn(job, credentials, "ssh-secret")

    asyncio.run(scenario())
    phases = phase_log.read_text(encoding="utf-8").splitlines()
    assert "--preflight-only" in phases[0]
    assert "--install-service" in phases[1]
    assert "--skip-inspect" in phases[1]
    assert "--inspect-only" in phases[2]


def test_deploy_runner_subprocess_failure_is_safe(tmp_path: Path) -> None:
    script = tmp_path / "fail.sh"
    script.write_text("#!/bin/bash\nexit 23\n", encoding="utf-8")
    script.chmod(0o700)

    with pytest.raises(SetupStepError, match="установить агент") as caught:
        asyncio.run(
            _runner(script).install_agent(
                _job(),
                AgentCredentials("backend-test", "hmac-secret", "http://node"),
                "ssh-secret",
            )
        )

    assert "ssh-secret" not in str(caught.value)
    assert "hmac-secret" not in str(caught.value)


def test_deploy_runner_timeout_terminates_process_group(tmp_path: Path, monkeypatch) -> None:
    marker = tmp_path / "terminated"
    script = tmp_path / "timeout.sh"
    script.write_text(
        "#!/bin/bash\ntrap 'printf terminated > \"$TERMINATION_MARKER\"; exit 143' TERM\n"
        "sleep 30\n",
        encoding="utf-8",
    )
    script.chmod(0o700)
    monkeypatch.setenv("TERMINATION_MARKER", str(marker))

    with pytest.raises(SetupStepError, match="истекло"):
        asyncio.run(
            _runner(script, timeout=0.05).install_agent(
                _job(),
                AgentCredentials("backend-test", "hmac-secret", "http://node"),
                "ssh-secret",
            )
        )

    assert marker.read_text(encoding="utf-8") == "terminated"


def test_database_claim_is_atomic_between_workers(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'jobs.db'}?timeout=5"
    database = Database(database_url)
    Base.metadata.create_all(database.engine)
    DatabaseStorage(database).add_setup_job(_job())
    workers = [Database(database_url), Database(database_url)]

    def claim(worker_database: Database) -> str | None:
        claimed = DatabaseStorage(worker_database).claim_next_setup_job(
            datetime.now(UTC), "Проверяем SSH-подключение"
        )
        return claimed.id if claimed else None

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, workers))
        assert results.count("job-1") == 1
        assert results.count(None) == 1
        stored = DatabaseStorage(database).get_setup_job("job-1")
        assert stored is not None
        assert stored.status == SetupJobStatus.CHECKING_SSH
    finally:
        for worker in workers:
            worker.close()
        database.close()


class _BlockingHealthTransport(AgentTransport):
    def __init__(self) -> None:
        self.status_started = asyncio.Event()
        self.release_status = asyncio.Event()

    async def request(self, *, base_url, method, path, headers, body) -> AgentResponse:
        if path == "/health":
            return AgentResponse(200, {"status": "ok"})
        if path == "/status":
            self.status_started.set()
            await self.release_status.wait()
            return AgentResponse(200, {"container_running": True, "warnings": []})
        raise AssertionError(path)


class _BlockingInstallRunner:
    def __init__(self) -> None:
        self.install_started = asyncio.Event()
        self.install_cancelled = asyncio.Event()

    async def check_ssh(self, job, credentials, ssh_secret) -> None:
        raise AssertionError("check_ssh must be skipped")

    async def install_agent(self, job, credentials, ssh_secret) -> None:
        self.install_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.install_cancelled.set()
            raise

    async def install_vpn(self, job, credentials, ssh_secret) -> None:
        raise AssertionError("install_vpn must be skipped")


def test_cancel_interrupts_active_deploy_operation() -> None:
    async def scenario() -> None:
        container = build_container(
            Settings(
                app_env="local",
                setup_worker_enabled=True,
                setup_worker_poll_seconds=0.01,
                setup_step_delay_seconds=0,
            )
        )
        now = datetime.now(UTC)
        admin = User(
            id="admin-1",
            login="admin",
            display_name="Admin",
            role=UserRole.ADMIN,
            password_hash="unused",
            created_at=now,
            updated_at=now,
        )
        container.storage.add_user(admin)
        runner = _BlockingInstallRunner()
        container.setup_worker._runner = runner
        created = container.setup_jobs.create(
            admin,
            server_name="node",
            host="203.0.113.10",
            ssh_port=22,
            ssh_username="root",
            auth_method=AuthMethod.PASSWORD,
            secret="temporary-password",
            install_awg=False,
            verify_before_install=False,
        )
        assert created.secret_encrypted is None
        assert (
            container.setup_jobs.get_ephemeral_ssh_secret(created.id)
            == "temporary-password"
        )
        claimed = container.setup_jobs.claim_next()
        assert claimed is not None
        worker_task = asyncio.create_task(container.setup_worker._run_job(claimed))
        await asyncio.wait_for(runner.install_started.wait(), timeout=1)
        container.setup_jobs.cancel(admin, created.id)
        await asyncio.wait_for(worker_task, timeout=1)

        assert runner.install_cancelled.is_set()
        assert container.setup_jobs.get(created.id).status == SetupJobStatus.CANCELLED
        assert container.setup_jobs.get_ephemeral_ssh_secret(created.id) is None

    asyncio.run(scenario())


def test_cancel_during_health_check_cannot_be_overwritten(tmp_path: Path) -> None:
    async def scenario() -> None:
        container = build_container(
            Settings(
                app_env="local",
                database_url=f"sqlite+pysqlite:///{tmp_path / 'cancel.db'}?timeout=5",
                setup_worker_enabled=True,
                setup_step_delay_seconds=0,
            )
        )
        assert container.database is not None
        Base.metadata.create_all(container.database.engine)
        now = datetime.now(UTC)
        admin = User(
            id="admin-1",
            login="admin",
            display_name="Admin",
            role=UserRole.ADMIN,
            password_hash="unused",
            created_at=now,
            updated_at=now,
        )
        container.storage.add_user(admin)
        transport = _BlockingHealthTransport()
        container.agent._transport = transport
        created = container.setup_jobs.create(
            admin,
            server_name="node",
            host="203.0.113.10",
            ssh_port=22,
            ssh_username="root",
            auth_method=AuthMethod.PASSWORD,
            secret="temporary-password",
            install_awg=False,
            verify_before_install=False,
        )
        claimed = container.setup_jobs.claim_next()
        assert claimed is not None
        worker_task = asyncio.create_task(container.setup_worker._run_job(claimed))
        await asyncio.wait_for(transport.status_started.wait(), timeout=1)
        container.setup_jobs.cancel(admin, created.id)
        transport.release_status.set()
        await worker_task

        stored = container.setup_jobs.get(created.id)
        assert stored.status == SetupJobStatus.CANCELLED
        assert stored.secret_encrypted is None
        nodes = container.servers.list_all()
        assert len(nodes) == 1
        assert nodes[0].is_available_for_new_devices is False
        container.database.close()

    asyncio.run(scenario())
