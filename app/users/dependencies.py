import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession


from app.db.session import get_db
from app.core.redis import (
    get_cached_token_version,
    is_token_blocklisted,
    set_cached_token_version,
)

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

    if await is_token_blocklisted(jti):
        raise credentials_exception

    current_version = await get_cached_token_version(user_id)
    user = await db.get(User, uuid.UUID(user_id))

    if user is None:
        raise credentials_exception

    if current_version is None:
        current_version = user.token_version

        await set_cached_token_version(user_id, current_version)

    if token_version != current_version or user.status != UserStatusEnum.APPROVED:
        raise credentials_exception

    return user


def require_roles(*roles: UserRoleEnum):
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You dont have permission to perform this action",
            )

        return current_user

    return checker
