from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import Container, CurrentUser
from app.core.errors import not_found
from app.schemas.servers import ServerOut

router = APIRouter(prefix="/servers", tags=["servers"])


@router.get("", response_model=list[ServerOut])
async def list_servers(user: CurrentUser, container: Container) -> list[ServerOut]:
    return [ServerOut.from_domain(n) for n in container.servers.list_available()]


@router.get("/{server_id}", response_model=ServerOut)
async def get_server(server_id: str, user: CurrentUser, container: Container) -> ServerOut:
    for node in container.servers.list_available():
        if node.id == server_id:
            return ServerOut.from_domain(node)
    raise not_found("Сервер не найден")
