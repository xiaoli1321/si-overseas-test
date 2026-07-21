from datetime import UTC, datetime, timedelta
import secrets
import string
from typing import Any

import jwt
from passlib.context import CryptContext

from src.core.config import get_settings
from src.core.exceptions import UnauthorizedError

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Exclude visually ambiguous characters (0/O, 1/l/I) so a manager can read a
# generated password aloud or over chat without transcription errors.
_PASSWORD_ALPHABET = "".join(
    c for c in (string.ascii_letters + string.digits) if c not in "0O1lI"
)


def generate_password(length: int = 12) -> str:
    """Generate a random, human-transcribable password for account resets."""
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()
        ),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired access token.") from exc
    if not payload.get("sub"):
        raise UnauthorizedError("Invalid access token subject.")
    return payload
