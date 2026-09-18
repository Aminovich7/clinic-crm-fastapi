import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.users.models import UserRoleEnum, UserStatusEnum, User
from app.users.schemas import (
    AssistantCreate,
    AssistantCredentialsUpdate,
    ManagerCreate,
    ManagerCredentialsUpdate,
    SuperAdminCredentialsUpdate,
)

async def authenticate_user(
    db: AsyncSession, username: str, password: str
) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or user.status != UserStatusEnum.APPROVED:
        return None
    if not verify_password(password, user.hashed_password):
        return None

    return user

def issue_token_pair(user: User) -> tuple[str, str]:
    access = create_access_token(
        user_id=user.id,
        role=user.role.value,
        token_version=user.token_version,
    )
    refresh = create_refresh_token(
        user_id=user.id,
        role=user.role.value,
        token_version=user.token_version,
    )
    return access, refresh

async def _require_username_available(
    db: AsyncSession, username: str, *, exclude_user_id: uuid.UUID | None = None
) -> None:
    """409 if `username` is taken by anyone other than `exclude_user_id`.

    users.username carries a unique index, so without this check a rename
    onto an existing name surfaced as an IntegrityError from the commit —
    a 500 where the honest answer is 409. Creation passes no
    exclude_user_id; an update excludes the row being renamed so that
    re-submitting an unchanged username is not a conflict with itself.
    """
    stmt = select(User).where(User.username == username)
    if exclude_user_id is not None:
        stmt = stmt.where(User.id != exclude_user_id)

    if (await db.execute(stmt)).scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Username already taken",
        )

async def _create_user(
    db: AsyncSession,
    *,
    actor: User,
    username: str,
    full_name: str,
    password: str,
    role: UserRoleEnum,
) -> User:
    await _require_username_available(db, username)

    user = User(
        username=username,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=role,
        status=UserStatusEnum.APPROVED,
        created_by_id=actor.id,
    )
    db.add(user)
    await db.flush()

    await db.commit()
    await db.refresh(user)
    return user

async def list_users_by_role(
    db: AsyncSession,
    *,
    role: UserRoleEnum,
    page: int,
    page_size: int,
) -> tuple[list[User], int]:
    base_stmt = select(User).where(User.role == role)

    total = (
        await db.execute(select(func.count()).select_from(base_stmt.subquery()))
    ).scalar_one()

    stmt = (
        base_stmt.order_by(User.full_name, User.username)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(stmt)).scalars().all()
    return list(items), total

async def create_manager(db: AsyncSession, actor: User, data: ManagerCreate) -> User:
    return await _create_user(
        db,
        actor=actor,
        username=data.username,
        full_name=data.full_name,
        password=data.password,
        role=UserRoleEnum.MANAGER,
    )

async def create_assistant(
    db: AsyncSession, actor: User, data: AssistantCreate
) -> User:
    return await _create_user(
        db,
        actor=actor,
        username=data.username,
        full_name=data.full_name,
        password=data.password,
        role=UserRoleEnum.ASSISTANT,
    )

async def _update_credentials(
    db: AsyncSession,
    *,
    target: User,
    username: str | None,
    full_name: str | None,
    password: str | None,
) -> User:
    """Apply a credential change and bump token_version if anything changed.

    Bumping token_version is what invalidates the user's existing sessions.
    It is now a single database write, committed atomically with the
    credential change itself: there is no second copy in Redis that a crash
    between the two writes could leave disagreeing with it. See the note in
    app/core/redis.py.
    """
    changed = False

    if username and username != target.username:
        await _require_username_available(db, username, exclude_user_id=target.id)
        target.username = username
        changed = True
    if full_name and full_name != target.full_name:
        target.full_name = full_name
        changed = True
    if password:
        target.hashed_password = hash_password(password)
        changed = True

    if changed:
        target.token_version += 1

    await db.commit()
    await db.refresh(target)
    return target

async def update_assistant_credentials(
    db: AsyncSession,
    *,
    actor: User,
    assistant: User,
    data: AssistantCredentialsUpdate,
) -> User:
    return await _update_credentials(
        db,
        target=assistant,
        username=data.username,
        full_name=data.full_name,
        password=data.password,
    )

async def update_manager_credentials(
    db: AsyncSession,
    *,
    actor: User,
    assistant: User,
    data: ManagerCredentialsUpdate,
) -> User:
    return await _update_credentials(
        db,
        target=assistant,
        username=data.username,
        full_name=data.full_name,
        password=data.password,
    )

async def set_user_status(
    db: AsyncSession,
    *,
    actor: User,
    target: User,
    new_status: UserStatusEnum,
) -> User:
    if target.status == new_status:
        return target

    target.status = new_status
    # Bumping the version drops the user's live sessions immediately; the
    # status check in get_current_user would catch them anyway, but this also
    # invalidates any refresh token they still hold.
    target.token_version += 1

    await db.commit()
    await db.refresh(target)
    return target

async def update_superadmin_credentials(
    db: AsyncSession,
    superadmin: User,
    data: SuperAdminCredentialsUpdate,
) -> User:
    return await _update_credentials(
        db,
        target=superadmin,
        username=data.superadmin_username,
        full_name=None,
        password=data.superadmin_password,
    )