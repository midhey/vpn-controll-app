from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import ClientMeta, Container, CurrentUser
from app.schemas.devices import DeviceCreateIn, DeviceCreateOut, DeviceOut, IssueResultOut

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceOut])
async def list_devices(user: CurrentUser, container: Container) -> list[DeviceOut]:
    return [
        DeviceOut.from_domain(d, container.devices.server_name(d))
        for d in container.devices.list_for_user(user.id)
    ]


@router.post("", response_model=DeviceCreateOut, status_code=201)
async def create_device(
    body: DeviceCreateIn, user: CurrentUser, container: Container, meta: ClientMeta
) -> DeviceCreateOut:
    ip, user_agent = meta
    device, issue = await container.devices.create(
        user,
        name=body.name,
        server_node_id=body.server_node_id,
        ip=ip,
        user_agent=user_agent,
    )
    return DeviceCreateOut(
        device=DeviceOut.from_domain(device, container.devices.server_name(device)),
        issue_result=IssueResultOut(**issue),
    )


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: str, user: CurrentUser, container: Container) -> DeviceOut:
    device = container.devices.get_for_actor(user, device_id)
    return DeviceOut.from_domain(device, container.devices.server_name(device))


@router.delete("/{device_id}", response_model=DeviceOut)
async def revoke_device(
    device_id: str, user: CurrentUser, container: Container, meta: ClientMeta
) -> DeviceOut:
    ip, user_agent = meta
    device = await container.devices.revoke(user, device_id, ip=ip, user_agent=user_agent)
    return DeviceOut.from_domain(device, container.devices.server_name(device))


@router.get("/{device_id}/issue-result", response_model=IssueResultOut)
async def issue_result(device_id: str, user: CurrentUser, container: Container) -> IssueResultOut:
    return IssueResultOut(**container.devices.issue_result(user, device_id))
