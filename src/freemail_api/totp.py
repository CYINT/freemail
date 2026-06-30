from __future__ import annotations

import base64
import hmac
import secrets
import struct
import time
from hashlib import sha1
from urllib.parse import quote


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_uri(*, issuer: str, account: str, secret: str) -> str:
    label = f"{issuer}:{account}"
    return f"otpauth://totp/{quote(label)}?secret={quote(secret)}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"


def verify_totp_code(secret: str, code: str, *, now: int | None = None, window: int = 1) -> bool:
    normalized = "".join(character for character in code if character.isdigit())
    if len(normalized) != 6:
        return False
    active_now = int(time.time()) if now is None else now
    counter = active_now // 30
    for offset in range(-window, window + 1):
        expected = totp_code(secret, counter=counter + offset)
        if hmac.compare_digest(expected, normalized):
            return True
    return False


def totp_code(secret: str, *, counter: int | None = None, now: int | None = None) -> str:
    active_counter = ((int(time.time()) if now is None else now) // 30) if counter is None else counter
    padded_secret = secret.upper() + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded_secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", active_counter), sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"
