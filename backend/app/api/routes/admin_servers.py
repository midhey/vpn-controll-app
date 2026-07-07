from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container, CurrentAdmin
from app.schemas.admin_servers import (
    AdminServerCreateIn,
    AdminServerOut,
    AdminServerUpdateIn,
    AgentPeerOut,
)

router = APIRouter(prefix="/admin/servers", tags=["admin:servers"])


def _out(container, node) -> AdminServerOut:
    return AdminServerOut.from_domain(
        node, container.storage.count_active_devices_for_server(node.id)
    )


@router.get("", response_model=list[AdminServerOut])
async def list_servers(admin: CurrentAdmin, container: Container) -> list[AdminServerOut]:
    return [_out(container, n) for n in container.servers.list_all()]


@router.post("", response_model=AdminServerOut, status_code=201)
async def create_server(
    body: AdminServerCreateIn, admin: CurrentAdmin, container: Container
) -> AdminServerOut:
    node = container.servers.create_manual(
        admin,
        name=body.name,
        public_host=body.public_host,
        agent_base_url=body.agent_base_url,
        public_port=body.public_port,
        region_note=body.region_note,
        provider=body.provider,
        agent_key_id=body.agent_key_id,
        agent_secret=body.agent_secret,
        agent_allowed_ip_note=body.agent_allowed_ip_note,
        is_available_for_new_devices=body.is_available_for_new_devices,
    )
    return _out(container, node)


@router.get("/{server_id}", response_model=AdminServerOut)
async def get_server(
    server_id: str, admin: CurrentAdmin, container: Container
) -> AdminServerOut:
    return _out(container, container.servers.get(server_id))


@router.patch("/{server_id}", response_model=AdminServerOut)
async def update_server(
    server_id: str, body: AdminServerUpdateIn, admin: CurrentAdmin, container: Container
) -> AdminServerOut:
    node = container.servers.update(admin, server_id, body.model_dump(exclude_unset=True))
    return _out(container, node)


@router.post("/{server_id}/health-check", response_model=AdminServerOut)
async def health_check(
    server_id: str, admin: CurrentAdmin, container: Container
) -> AdminServerOut:
    node = await container.servers.health_check(server_id, actor_user_id=admin.id)
    return _out(container, node)


@router.get("/{server_id}/peers", response_model=list[AgentPeerOut])
async def server_peers(
    server_id: str, admin: CurrentAdmin, container: Container
) -> list[AgentPeerOut]:
    return [AgentPeerOut(**peer) for peer in await container.servers.agent_peers(server_id)]


@router.post("/{server_id}/disable", response_model=AdminServerOut)
async def disable_server(
    server_id: str, admin: CurrentAdmin, container: Container
) -> AdminServerOut:
    return _out(container, container.servers.set_disabled(admin, server_id, True))


@router.post("/{server_id}/enable", response_model=AdminServerOut)
async def enable_server(
    server_id: str, admin: CurrentAdmin, container: Container
) -> AdminServerOut:
    return _out(container, container.servers.set_disabled(admin, server_id, False))
