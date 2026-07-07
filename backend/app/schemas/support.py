from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.models import SupportContribution, SupportSettings


class SupportViewOut(BaseModel):
    """GET /support: для «невидимых» участников — только visible=false."""

    visible: bool
    title: str | None = None
    description: str | None = None
    sbp_phone: str | None = None
    bank_name: str | None = None
    extra_contact: str | None = None
    monthly_cost_amount: float | None = None
    reserve_amount: float | None = None


class ContributionOut(BaseModel):
    id: str
    amount: float
    currency: str
    period_label: str | None = None
    comment: str | None = None
    recorded_at: datetime

    @classmethod
    def from_domain(cls, contribution: SupportContribution) -> ContributionOut:
        return cls(
            id=contribution.id,
            amount=contribution.amount,
            currency=contribution.currency,
            period_label=contribution.period_label,
            comment=contribution.comment,
            recorded_at=contribution.recorded_at,
        )


class SupportHistoryOut(BaseModel):
    visible: bool
    items: list[ContributionOut]


class ContributionCreateIn(BaseModel):
    amount: float = Field(gt=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    period_label: str | None = Field(default=None, max_length=64)
    comment: str | None = Field(default=None, max_length=500)


class SupportSettingsOut(BaseModel):
    title: str
    description: str
    sbp_phone: str | None = None
    bank_name: str | None = None
    extra_contact: str | None = None
    monthly_cost_amount: float | None = None
    reserve_amount: float | None = None
    is_enabled: bool
    updated_at: datetime | None = None

    @classmethod
    def from_domain(cls, settings: SupportSettings) -> SupportSettingsOut:
        return cls(
            title=settings.title,
            description=settings.description,
            sbp_phone=settings.sbp_phone,
            bank_name=settings.bank_name,
            extra_contact=settings.extra_contact,
            monthly_cost_amount=settings.monthly_cost_amount,
            reserve_amount=settings.reserve_amount,
            is_enabled=settings.is_enabled,
            updated_at=settings.updated_at,
        )


class SupportSettingsUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    sbp_phone: str | None = None
    bank_name: str | None = None
    extra_contact: str | None = None
    monthly_cost_amount: float | None = Field(default=None, ge=0)
    reserve_amount: float | None = Field(default=None, ge=0)
    is_enabled: bool | None = None
