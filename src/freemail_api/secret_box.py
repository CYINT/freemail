from __future__ import annotations

import base64
from hashlib import sha256

from cryptography.fernet import Fernet, InvalidToken


class SecretBoxConfigurationError(RuntimeError):
    pass


class SecretBoxDecryptionError(ValueError):
    pass


def encrypt_text(value: str, secret: str | None) -> str:
    return _fernet(secret).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str, secret: str | None) -> str:
    try:
        return _fernet(secret).decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as error:
        raise SecretBoxDecryptionError("secret could not be decrypted") from error


def _fernet(secret: str | None) -> Fernet:
    if not secret:
        raise SecretBoxConfigurationError("secret is not configured")
    key = base64.urlsafe_b64encode(sha256(secret.encode("utf-8")).digest())
    return Fernet(key)
