"""Клиент Go-агента на VPS-узлах.

Единственная точка общения бэкенда с агентом. Подпись повторяет
agent/internal/httpapi/auth.go:

    body_hash = sha256(body)
    payload   = METHOD \n escaped_path_with_query \n timestamp_rfc3339 \n hex(body_hash)
    signature = hex(hmac_sha256(secret, payload))

Критичные детали контракта:
- подписывается percent-encoded путь ровно в том виде, в котором он уходит
  на провод (агент сверяет с Go EscapedPath() + raw query);
- ключи WireGuard — base64 с `+`, `/`, `=`: в DELETE-пути ключ кодируется
  как один сегмент (quote(key, safe=""));
- таймстамп — текущий UTC RFC3339, допуск агента ±60 секунд;
- у POST /peers успех — 201; JSON строгий (DisallowUnknownFields);
- ошибки агента: {"error": "...", "status": ..., "status_text": "..."}.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import quote, unquote

from app.core.errors import AppError, ErrorCode
from app.core.security import SecretBox
from app.domain.models import ServerNode

HEADER_KEY_ID = "X-Agent-Key-Id"
HEADER_TIMESTAMP = "X-Agent-Timestamp"
HEADER_SIGNATURE = "X-Agent-Signature"

SKEW_MESSAGE = "timestamp outside allowed skew"


def rfc3339_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sign_agent_request(
    secret: bytes, method: str, escaped_path_with_query: str, timestamp: str, body: bytes
) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    payload = "\n".join([method.upper(), escaped_path_with_query, timestamp, body_hash])
    return hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def peer_path(public_key: str) -> str:
    """Путь DELETE /peers/{key}: ключ кодируется как один сегмент, `/` -> %2F."""
    return "/peers/" + quote(public_key, safe="")


class AgentTransportError(Exception):
    """Сетевая ошибка: узел не ответил."""


@dataclass(slots=True)
class AgentResponse:
    status_code: int
    payload: Any


class AgentTransport(Protocol):
    async def request(
        self, *, base_url: str, method: str, path: str, headers: dict[str, str], body: bytes
    ) -> AgentResponse: ...


@dataclass(slots=True)
class AgentIssueResult:
    public_key: str
    client_ip: str
    config: str
    vpn_url: str


class AgentClient:
    def __init__(self, transport: AgentTransport, secret_box: SecretBox) -> None:
        self._transport = transport
        self._secret_box = secret_box

    async def health(self, node: ServerNode) -> dict[str, Any]:
        response = await self._request(node, "GET", "/health", signed=False)
        return self._expect(response, 200, node)

    async def status(self, node: ServerNode) -> dict[str, Any]:
        response = await self._request(node, "GET", "/status")
        return self._expect(response, 200, node)

    async def peers(self, node: ServerNode) -> list[dict[str, Any]]:
        response = await self._request(node, "GET", "/peers")
        return self._expect(response, 200, node)

    async def issue_peer(
        self,
        node: ServerNode,
        *,
        name: str,
        dns: list[str] | None = None,
        endpoint_host: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentIssueResult:
        # Строго документированные поля: у агента DisallowUnknownFields.
        request_body: dict[str, Any] = {"name": name}
        if dns:
            request_body["dns"] = dns
        if endpoint_host:
            request_body["endpoint_host"] = endpoint_host
        if metadata:
            request_body["metadata"] = metadata
        response = await self._request(node, "POST", "/peers", body_obj=request_body)
        payload = self._expect(response, 201, node)
        return AgentIssueResult(
            public_key=payload["public_key"],
            client_ip=payload["client_ip"],
            config=payload["config"],
            vpn_url=payload["vpn_url"],
        )

    async def revoke_peer(self, node: ServerNode, public_key: str) -> dict[str, Any]:
        response = await self._request(node, "DELETE", peer_path(public_key))
        return self._expect(response, 200, node)

    async def _request(
        self,
        node: ServerNode,
        method: str,
        path: str,
        *,
        body_obj: Any = None,
        signed: bool = True,
    ) -> AgentResponse:
        body = b""
        headers: dict[str, str] = {}
        if body_obj is not None:
            body = json.dumps(body_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if signed:
            if not node.agent_key_id or not node.agent_secret_encrypted:
                raise AppError(
                    ErrorCode.SECRET_REQUIRED,
                    "Для узла не настроен доступ к агенту",
                    status=400,
                    details={"server_node_id": node.id},
                )
            secret = self._secret_box.decrypt(node.agent_secret_encrypted).encode("utf-8")
            timestamp = rfc3339_utc_now()
            headers[HEADER_KEY_ID] = node.agent_key_id
            headers[HEADER_TIMESTAMP] = timestamp
            headers[HEADER_SIGNATURE] = sign_agent_request(secret, method, path, timestamp, body)
        try:
            return await self._transport.request(
                base_url=node.agent_base_url, method=method, path=path, headers=headers, body=body
            )
        except AgentTransportError as exc:
            raise AppError(
                ErrorCode.AGENT_UNAVAILABLE,
                "Узел сейчас недоступен",
                status=502,
                details={"server_node_id": node.id, "reason": str(exc)},
            ) from exc

    def _expect(self, response: AgentResponse, expected_status: int, node: ServerNode) -> Any:
        if response.status_code == expected_status:
            return response.payload
        agent_message = ""
        if isinstance(response.payload, dict):
            agent_message = str(response.payload.get("error", ""))
        details: dict[str, Any] = {
            "server_node_id": node.id,
            "agent_status": response.status_code,
            "agent_message": agent_message,
        }
        if response.status_code >= 500:
            raise AppError(
                ErrorCode.AGENT_UNAVAILABLE, "Узел ответил ошибкой", status=502, details=details
            )
        if SKEW_MESSAGE in agent_message:
            details["hint"] = "Часы бэкенда и узла разошлись больше чем на 60 секунд (NTP)"
        raise AppError(
            ErrorCode.AGENT_REJECTED, "Узел отклонил запрос", status=502, details=details
        )


class HttpxAgentTransport:
    """Реальный транспорт (AGENT_MODE=http).

    Таймауты по плану: connect 3s; read 15s для health/status/peers и 30s для
    issue/revoke (на узле выполняются docker exec и синхронизация конфига).
    TODO при интеграции: держать общий пул соединений вместо клиента на запрос
    и проверить, что httpx не перекодирует %2F в пути (подпись должна совпасть).
    """

    def __init__(self) -> None:
        import httpx  # локальный импорт: fake-режим работает без httpx

        self._httpx = httpx

    async def request(
        self, *, base_url: str, method: str, path: str, headers: dict[str, str], body: bytes
    ) -> AgentResponse:
        httpx = self._httpx
        is_peer_mutation = method in {"POST", "DELETE"} and path.startswith("/peers")
        timeout = httpx.Timeout(
            connect=3.0, read=30.0 if is_peer_mutation else 15.0, write=10.0, pool=5.0
        )
        try:
            async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
                response = await client.request(method, path, headers=headers, content=body)
        except httpx.HTTPError as exc:
            raise AgentTransportError(str(exc)) from exc
        try:
            payload = response.json() if response.content else None
        except ValueError:
            payload = {"error": response.text[:500]}
        return AgentResponse(status_code=response.status_code, payload=payload)


@dataclass(slots=True)
class _FakePeer:
    public_key: str
    name: str
    client_ip: str


@dataclass(slots=True)
class _FakeNodeState:
    peers: dict[str, _FakePeer] = field(default_factory=dict)
    next_ip_octet: int = 2


class FakeAgentTransport:
    """Имитация Go-агента (AGENT_MODE=fake, по умолчанию).

    Состояние отдельное на каждый agent_base_url, поэтому несколько «узлов»
    живут независимо. Подпись не проверяет (алгоритм закреплён юнит-тестами),
    но последний запрос сохраняет в last_request — удобно для тестов.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, _FakeNodeState] = {}
        self.last_request: dict[str, Any] | None = None

    async def request(
        self, *, base_url: str, method: str, path: str, headers: dict[str, str], body: bytes
    ) -> AgentResponse:
        self.last_request = {
            "base_url": base_url,
            "method": method,
            "path": path,
            "headers": dict(headers),
            "body": bytes(body),
        }
        state = self._nodes.setdefault(base_url, _FakeNodeState())
        if method == "GET" and path == "/health":
            return AgentResponse(200, {"status": "ok", "version": "0.2.0"})
        if method == "GET" and path == "/status":
            return AgentResponse(200, self._status_payload(state))
        if method == "GET" and path == "/peers":
            return AgentResponse(200, [self._peer_view(p) for p in state.peers.values()])
        if method == "POST" and path == "/peers":
            return self._issue(state, body)
        if method == "DELETE" and path.startswith("/peers/"):
            public_key = unquote(path.removeprefix("/peers/"))
            return self._revoke(state, public_key)
        return AgentResponse(
            404, {"error": "not found", "status": 404, "status_text": "Not Found"}
        )

    def _issue(self, state: _FakeNodeState, body: bytes) -> AgentResponse:
        try:
            request = json.loads(body.decode("utf-8"))
        except ValueError:
            return AgentResponse(
                400, {"error": "invalid JSON", "status": 400, "status_text": "Bad Request"}
            )
        public_key = base64.b64encode(secrets.token_bytes(32)).decode("ascii")
        client_ip = f"10.8.1.{state.next_ip_octet}"
        state.next_ip_octet += 1
        peer = _FakePeer(
            public_key=public_key, name=str(request.get("name", "")), client_ip=client_ip
        )
        state.peers[public_key] = peer
        dns = request.get("dns") or ["1.1.1.1", "8.8.8.8"]
        endpoint_host = request.get("endpoint_host") or "203.0.113.10"
        config = (
            "[Interface]\n"
            f"Address = {client_ip}/32\n"
            f"DNS = {', '.join(dns)}\n"
            "PrivateKey = fake-client-private-key\n"
            "Jc = 6\nJmin = 10\nJmax = 50\n\n"
            "[Peer]\n"
            "PublicKey = fake-server-public-key\n"
            "PresharedKey = fake-preshared-key\n"
            "AllowedIPs = 0.0.0.0/0, ::/0\n"
            f"Endpoint = {endpoint_host}:51820\n"
        )
        vpn_url = "vpn://" + base64.urlsafe_b64encode(
            f"fake:{public_key}:{client_ip}".encode("utf-8")
        ).decode("ascii").rstrip("=")
        return AgentResponse(
            201,
            {
                "public_key": public_key,
                "client_ip": client_ip,
                "config": config,
                "vpn_url": vpn_url,
            },
        )

    def _revoke(self, state: _FakeNodeState, public_key: str) -> AgentResponse:
        if public_key not in state.peers:
            return AgentResponse(
                404, {"error": "peer not found", "status": 404, "status_text": "Not Found"}
            )
        del state.peers[public_key]
        return AgentResponse(200, {"revoked": True, "public_key": public_key})

    def _status_payload(self, state: _FakeNodeState) -> dict[str, Any]:
        return {
            "container": "amnezia-awg2",
            "container_running": True,
            "container_image": "amneziavpn/amnezia-wg:fake",
            "container_created": "2026-01-01T00:00:00Z",
            "interface": "awg0",
            "runtime_interface": "awg0",
            "runtime_public_key": "fake-server-public-key",
            "listen_port": "51820",
            "config_path": "/opt/amnezia/awg/awg0.conf",
            "config_exists": True,
            "clients_table_path": "/opt/amnezia/awg/clientsTable",
            "peer_count_config": len(state.peers),
            "peer_count_runtime": len(state.peers),
        }

    def _peer_view(self, peer: _FakePeer) -> dict[str, Any]:
        return {
            "public_key": peer.public_key,
            "name": peer.name,
            "allowed_ips_config": [f"{peer.client_ip}/32"],
            "allowed_ips_runtime": [f"{peer.client_ip}/32"],
            "in_config": True,
            "in_runtime": True,
            "in_clients_table": True,
            "endpoint": "198.51.100.7:54321",
            "latest_handshake": "1 minute, 3 seconds ago",
            "transfer_received": "1.2 MiB",
            "transfer_sent": "3.4 MiB",
        }
