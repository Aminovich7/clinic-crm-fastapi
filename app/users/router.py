import uuid
from datetime import datetime, timezone


import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.core.redis import blocklist_token, is_token_blocklisted
from app.core.security import TokenType, decode_token
from app.users.dependencies import get_current_user, oauth2_scheme, require_roles
from app.users.models import UserRoleEnum, UserStatusEnum, User
from app.users.schemas import (
    AssistantCreate,
    AssistantCredentialsUpdate,
    ManagerCreate,
    ManagerCredentialsUpdate,
    RefreshRequest,
    SuperAdminCredentialsUpdate,
    TokenPair,
    UserOut,
)

from app.users.service import (
    authenticate_user,
    create_assistant,
    create_manager,
    update_assistant_credentials,
    update_manager_credentials,
    issue_token_pair,
    set_user_status,
    update_superadmin_credentials,
)

router = APIRouter(tags=["Auth"])


@router.post("/auth/login", response_model=TokenPair)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Login yoki Parol xato, Adminga murojaat qiling!",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token, refresh_token = issue_token_pair(user)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh_token(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(
            body.refresh_token,
            expected_type=TokenType.REFRESH,
        )

    except jwt.PyJWTError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token"
        )

    if await is_token_blocklisted(payload["jti"]):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Refresh token has been revoked"
        )

    user = await db.get(User, uuid.UUID(payload["sub"]))

    if (
        user is None
        or user.status != UserStatusEnum.APPROVED
        or user.token_version != payload["ver"]
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Refresh token no longer valid"
        )

    now_ts = int(datetime.now(timezone.utc).timestamp())
    await blocklist_token(payload["jti"], payload["exp"] - now_ts)

    access_token, refresh_token = issue_token_pair(user)

    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: RefreshRequest | None = None,
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
):

    access_payload = decode_token(token, expected_type=TokenType.ACCESS)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    await blocklist_token(access_payload["jti"], access_payload["exp"] - now_ts)

    if body and body.refresh_token:
        try:
            refresh_payload = decode_token(
                body.refresh_token, expected_type=TokenType.REFRESH
            )
            await blocklist_token(
                refresh_payload["jti"],
                refresh_payload["exp"] - now_ts,
            )

        except jwt.PyJWTError:
            pass


@router.get("/auth/me", response_model=UserOut)
async def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post(
    "/users/managers", response_model=UserOut, status_code=status.HTTP_201_CREATED
)
async def create_manager_endpoint(
    data: ManagerCreate,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):

    return await create_manager(db, actor, data)


@router.patch("/users/managers/{manager_id}", response_model=UserOut)
async def update_manager_endpoint(
    manager_id: uuid.UUID,
    data: ManagerCredentialsUpdate,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    manager = await db.get(User, manager_id)

    if manager is None or manager.role != UserRoleEnum.MANAGER:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Manager not found")

    if actor.role == UserRoleEnum.MANAGER and actor.id != manager.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Managers can only update their own profile",
        )

    return await update_manager_credentials(db, actor=actor, assistant=manager, data=data)


@router.post("/users/managers/{manager_id}/block", response_model=UserOut)
async def block_manager_endpoint(
    manager_id: uuid.UUID,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    manager = await db.get(User, manager_id)
    if manager is None or manager.role != UserRoleEnum.MANAGER:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Manager not found")
    return await set_user_status(
        db,
        actor=actor,
        target=manager,
        new_status=UserStatusEnum.BLOCKED,
    )


@router.post("/users/managers/{manager_id}/unblock", response_model=UserOut)
async def unblock_manager_endpoint(
    manager_id: uuid.UUID,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    manager = await db.get(User, manager_id)
    if manager is None or manager.role != UserRoleEnum.MANAGER:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Manager not found")
    return await set_user_status(
        db,
        actor=actor,
        target=manager,
        new_status=UserStatusEnum.APPROVED,
    )


@router.post(
    "/users/assistants", response_model=UserOut, status_code=status.HTTP_201_CREATED
)
async def create_assistant_endpoint(
    data: AssistantCreate,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)),
    db: AsyncSession = Depends(get_db),
):

    return await create_assistant(db, actor, data)


@router.patch("/users/assistants/{assistant_id}", response_model=UserOut)
async def update_assistant_endpoint(
    assistant_id: uuid.UUID,
    data: AssistantCredentialsUpdate,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    assistant = await db.get(User, assistant_id)
    if assistant is None or assistant.role != UserRoleEnum.ASSISTANT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assistant not found")

    return await update_assistant_credentials(db, actor=actor, assistant=assistant, data=data)


@router.post("/users/assistants/{assistant_id}/block", response_model=UserOut)
async def block_assistant_endpoint(
    assistant_id: uuid.UUID,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    assistant = await db.get(User, assistant_id)
    if assistant is None or assistant.role != UserRoleEnum.ASSISTANT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assistant not found")
    return await set_user_status(
        db,
        actor=actor,
        target=assistant,
        new_status=UserStatusEnum.BLOCKED,
    )


@router.post("/users/assistants/{assistant_id}/unblock", response_model=UserOut)
async def unblock_assistant_endpoint(
    assistant_id: uuid.UUID,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    assistant = await db.get(User, assistant_id)
    if assistant is None or assistant.role != UserRoleEnum.ASSISTANT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assistant not found")
    return await set_user_status(
        db,
        actor=actor,
        target=assistant,
        new_status=UserStatusEnum.APPROVED,
    )


@router.patch(
    "/users/superadmin",
    response_model=UserOut,
)
async def superadmin_credentials_update_endpoint(
    data: SuperAdminCredentialsUpdate,
    actor: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await update_superadmin_credentials(
        db,
        actor,
        data,
    )
