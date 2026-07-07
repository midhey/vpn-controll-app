from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.api.deps import ClientMeta, Container, CurrentUser
from app.schemas.auth import LoginIn, SessionOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=SessionOut)
async def login(
    body: LoginIn, container: Container, meta: ClientMeta, response: Response
) -> SessionOut:
    ip, user_agent = meta
    user, token = container.auth.login(body.login, body.password, ip=ip, user_agent=user_agent)
    settings = container.settings
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_days * 86400,
        path="/",
    )
    return SessionOut(user=UserOut.from_domain(user))


@router.post("/logout")
async def logout(
    request: Request, container: Container, meta: ClientMeta, response: Response
) -> dict:
    ip, user_agent = meta
    token = request.cookies.get(container.settings.session_cookie_name)
    if token:
        container.auth.logout(token, ip=ip, user_agent=user_agent)
    response.delete_cookie(container.settings.session_cookie_name, path="/")
    return {"ok": True}


@router.get("/session", response_model=SessionOut)
async def session(user: CurrentUser) -> SessionOut:
    return SessionOut(user=UserOut.from_domain(user))
