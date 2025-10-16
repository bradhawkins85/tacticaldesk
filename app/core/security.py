from __future__ import annotations

import bcrypt

BCRYPT_MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(ValueError):
    """Raised when attempting to hash a password that exceeds bcrypt's limits."""


def _ensure_password_size(password: str) -> None:
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"Password exceeds bcrypt's maximum supported size of {BCRYPT_MAX_PASSWORD_BYTES} bytes when encoded in UTF-8."
        )


def hash_password(password: str) -> str:
    _ensure_password_size(password)
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        _ensure_password_size(password)
    except PasswordTooLongError:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False
