"""Пин алгоритма подписи: должен байт-в-байт совпадать с agent/internal/httpapi/auth.go."""

from __future__ import annotations

import hashlib
import hmac

from app.services.agent_client import peer_path, sign_agent_request


def reference_signature(
    secret: bytes, method: str, path: str, timestamp: str, body: bytes
) -> str:
    """Независимая реализация формулы из auth.go для сверки."""
    body_hash = hashlib.sha256(body).hexdigest()
    payload = f"{method}\n{path}\n{timestamp}\n{body_hash}"
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def test_signature_matches_reference_empty_body():
    args = (b"topsecret", "GET", "/status", "2026-07-07T10:00:00Z", b"")
    assert sign_agent_request(*args) == reference_signature(*args)


def test_signature_matches_reference_with_body_and_query():
    args = (
        b"another-secret",
        "POST",
        "/peers?verbose=1",
        "2026-07-07T10:00:00Z",
        b'{"name":"Alice iPhone"}',
    )
    assert sign_agent_request(*args) == reference_signature(*args)


def test_signature_depends_on_each_part():
    base = (b"s", "GET", "/peers", "2026-07-07T10:00:00Z", b"")
    signature = sign_agent_request(*base)
    assert signature != sign_agent_request(b"s", "POST", "/peers", base[3], b"")
    assert signature != sign_agent_request(b"s", "GET", "/status", base[3], b"")
    assert signature != sign_agent_request(b"s", "GET", "/peers", "2026-07-07T10:00:01Z", b"")
    assert signature != sign_agent_request(b"s", "GET", "/peers", base[3], b"x")


def test_peer_path_percent_encodes_base64_key():
    # Ключи WireGuard — base64 с `+`, `/`, `=`: кодируются как один сегмент.
    assert peer_path("abc+def/ghi=") == "/peers/abc%2Bdef%2Fghi%3D"
    assert peer_path("plain") == "/peers/plain"
