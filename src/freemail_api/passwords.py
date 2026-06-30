from argon2 import PasswordHasher


_HASHER = PasswordHasher()


def hash_initial_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password_hash(password_hash: str, password: str) -> bool:
    return _HASHER.verify(password_hash, password)
