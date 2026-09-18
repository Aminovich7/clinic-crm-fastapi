import uuid

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession


from app.db.session import get_db
from app.core.redis import is_token_blocklisted

from app.core.security import TokenType, decode_token
from app.users.models import UserRoleEnum, UserStatusEnum, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token, expected_type=TokenType.ACCESS)

    except jwt.PyJWTError:
        raise credentials_exception

    user_id = payload.get("sub")
    token_version = payload.get("ver")
    jti = payload.get("jti")

    if user_id is None or token_version is None or jti is None:
        raise credentials_exception

    # A token whose `sub` is not a UUID is simply not one of ours. Parsing it
    # unguarded raised ValueError and surfaced as a 500; the honest answer to
    # an unusable token is the same 401 as any other failed validation.
    try:
        user_uuid = uuid.UUID(str(user_id))
    except (ValueError, AttributeError, TypeError):
        raise credentials_exception

    if await is_token_blocklisted(jti):
        raise credentials_exception

    user = await db.get(User, user_uuid)

    if user is None:
        raise credentials_exception

    # Compared against the database row, not a Redis mirror of it: this row is
    # loaded on every request anyway, so the cache saved nothing and could
    # only drift. See the note in app/core/redis.py.
    if token_version != user.token_version or user.status != UserStatusEnum.APPROVED:
        raise credentials_exception

    return user


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """The current user, or None when the caller is anonymous or invalid.

    For endpoints that must answer anonymous callers but reveal more to
    authenticated ones — /health being the only one today. Never raises, so
    it cannot turn a public endpoint into a 401.
    """
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None

    try:
        return await get_current_user(token=token.strip(), db=db)
    except Exception:
        return None


def require_roles(*roles: UserRoleEnum):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You dont have permission to perform this action",
            )

        return current_user

    return checker
