import uuid


from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from app.audit.service import record_audit_event
from app.core.redis import set_cached_token_version
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


async def _create_user(
    db: AsyncSession,
    *,
    actor: User,
    username: str,
    full_name: str,
    password: str,
    role: UserRoleEnum,
) -> User:
    existing = await db.execute(
        select(User).where(
            User.username == username,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Username already taken",
        )

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

    await record_audit_event(
        db,
        actor=actor,
        action=f"create_{role.value}",
        resource_type="user",
        resource_id=user.id,
    )

    await db.commit()
    await db.refresh(user)
    return user


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


async def update_assistant_credentials(
    db: AsyncSession,
    *,
    actor: User,
    assistant: User,
    data: AssistantCredentialsUpdate,
) -> User:
    changed_fields = []
    if data.username:
        assistant.username = data.username
        changed_fields.append("username")
    if data.full_name:
        assistant.full_name = data.full_name
        changed_fields.append("full_name")
    if data.password:
        assistant.hashed_password = hash_password(data.password)
        changed_fields.append("password")

    if changed_fields:
        assistant.token_version += 1
        await set_cached_token_version(str(assistant.id), assistant.token_version)

        await record_audit_event(
            db,
            actor=actor,
            action="update_assistant_credentials",
            resource_type="user",
            resource_id=assistant.id,
            metadata={"changed_fields": changed_fields},
        )

    await db.commit()
    await db.refresh(assistant)
    return assistant


async def update_manager_credentials(
    db: AsyncSession,
    *,
    actor: User,
    assistant: User,
    data: ManagerCredentialsUpdate,
) -> User:
    changed_fields = []
    if data.username:
        assistant.username = data.username
        changed_fields.append("username")
    if data.full_name:
        assistant.full_name = data.full_name
        changed_fields.append("full_name")
    if data.password:
        assistant.hashed_password = hash_password(data.password)
        changed_fields.append("password")

    if changed_fields:
        assistant.token_version += 1
        await set_cached_token_version(str(assistant.id), assistant.token_version)

        await record_audit_event(
            db,
            actor=actor,
            action="update_manager_credentials",
            resource_type="user",
            resource_id=assistant.id,
            metadata={"changed_fields": changed_fields},
        )

    await db.commit()
    await db.refresh(assistant)
    return assistant


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
    target.token_version += 1
    await set_cached_token_version(str(target.id), target.token_version)

    await record_audit_event(
        db,
        actor=actor,
        action="block_user" if new_status == UserStatusEnum.BLOCKED else "unblock_user",
        resource_type="user",
        resource_id=target.id,
    )

    await db.commit()
    await db.refresh(target)
    return target


async def update_superadmin_credentials(
    db: AsyncSession,
    superadmin: User,
    data: SuperAdminCredentialsUpdate,
) -> User:

    if data.superadmin_username:

        superadmin.username = data.superadmin_username

    if data.superadmin_password:
        superadmin.hashed_password = hash_password(data.superadmin_password)

    if data.superadmin_username or data.superadmin_password:
        superadmin.token_version += 1
        await set_cached_token_version(str(superadmin.id), superadmin.token_version)

    await db.commit()
    await db.refresh(superadmin)

    return superadmin