from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.models import User, UserRole


class AdminUserOut(BaseModel):
    id: str
    login: str
    display_name: str
    role: UserRole
    telegram_username: str | None = None
    is_active: bool
    device_limit: int | None = None
    device_limit_unlimited: bool
    show_server_support: bool
    free_access: bool
    note: str | None = None
    active_device_count: int = 0
    created_at: datetime

    @classmethod
    def from_domain(cls, user: User, active_device_count: int = 0) -> AdminUserOut:
        return cls(
            id=user.id,
            login=user.login,
            display_name=user.display_name,
            role=user.role,
            telegram_username=user.telegram_username,
            is_active=user.is_active,
            device_limit=user.device_limit,
            device_limit_unlimited=user.device_limit_unlimited,
            show_server_support=user.show_server_support,
            free_access=user.free_access,
            note=user.note,
            active_device_count=active_device_count,
            created_at=user.created_at,
        )


class AdminUserCreateIn(BaseModel):
    login: str = Field(min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=6, max_length=256)
    role: UserRole = UserRole.USER
    telegram_username: str | None = Field(default=None, max_length=64)
    device_limit: int | None = Field(default=3, ge=0)
    device_limit_unlimited: bool = False
    show_server_support: bool = True
    free_access: bool = False
    note: str | None = Field(default=None, max_length=500)


class AdminUserUpdateIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: UserRole | None = None
    telegram_username: str | None = Field(default=None, max_length=64)
    device_limit: int | None = Field(default=None, ge=0)
    device_limit_unlimited: bool | None = None
    show_server_support: bool | None = None
    free_access: bool | None = None
    note: str | None = Field(default=None, max_length=500)


class ResetPasswordIn(BaseModel):
    password: str = Field(min_length=6, max_length=256)
