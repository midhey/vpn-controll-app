from __future__ import annotations

from pydantic import BaseModel

from app.domain.models import ServerNode, ServerStatus


class ServerOut(BaseModel):
    """Вид сервера для обычного участника — без хостов и учёток агента."""

    id: str
    name: str
    region_note: str | None = None
    status: ServerStatus

    @classmethod
    def from_domain(cls, node: ServerNode) -> ServerOut:
        return cls(id=node.id, name=node.name, region_note=node.region_note, status=node.status)
