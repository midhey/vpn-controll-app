from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.models import User, UserRole


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: str
    login: str
    display_name: str
    role: UserRole
    telegram_username: str | None = None

    @classmethod
    def from_domain(cls, user: User) -> UserOut:
        return cls(
            id=user.id,
            login=user.login,
            display_name=user.display_name,
            role=user.role,
            telegram_username=user.telegram_username,
        )


class SessionOut(BaseModel):
    user: UserOut
