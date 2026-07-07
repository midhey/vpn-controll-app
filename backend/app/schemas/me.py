from __future__ import annotations

from pydantic import BaseModel

from app.schemas.auth import UserOut
from app.schemas.devices import DeviceOut


class AccessOut(BaseModel):
    is_active: bool
    message: str


class DeviceLimitOut(BaseModel):
    used: int
    limit: int | None = None
    unlimited: bool


class SupportHintOut(BaseModel):
    visible: bool
    hint: str | None = None


class DashboardOut(BaseModel):
    user: UserOut
    access: AccessOut
    device_limit: DeviceLimitOut
    support: SupportHintOut
    recent_devices: list[DeviceOut]
