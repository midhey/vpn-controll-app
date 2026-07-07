from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container, CurrentUser
from app.domain.models import DeviceStatus
from app.schemas.auth import UserOut
from app.schemas.devices import DeviceOut
from app.schemas.me import AccessOut, DashboardOut, DeviceLimitOut, SupportHintOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.from_domain(user)


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(user: CurrentUser, container: Container) -> DashboardOut:
    used = container.storage.count_devices_toward_limit(user.id)
    unlimited = user.device_limit_unlimited or user.device_limit is None
    support_visible = container.support.visible_for(user)
    recent = [
        d
        for d in container.devices.list_for_user(user.id)
        if d.status != DeviceStatus.REVOKED
    ][:3]
    return DashboardOut(
        user=UserOut.from_domain(user),
        access=AccessOut(is_active=user.is_active, message="Твой доступ активен"),
        device_limit=DeviceLimitOut(
            used=used,
            limit=None if unlimited else user.device_limit,
            unlimited=unlimited,
        ),
        support=SupportHintOut(
            visible=support_visible,
            hint="Можно поддержать сервер" if support_visible else None,
        ),
        recent_devices=[
            DeviceOut.from_domain(d, container.devices.server_name(d)) for d in recent
        ],
    )
