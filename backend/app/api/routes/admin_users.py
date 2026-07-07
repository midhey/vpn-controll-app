from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container, CurrentAdmin
from app.schemas.admin_users import (
    AdminUserCreateIn,
    AdminUserOut,
    AdminUserUpdateIn,
    ResetPasswordIn,
)
from app.schemas.devices import DeviceOut
from app.schemas.support import ContributionCreateIn, ContributionOut

router = APIRouter(prefix="/admin/users", tags=["admin:users"])


@router.get("", response_model=list[AdminUserOut])
async def list_users(admin: CurrentAdmin, container: Container) -> list[AdminUserOut]:
    return [
        AdminUserOut.from_domain(user, count)
        for user, count in container.users.list_with_device_counts()
    ]


@router.post("", response_model=AdminUserOut, status_code=201)
async def create_user(
    body: AdminUserCreateIn, admin: CurrentAdmin, container: Container
) -> AdminUserOut:
    user = container.users.create(
        admin,
        login=body.login,
        display_name=body.display_name,
        password=body.password,
        role=body.role,
        telegram_username=body.telegram_username,
        device_limit=body.device_limit,
        device_limit_unlimited=body.device_limit_unlimited,
        show_server_support=body.show_server_support,
        free_access=body.free_access,
        note=body.note,
    )
    return AdminUserOut.from_domain(user)


@router.get("/{user_id}", response_model=AdminUserOut)
async def get_user(user_id: str, admin: CurrentAdmin, container: Container) -> AdminUserOut:
    user = container.users.get(user_id)
    return AdminUserOut.from_domain(
        user, container.storage.count_devices_toward_limit(user.id)
    )


@router.patch("/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: str, body: AdminUserUpdateIn, admin: CurrentAdmin, container: Container
) -> AdminUserOut:
    user = container.users.update(admin, user_id, body.model_dump(exclude_unset=True))
    return AdminUserOut.from_domain(
        user, container.storage.count_devices_toward_limit(user.id)
    )


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str, body: ResetPasswordIn, admin: CurrentAdmin, container: Container
) -> dict:
    container.users.reset_password(admin, user_id, body.password)
    return {"ok": True}


@router.post("/{user_id}/disable", response_model=AdminUserOut)
async def disable_user(user_id: str, admin: CurrentAdmin, container: Container) -> AdminUserOut:
    user = container.users.set_active(admin, user_id, False)
    return AdminUserOut.from_domain(user)


@router.post("/{user_id}/enable", response_model=AdminUserOut)
async def enable_user(user_id: str, admin: CurrentAdmin, container: Container) -> AdminUserOut:
    user = container.users.set_active(admin, user_id, True)
    return AdminUserOut.from_domain(user)


@router.get("/{user_id}/devices", response_model=list[DeviceOut])
async def user_devices(
    user_id: str, admin: CurrentAdmin, container: Container
) -> list[DeviceOut]:
    container.users.get(user_id)  # 404, если участника нет
    return [
        DeviceOut.from_domain(d, container.devices.server_name(d))
        for d in container.devices.list_for_user(user_id)
    ]


@router.get("/{user_id}/support-contributions", response_model=list[ContributionOut])
async def user_contributions(
    user_id: str, admin: CurrentAdmin, container: Container
) -> list[ContributionOut]:
    return [
        ContributionOut.from_domain(c)
        for c in container.support.list_for_user_admin(user_id)
    ]


@router.post(
    "/{user_id}/support-contributions", response_model=ContributionOut, status_code=201
)
async def record_contribution(
    user_id: str, body: ContributionCreateIn, admin: CurrentAdmin, container: Container
) -> ContributionOut:
    contribution = container.support.record(
        admin,
        user_id,
        amount=body.amount,
        currency=body.currency,
        period_label=body.period_label,
        comment=body.comment,
    )
    return ContributionOut.from_domain(contribution)
