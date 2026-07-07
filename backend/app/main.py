"""Сборка приложения: контейнер сервисов, middleware, bootstrap первого админа.

Запуск локально:  uvicorn app.main:app --reload
Swagger:          /api/docs
"""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import (
    admin_audit_logs,
    admin_servers,
    admin_setup_jobs,
    admin_support,
    admin_users,
    auth,
    devices,
    me,
    servers,
    support,
)
from app.core.config import Settings
from app.core.errors import ErrorCode, error_body, install_error_handlers
from app.core.logging import setup_logging
from app.core.security import (
    PasswordHasher,
    PlaintextSecretBox,
    SecretBox,
    generate_password,
)
from app.db.session import Database
from app.domain.models import User, UserRole
from app.services.agent_client import (
    AgentClient,
    AgentTransport,
    FakeAgentTransport,
    HttpxAgentTransport,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.device_service import DeviceService
from app.services.server_service import ServerService
from app.services.setup_job_service import SetupJobService
from app.services.support_service import SupportService
from app.services.user_service import UserService
from app.storage.db import DatabaseStorage
from app.storage.memory import InMemoryStorage
from app.workers.setup_worker import SetupWorker, StubSetupRunner

logger = logging.getLogger(__name__)

API_VERSION = "0.1.0"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Container:
    settings: Settings
    clock: Any
    storage: Any
    database: Database | None
    password_hasher: PasswordHasher
    secret_box: SecretBox
    agent_transport: AgentTransport
    agent: AgentClient
    audit: AuditService
    auth: AuthService
    users: UserService
    servers: ServerService
    devices: DeviceService
    support: SupportService
    setup_jobs: SetupJobService
    setup_worker: SetupWorker


def build_container(settings: Settings) -> Container:
    clock = utc_now
    database = Database(settings.database_url) if settings.database_url else None
    storage = DatabaseStorage(database) if database else InMemoryStorage()
    password_hasher = PasswordHasher()
    secret_box = PlaintextSecretBox()
    transport: AgentTransport
    if settings.agent_mode == "http":
        transport = HttpxAgentTransport()
    else:
        transport = FakeAgentTransport()
    agent = AgentClient(transport, secret_box)
    audit = AuditService(storage, clock)
    auth_service = AuthService(storage, settings, password_hasher, audit, clock)
    users = UserService(storage, password_hasher, audit, clock)
    server_service = ServerService(storage, agent, secret_box, audit, clock)
    device_service = DeviceService(
        storage, server_service, agent, secret_box, settings, audit, clock
    )
    support_service = SupportService(storage, users, audit, clock)
    setup_jobs = SetupJobService(storage, secret_box, audit, clock)
    runner = StubSetupRunner(settings.setup_step_delay_seconds)
    setup_worker = SetupWorker(storage, setup_jobs, server_service, agent, runner, settings)
    return Container(
        settings=settings,
        clock=clock,
        storage=storage,
        database=database,
        password_hasher=password_hasher,
        secret_box=secret_box,
        agent_transport=transport,
        agent=agent,
        audit=audit,
        auth=auth_service,
        users=users,
        servers=server_service,
        devices=device_service,
        support=support_service,
        setup_jobs=setup_jobs,
        setup_worker=setup_worker,
    )


def bootstrap_first_admin(container: Container) -> None:
    """Идемпотентно: создаёт админа, только если ни одного админа ещё нет."""
    if container.storage.has_admin():
        return
    settings = container.settings
    password = settings.first_admin_password
    generated = password is None
    if generated:
        password = generate_password()
    now = container.clock()
    admin = User(
        id=str(uuid.uuid4()),
        login=settings.first_admin_login.strip().lower(),
        display_name=settings.first_admin_login,
        role=UserRole.ADMIN,
        password_hash=container.password_hasher.hash(password),
        created_at=now,
        updated_at=now,
        device_limit=None,
        device_limit_unlimited=True,
        show_server_support=False,
        free_access=True,
    )
    container.storage.add_user(admin)
    container.audit.log("bootstrap_admin_created", target_type="user", target_id=admin.id)
    if generated:
        logger.warning(
            "Создан первый админ %r с одноразовым паролем: %s — задай FIRST_ADMIN_PASSWORD "
            "или смени пароль после входа",
            admin.login,
            password,
        )
    else:
        logger.info("Создан первый админ %r (пароль из FIRST_ADMIN_PASSWORD)", admin.login)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    setup_logging()
    container = build_container(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        bootstrap_first_admin(container)
        if settings.setup_worker_enabled:
            container.setup_worker.start()
        yield
        await container.setup_worker.stop()
        if container.database is not None:
            container.database.close()

    app = FastAPI(
        title="Подсос VPN API",
        version=API_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.container = container
    install_error_handlers(app)

    @app.middleware("http")
    async def csrf_protect(request: Request, call_next):
        """SameSite=Lax + кастомный заголовок: межсайтовая форма не пройдёт preflight."""
        if settings.csrf_enabled and request.method in UNSAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin not in settings.cors_origins:
                return JSONResponse(
                    status_code=403,
                    content=error_body(ErrorCode.CSRF_FAILED, "Запрос отклонён (CSRF)"),
                )
            if request.headers.get("x-requested-with", "").lower() != "xmlhttprequest":
                return JSONResponse(
                    status_code=403,
                    content=error_body(
                        ErrorCode.CSRF_FAILED, "Нет заголовка X-Requested-With"
                    ),
                )
        return await call_next(request)

    # CORS добавляется после CSRF-миддлвари, чтобы быть внешним слоем (preflight).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api = APIRouter(prefix="/api/v1")

    @api.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "version": API_VERSION}

    for router in (
        auth.router,
        me.router,
        devices.router,
        servers.router,
        support.router,
        admin_users.router,
        admin_servers.router,
        admin_setup_jobs.router,
        admin_support.router,
        admin_audit_logs.router,
    ):
        api.include_router(router)
    app.include_router(api)
    return app


app = create_app()
