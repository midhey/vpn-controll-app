from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container, CurrentAdmin
from app.schemas.setup_jobs import SetupJobCreateIn, SetupJobEventOut, SetupJobOut

router = APIRouter(prefix="/admin/setup-jobs", tags=["admin:setup-jobs"])


def _out(job, container: Container) -> SetupJobOut:
    return SetupJobOut.from_domain(
        job,
        agent_base_url=container.settings.setup_agent_base_url_template.format(host=job.host),
        agent_allow_ips=container.settings.setup_agent_allow_ips,
    )


@router.post("", response_model=SetupJobOut, status_code=201)
async def create_job(
    body: SetupJobCreateIn, admin: CurrentAdmin, container: Container
) -> SetupJobOut:
    job = container.setup_jobs.create(
        admin,
        server_name=body.server_name,
        host=body.host,
        ssh_port=body.ssh_port,
        ssh_username=body.ssh_username,
        auth_method=body.auth_method,
        secret=body.secret,
        region_note=body.region_note,
        install_awg=body.install_awg,
        available_for_new_devices=body.available_for_new_devices,
        verify_before_install=body.verify_before_install,
    )
    return _out(job, container)


@router.get("", response_model=list[SetupJobOut])
async def list_jobs(admin: CurrentAdmin, container: Container) -> list[SetupJobOut]:
    return [_out(j, container) for j in container.setup_jobs.list()]


@router.get("/{job_id}", response_model=SetupJobOut)
async def get_job(job_id: str, admin: CurrentAdmin, container: Container) -> SetupJobOut:
    return _out(container.setup_jobs.get(job_id), container)


@router.post("/{job_id}/start", response_model=SetupJobOut)
async def start_job(job_id: str, admin: CurrentAdmin, container: Container) -> SetupJobOut:
    return _out(container.setup_jobs.start(admin, job_id), container)


@router.post("/{job_id}/cancel", response_model=SetupJobOut)
async def cancel_job(job_id: str, admin: CurrentAdmin, container: Container) -> SetupJobOut:
    return _out(container.setup_jobs.cancel(admin, job_id), container)


@router.get("/{job_id}/events", response_model=list[SetupJobEventOut])
async def job_events(
    job_id: str, admin: CurrentAdmin, container: Container
) -> list[SetupJobEventOut]:
    return [SetupJobEventOut.from_domain(e) for e in container.setup_jobs.events(job_id)]
