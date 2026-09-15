import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

import jwt
from app.core.config import settings

from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()  # Argon2, per OWASP


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def _create_token(
    *,
    subject: str,
    role: str,
    token_version: int,
    token_type: TokenType,
    expires_delta: timedelta
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "ver": token_version,
        "type": token_type.value,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(*, user_id: uuid.UUID, role: str, token_version: int) -> str:
    return _create_token(
        subject=str(user_id),
        role=role,
        token_version=token_version,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(*, user_id: uuid.UUID, role: str, token_version: int) -> str:
    return _create_token(
        subject=str(user_id),
        role=role,
        token_version=token_version,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: TokenType)->dict:
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type.value:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload