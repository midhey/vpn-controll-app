"""Пароли, токены сессий и шифрование секретов при хранении.

Скелет обходится стандартной библиотекой:
- PBKDF2 — временная замена argon2id (`argon2-cffi` подключится вместе
  с прод-зависимостями, интерфейс не изменится);
- PlaintextSecretBox только кодирует base64 и НЕ является защитой —
  при подключении БД заменяется на Fernet (`cryptography`) с ENCRYPTION_KEY.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

PBKDF2_ITERATIONS = 120_000


class PasswordHasher:
    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
        )
        return "pbkdf2_sha256${}${}${}".format(
            PBKDF2_ITERATIONS,
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )

    def verify(self, password: str, stored: str) -> bool:
        try:
            scheme, iterations_raw, salt_b64, digest_b64 = stored.split("$")
            if scheme != "pbkdf2_sha256":
                return False
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(digest_b64)
            actual = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), salt, int(iterations_raw)
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(actual, expected)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """В хранилище живёт только хеш токена, сырой токен — только в куке."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def generate_agent_key_id() -> str:
    return f"backend-{secrets.token_hex(4)}"


def generate_agent_secret() -> str:
    return secrets.token_urlsafe(48)


def generate_password() -> str:
    return secrets.token_urlsafe(10)


class SecretBox:
    """Интерфейс шифрования секретов при хранении (agent secret, SSH-доступ,
    результаты выпуска конфигов)."""

    def encrypt(self, value: str) -> str:
        raise NotImplementedError

    def decrypt(self, value: str) -> str:
        raise NotImplementedError


class PlaintextSecretBox(SecretBox):
    """Заглушка для in-memory скелета: только помечает значение как «упакованное».

    Не защита. Реальная реализация — Fernet с ENCRYPTION_KEY.
    """

    _prefix = "plain$"

    def encrypt(self, value: str) -> str:
        return self._prefix + base64.b64encode(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value.startswith(self._prefix):
            raise ValueError("unknown secret box format")
        return base64.b64decode(value[len(self._prefix) :]).decode("utf-8")
