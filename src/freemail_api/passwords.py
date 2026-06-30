from argon2 import PasswordHasher
from argon2.exceptions import VerificationError


_HASHER = PasswordHasher()


def hash_initial_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password_hash(password_hash: str, password: str) -> bool:
    try:
        return _HASHER.verify(password_hash, password)
    except VerificationError:
        return False
