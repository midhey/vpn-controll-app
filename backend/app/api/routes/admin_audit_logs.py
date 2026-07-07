from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import Container, CurrentAdmin
from app.schemas.audit import AuditLogOut

router = APIRouter(prefix="/admin/audit-logs", tags=["admin:audit"])


@router.get("", response_model=list[AuditLogOut])
async def list_audit_logs(
    admin: CurrentAdmin,
    container: Container,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditLogOut]:
    return [AuditLogOut.from_domain(entry) for entry in container.audit.list(limit)]
