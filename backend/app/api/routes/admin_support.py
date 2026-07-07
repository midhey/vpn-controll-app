from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container, CurrentAdmin
from app.schemas.support import SupportSettingsOut, SupportSettingsUpdateIn

router = APIRouter(prefix="/admin/support-settings", tags=["admin:support"])


@router.get("", response_model=SupportSettingsOut)
async def get_settings(admin: CurrentAdmin, container: Container) -> SupportSettingsOut:
    return SupportSettingsOut.from_domain(container.support.get_settings())


@router.patch("", response_model=SupportSettingsOut)
async def update_settings(
    body: SupportSettingsUpdateIn, admin: CurrentAdmin, container: Container
) -> SupportSettingsOut:
    settings = container.support.update_settings(admin, body.model_dump(exclude_unset=True))
    return SupportSettingsOut.from_domain(settings)
