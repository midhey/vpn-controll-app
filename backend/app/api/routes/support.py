from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container, CurrentUser
from app.schemas.support import ContributionOut, SupportHistoryOut, SupportViewOut

router = APIRouter(prefix="/support", tags=["support"])


@router.get("", response_model=SupportViewOut)
async def support_view(user: CurrentUser, container: Container) -> SupportViewOut:
    return SupportViewOut(**container.support.view_for(user))


@router.get("/history", response_model=SupportHistoryOut)
async def support_history(user: CurrentUser, container: Container) -> SupportHistoryOut:
    visible, items = container.support.history_for(user)
    return SupportHistoryOut(
        visible=visible, items=[ContributionOut.from_domain(c) for c in items]
    )
