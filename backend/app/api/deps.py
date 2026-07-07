"""Зависимости роутеров: контейнер сервисов, текущий пользователь, роли."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request

from app.core.errors import forbidden, unauthorized
from app.domain.models import User, UserRole


def get_container(request: Request) -> Any:
    """Контейнер собирается в app.main.build_container и живёт в app.state."""
    return request.app.state.container


def get_client_meta(request: Request) -> tuple[str | None, str | None]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


async def get_current_user(request: Request) -> User:
    container = request.app.state.container
    token = request.cookies.get(container.settings.session_cookie_name)
    if not token:
        raise unauthorized()
    user = container.auth.resolve_session(token)
    if user is None:
        raise unauthorized("Сессия истекла — войди заново")
    return user


async def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != UserRole.ADMIN:
        raise forbidden()
    return user


Container = Annotated[Any, Depends(get_container)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
ClientMeta = Annotated[tuple[str | None, str | None], Depends(get_client_meta)]
