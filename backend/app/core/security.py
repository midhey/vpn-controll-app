"""Пароли, токены сессий и шифрование секретов при хранении."""

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
    """Небезопасный dev-only fallback. Никогда не использовать вне local."""

    _prefix = "plain$"

    def encrypt(self, value: str) -> str:
        return self._prefix + base64.b64encode(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value.startswith(self._prefix):
            raise ValueError("unknown secret box format")
        return base64.b64decode(value[len(self._prefix) :]).decode("utf-8")


class FernetSecretBox(SecretBox):
    """Authenticated encryption for credentials persisted by the control plane."""

    _prefix = "fernet$"

    def __init__(self, key: str) -> None:
        try:
            from cryptography.fernet import Fernet

            self._fernet = Fernet(key.encode("ascii"))
        except (ImportError, ValueError, UnicodeEncodeError) as exc:
            raise ValueError("ENCRYPTION_KEY must be a valid Fernet key") from exc

    def encrypt(self, value: str) -> str:
        return self._prefix + self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        if not value.startswith(self._prefix):
            raise ValueError("unknown secret box format")
        try:
            return self._fernet.decrypt(value[len(self._prefix) :].encode("ascii")).decode("utf-8")
        except Exception as exc:  # InvalidToken intentionally has no useful public detail.
            raise ValueError("secret cannot be decrypted") from exc
