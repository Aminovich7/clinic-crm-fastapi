# Clinic CRM — Authentication & Authorization Guide

Scope: this document covers **only** authentication/authorization — the `users` module, JWT
issuance/validation, role enforcement, and superadmin bootstrapping. Doctors, rooms,
surgeries, and audit-log *writing* are intentionally left out, as you asked. The design
below does leave a couple of small hooks (noted where relevant) so that when you build audit
logging later, you won't have to touch the auth layer again.

---

## 1. Recommended stack (and why)

| Concern | Pick | Why not the "classic" choice |
|---|---|---|
| Web framework | FastAPI (async) | — |
| DB / ORM | PostgreSQL + SQLAlchemy 2.0 async (`asyncpg` driver) | your choice, confirmed |
| Migrations | Alembic | standard companion to SQLAlchemy |
| Password hashing | **pwdlib** with **Argon2** | `passlib` (the library FastAPI's own docs used to recommend) has had no real release since 2020 and is known to break on Python 3.13+. The FastAPI maintainers themselves now point people to `pwdlib`, which wraps Argon2 (OWASP's current recommended algorithm) with a tiny, actively maintained API. |
| JWT encode/decode | **PyJWT** | `python-jose`, the other library that used to show up in tutorials, has been effectively unmaintained since 2021 with open security issues. FastAPI's docs migrated to PyJWT for this reason — smaller surface area, actively maintained, and slightly faster in practice. |
| Session/revocation store | **Redis** (`redis.asyncio`, built into `redis-py` ≥ 4.2 — no separate `aioredis` package needed) | — |
| Settings | `pydantic-settings` | type-safe `.env` loading, integrates natively with FastAPI |

Install list:

```bash
pip install "fastapi[standard]" \
            "sqlalchemy[asyncio]>=2.0" \
            asyncpg \
            alembic \
            pydantic-settings \
            pyjwt \
            "pwdlib[argon2]" \
            "redis>=4.2" \
            python-multipart
```

`python-multipart` is required because the login endpoint uses FastAPI's standard
`OAuth2PasswordRequestForm` (form-encoded `username`/`password`), which lets you test login
directly from Swagger UI's built-in "Authorize" button — useful right now since you have no
frontend yet.

---

## 2. Folder structure

Matches your preference of keeping everything user-related together, similar to a Django
app:

```
app/
├── main.py
├── core/
│   ├── config.py        # env settings
│   ├── database.py       # async engine/session, Base
│   ├── redis.py          # redis client + revocation helpers
│   └── security.py       # password hashing + JWT encode/decode
├── users/
│   ├── __init__.py
│   ├── models.py          # User, RoleEnum
│   ├── schemas.py         # Pydantic request/response models
│   ├── dependencies.py    # get_current_user, require_roles(...)
│   ├── service.py         # business logic
│   ├── router.py          # /auth + /users endpoints
│   └── seed.py            # seed_superadmin()
└── alembic/
```

---

## 3. Environment variables

Add to `.env.example` (and your real `.env`, git-ignored):

```env
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/clinic_crm
REDIS_URL=redis://redis:6379/0

SECRET_KEY=replace_with_output_of_openssl_rand_hex_32
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

SUPERADMIN_USERNAME=superadmin
SUPERADMIN_PASSWORD=change_this_to_a_strong_password
```

Generate a real secret with:

```bash
openssl rand -hex 32
```

Never commit the real `.env` — only `.env.example` with placeholder values.

---

## 4. `core/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    redis_url: str

    secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    superadmin_username: str
    superadmin_password: str


settings = Settings()
```

---

## 5. `core/database.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

---

## 6. Users model — `users/models.py`

```python
import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RoleEnum(str, PyEnum):
    SUPERADMIN = "superadmin"
    MANAGER = "manager"
    ASSISTANT = "assistant"


class UserStatus(str, PyEnum):
    APPROVED = "approved"
    BLOCKED = "blocked"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleEnum] = mapped_column(Enum(RoleEnum, name="user_role"), nullable=False)

    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"), default=UserStatus.APPROVED, nullable=False
    )

    # Bumped whenever this user's password/username changes, or an admin force-revokes
    # their sessions. Any JWT carrying an older "ver" claim is instantly worthless,
    # regardless of its expiry — see section 8 for why this matters.
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Not audit logging itself, but records *who* created the account — costs nothing
    # now and will save you time when you build real logs later.
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_by: Mapped["User | None"] = relationship(remote_side=[id])

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

Notes:
- `username` is the login field (matches "manager can update assistant's username").
- No `email` field — you don't need it since there's no self-registration or password-reset-by-email flow.
- `status` replaces the old plain `is_active` boolean. An enum reads far more clearly in
  code and logs ("assistant was BLOCKED by manager X") than a bare `True`/`False`, and
  leaves room to add more statuses later (e.g. `PENDING`, if you ever add a review step)
  without another schema rewrite.
- New accounts default to `UserStatus.APPROVED` — account creation *is* the approval step
  here, since only a superadmin/manager can create one in the first place and there's no
  separate registration/pending workflow. This satisfies "must be created already approved"
  with zero extra logic.
- `status == BLOCKED` is how a manager/superadmin freezes a profile — see section 12a for
  the blocking mechanism itself, which reuses `token_version` so it takes effect instantly,
  not just on the blocked user's next login attempt.

---

## 7. Alembic setup (brief)

```bash
alembic init alembic
```

In `alembic/env.py`, point it at your models' metadata and use an async-aware migration
runner (SQLAlchemy's standard recipe for async engines):

```python
import asyncio
from sqlalchemy.ext.asyncio import async_engine_from_config
from app.core.database import Base
from app.core.config import settings
from app.users import models  # noqa: F401 — ensures models are registered on Base.metadata

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", settings.database_url)

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    connectable = async_engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.")
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

asyncio.run(run_migrations_online())
```

Then:

```bash
alembic revision --autogenerate -m "create users table"
alembic upgrade head
```

**If you already have data with the old `is_active` column:** autogenerate will produce a
migration that adds `status` and drops `is_active`, but it won't know how to translate
existing rows on its own. Add one line to the generated migration, between the `add_column`
and `drop_column` calls, to backfill it:

```python
from sqlalchemy import table, column, String

users = table("users", column("is_active", None), column("status", String))
op.execute(users.update().where(users.c.is_active == True).values(status="approved"))
op.execute(users.update().where(users.c.is_active == False).values(status="blocked"))
```

Run this once against a copy of your data (or a staging DB) before applying it in
production, so nobody's account silently flips status during the migration.

**Docker note:** make sure your container's entrypoint/command runs `alembic upgrade head`
*before* starting `uvicorn`, since the app's startup lifecycle (section 12) seeds the
superadmin and expects the `users` table to already exist.

---

## 8. Security utilities — `core/security.py`

This is where password hashing and JWT logic live.

```python
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

import jwt
from pwdlib import PasswordHash

from app.core.config import settings

password_hasher = PasswordHash.recommended()  # Argon2, per OWASP


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    return password_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)


def _create_token(*, subject: str, role: str, token_version: int, token_type: TokenType, expires_delta: timedelta) -> str:
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
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: uuid.UUID, role: str, token_version: int) -> str:
    return _create_token(
        subject=str(user_id), role=role, token_version=token_version,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(*, user_id: uuid.UUID, role: str, token_version: int) -> str:
    return _create_token(
        subject=str(user_id), role=role, token_version=token_version,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: TokenType) -> dict:
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != expected_type.value:
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload
```

Key decisions worth understanding, not just copying:

- **`algorithms=[settings.jwt_algorithm]` is explicit**, not inferred from the token. This
  blocks the classic "alg confusion" attack where a forged token tells the library to skip
  verification.
- **`type` claim** stops someone from using a long-lived refresh token as if it were an
  access token.
- **`jti` claim** (a unique token ID) is what lets us revoke *one specific token* on logout
  without touching the user's other sessions.
- **`ver` claim** mirrors the user's `token_version` at the moment the token was issued —
  this is the mechanism for *instant* revocation, covered next.

---

## 9. Redis — revocation strategy — `core/redis.py`

You picked "JWT + Redis blocklist for instant revoke," which is the right call here: a
manager needs to be able to cut an assistant off the moment they change their password or
deactivate them, not wait 15 minutes for an access token to expire naturally.

Two complementary mechanisms, both backed by Redis:

1. **Per-token blocklist** — used for a normal logout. We blocklist that one token's `jti`
   until it would have expired anyway (so the blocklist entry auto-expires and Redis never
   fills up with stale data).
2. **Per-user token version cache** — used when a manager/superadmin changes an assistant's
   password or username, or force-revokes them. Bumping `token_version` invalidates *every*
   token ever issued to that user in one write, without needing to know which tokens exist.
   Postgres (`users.token_version`) is the source of truth; Redis just caches it so we don't
   hit the database on every single request.

```python
import redis.asyncio as redis

from app.core.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)

_VERSION_PREFIX = "user_token_version:"
_BLOCKLIST_PREFIX = "blocklist:"


async def get_cached_token_version(user_id: str) -> int | None:
    value = await redis_client.get(f"{_VERSION_PREFIX}{user_id}")
    return int(value) if value is not None else None


async def set_cached_token_version(user_id: str, version: int) -> None:
    await redis_client.set(f"{_VERSION_PREFIX}{user_id}", version)


async def blocklist_token(jti: str, ttl_seconds: int) -> None:
    if ttl_seconds > 0:
        await redis_client.set(f"{_BLOCKLIST_PREFIX}{jti}", "1", ex=ttl_seconds)


async def is_token_blocklisted(jti: str) -> bool:
    return await redis_client.exists(f"{_BLOCKLIST_PREFIX}{jti}") == 1
```

---

## 10. Schemas — `users/schemas.py`

```python
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.users.models import RoleEnum, UserStatus


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    role: RoleEnum
    status: UserStatus


class ManagerCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)


class AssistantCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8)


class AssistantCredentialsUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64)
    password: str | None = Field(default=None, min_length=8)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
```

---

## 11. Dependencies — `users/dependencies.py`

```python

import uuid

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import get_cached_token_version, is_token_blocklisted, set_cached_token_version
from app.core.security import TokenType, decode_token
from app.users.models import RoleEnum, User, UserStatus

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

    if token_version != current_version or user.status != UserStatus.APPROVED:
        raise credentials_exception

    return user


def require_roles(*roles: RoleEnum):
    """Dependency factory: require_roles(RoleEnum.SUPERADMIN, RoleEnum.MANAGER)"""

    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return checker
```

Important nuance: `get_current_user` re-fetches the user row (role, `status`,
`token_version`) from the database on every request instead of trusting the `role` claim
baked into the token. A JWT is just a signed *claim* — if a manager gets demoted, or a
superadmin blocks an assistant mid-session, you want that to take effect on their very next
request, not whenever their 15-minute token happens to expire.

---

## 12. Service layer — `users/service.py`

```python
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import set_cached_token_version
from app.core.security import create_access_token, create_refresh_token, hash_password, verify_password
from app.users.models import RoleEnum, User, UserStatus
from app.users.schemas import AssistantCreate, AssistantCredentialsUpdate, ManagerCreate


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or user.status != UserStatus.APPROVED:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def issue_token_pair(user: User) -> tuple[str, str]:
    access = create_access_token(user_id=user.id, role=user.role.value, token_version=user.token_version)
    refresh = create_refresh_token(user_id=user.id, role=user.role.value, token_version=user.token_version)
    return access, refresh


async def _create_user(db: AsyncSession, *, actor: User, username: str, password: str, role: RoleEnum) -> User:
    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")

    user = User(
        username=username,
        hashed_password=hash_password(password),
        role=role,
        status=UserStatus.APPROVED,
        created_by_id=actor.id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def create_manager(db: AsyncSession, actor: User, data: ManagerCreate) -> User:
    return await _create_user(db, actor=actor, username=data.username, password=data.password, role=RoleEnum.MANAGER)


async def create_assistant(db: AsyncSession, actor: User, data: AssistantCreate) -> User:
    return await _create_user(db, actor=actor, username=data.username, password=data.password, role=RoleEnum.ASSISTANT)


async def update_assistant_credentials(db: AsyncSession, assistant: User, data: AssistantCredentialsUpdate) -> User:
    if data.username:
        assistant.username = data.username
    if data.password:
        assistant.hashed_password = hash_password(data.password)

    if data.username or data.password:
        # Kill every session issued before this change — the old password/username
        # shouldn't keep working just because the access token hasn't expired yet.
        assistant.token_version += 1
        await set_cached_token_version(str(assistant.id), assistant.token_version)

    await db.commit()
    await db.refresh(assistant)
    return assistant


async def set_user_status(db: AsyncSession, target: User, new_status: UserStatus) -> User:
    """Block or unblock a manager/assistant profile.

    Bumping token_version here — not just flipping the column — is what makes a block take
    effect immediately. Without it, someone already logged in would keep working fine until
    their access token expired naturally (up to ACCESS_TOKEN_EXPIRE_MINUTES later), which
    doesn't satisfy "cannot touch the system until further change."
    """
    if target.status == new_status:
        return target  # no-op — nothing changed, don't bump token_version for nothing

    target.status = new_status
    target.token_version += 1
    await set_cached_token_version(str(target.id), target.token_version)

    await db.commit()
    await db.refresh(target)
    return target
```

Notice `_create_user` never allows creating a `SUPERADMIN` — that role only ever comes from
the bootstrap seed (section 13). Role assignment permissions are enforced one layer up, in
the router, via `require_roles(...)`.

`set_user_status` is intentionally role-agnostic — it works on managers and assistants
alike. Who is *allowed* to call it for which role is enforced entirely in the router (next
section), the same pattern used everywhere else in this guide: service functions do the
data change, routers decide who's allowed to trigger it.

---

## 13. Router — `users/router.py`

```python
import uuid
from datetime import datetime, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.redis import blocklist_token, is_token_blocklisted
from app.core.security import TokenType, decode_token
from app.users.dependencies import get_current_user, oauth2_scheme, require_roles
from app.users.models import RoleEnum, User, UserStatus
from app.users.schemas import (
    AssistantCreate, AssistantCredentialsUpdate, ManagerCreate,
    RefreshRequest, TokenPair, UserOut,
)
from app.users.service import (
    authenticate_user, create_assistant, create_manager,
    issue_token_pair, set_user_status, update_assistant_credentials,
)

router = APIRouter()


@router.post("/auth/login", response_model=TokenPair)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid login or password. Contact the admin!",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token, refresh_token = issue_token_pair(user)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh_tokens(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token, expected_type=TokenType.REFRESH)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired refresh token")

    if await is_token_blocklisted(payload["jti"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token has been revoked")

    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.status != UserStatus.APPROVED or user.token_version != payload["ver"]:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token no longer valid")

    # rotate: retire the old refresh token, issue a brand new pair
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
            refresh_payload = decode_token(body.refresh_token, expected_type=TokenType.REFRESH)
            await blocklist_token(refresh_payload["jti"], refresh_payload["exp"] - now_ts)
        except jwt.PyJWTError:
            pass  # already invalid/expired — nothing to do


@router.get("/auth/me", response_model=UserOut)
async def read_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/users/managers", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_manager_endpoint(
    data: ManagerCreate,
    actor: User = Depends(require_roles(RoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    return await create_manager(db, actor, data)


@router.post("/users/assistants", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_assistant_endpoint(
    data: AssistantCreate,
    actor: User = Depends(require_roles(RoleEnum.SUPERADMIN, RoleEnum.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    return await create_assistant(db, actor, data)


@router.patch("/users/assistants/{assistant_id}", response_model=UserOut)
async def update_assistant_endpoint(
    assistant_id: uuid.UUID,
    data: AssistantCredentialsUpdate,
    actor: User = Depends(require_roles(RoleEnum.SUPERADMIN, RoleEnum.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    assistant = await db.get(User, assistant_id)
    if assistant is None or assistant.role != RoleEnum.ASSISTANT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assistant not found")
    return await update_assistant_credentials(db, assistant, data)


@router.post("/users/assistants/{assistant_id}/block", response_model=UserOut)
async def block_assistant_endpoint(
    assistant_id: uuid.UUID,
    actor: User = Depends(require_roles(RoleEnum.SUPERADMIN, RoleEnum.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    assistant = await db.get(User, assistant_id)
    if assistant is None or assistant.role != RoleEnum.ASSISTANT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assistant not found")
    return await set_user_status(db, assistant, UserStatus.BLOCKED)


@router.post("/users/assistants/{assistant_id}/unblock", response_model=UserOut)
async def unblock_assistant_endpoint(
    assistant_id: uuid.UUID,
    actor: User = Depends(require_roles(RoleEnum.SUPERADMIN, RoleEnum.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    assistant = await db.get(User, assistant_id)
    if assistant is None or assistant.role != RoleEnum.ASSISTANT:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assistant not found")
    return await set_user_status(db, assistant, UserStatus.APPROVED)


@router.post("/users/managers/{manager_id}/block", response_model=UserOut)
async def block_manager_endpoint(
    manager_id: uuid.UUID,
    actor: User = Depends(require_roles(RoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    manager = await db.get(User, manager_id)
    if manager is None or manager.role != RoleEnum.MANAGER:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Manager not found")
    return await set_user_status(db, manager, UserStatus.BLOCKED)


@router.post("/users/managers/{manager_id}/unblock", response_model=UserOut)
async def unblock_manager_endpoint(
    manager_id: uuid.UUID,
    actor: User = Depends(require_roles(RoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    manager = await db.get(User, manager_id)
    if manager is None or manager.role != RoleEnum.MANAGER:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Manager not found")
    return await set_user_status(db, manager, UserStatus.APPROVED)
```

Role rules encoded here, matching your spec exactly:
- Only **superadmin** can create a manager.
- **Superadmin or manager** can create an assistant.
- Only **superadmin or manager** can update an assistant's username/password.
- **Superadmin or manager** can block/unblock an **assistant**.
- Only **superadmin** can block/unblock a **manager** — a manager can't freeze a peer or
  itself out of caution; that power is reserved one level up.
- There is **no** `/auth/register` endpoint anywhere — by design, since you don't want
  self-registration. Every account is created top-down.

---

## 13a. Design notes on blocking

A few decisions worth spelling out, since they're easy to get subtly wrong:

- **Blocking reuses `token_version`, not just the `status` column.** If blocking only
  flipped a column, an assistant already logged in would keep working fine until their
  15-minute access token expired on its own — that's not "cannot touch the system," that's
  "cannot touch the system in 15 minutes." Bumping `token_version` (same mechanism used for
  password changes) invalidates every token they're currently holding on their very next
  request.
- **The login error message is deliberately the same for "wrong password" and "blocked
  account."** `authenticate_user` returns `None` in both cases, and the router always
  responds with `"Invalid login or password. Contact the admin!"` This avoids leaking
  account status to whoever's typing at the login form (a blocked assistant's credentials
  could otherwise be used to probe whether their account still exists), while still telling
  a legitimate user their next step. If you'd rather blocked users see a more specific
  message, that has to happen through a different channel (a manager telling them directly),
  not through the login response.
- **A blocked assistant can't unblock themselves, obviously** — `set_user_status` is only
  reachable through the block/unblock endpoints, which are gated by `require_roles(...)`
  the same way every other admin action in this guide is. There's no path from the
  assistant's own token to that endpoint.
- **Blocking a manager is superadmin-only**, deliberately more restrictive than blocking an
  assistant. This keeps one manager from freezing another out of a dispute, and keeps the
  "who can lock out whom" hierarchy strictly top-down, matching the rest of this guide's
  account-creation rules.

---

## 14. Superadmin bootstrap — `users/seed.py`

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.users.models import RoleEnum, User


async def seed_superadmin(db: AsyncSession) -> None:
    result = await db.execute(select(User).where(User.role == RoleEnum.SUPERADMIN))
    if result.scalar_one_or_none() is not None:
        return  # already seeded — never silently overwrite an existing superadmin

    superadmin = User(
        username=settings.superadmin_username,
        hashed_password=hash_password(settings.superadmin_password),
        role=RoleEnum.SUPERADMIN,
        created_by_id=None,
    )
    db.add(superadmin)
    await db.commit()
```

Deliberately **create-once**: if you change `SUPERADMIN_PASSWORD` in `.env` and redeploy, it
will *not* silently reset the existing superadmin's password — that would be a surprising
and risky side effect on every restart. If you genuinely need to reset it, do that through a
one-off script or a future admin tool, not through boot-time seeding.

---

## 15. Wiring it into `main.py`

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.database import AsyncSessionLocal
from app.users.router import router as users_router
from app.users.seed import seed_superadmin


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        await seed_superadmin(db)
    yield


app = FastAPI(title="Clinic CRM", lifespan=lifespan)
app.include_router(users_router)
```

Run order at container start (make sure your Dockerfile/entrypoint does this):

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Migrations must run before the app starts, since `lifespan` queries the `users` table
immediately on boot.

---

## 16. Testing it without a frontend

Since there's no frontend yet, use FastAPI's auto-generated docs at `/docs`:

1. Hit **Authorize** (top right) — Swagger's built-in OAuth2 form works out of the box
   because `/auth/login` uses `OAuth2PasswordRequestForm`. Log in as the seeded superadmin.
2. Every subsequent request from the docs UI will carry the access token automatically.
3. Try `POST /users/managers` as superadmin → should succeed.
4. Try it again after logging in as a manager (once you've created one) → should get `403`.
5. Test `/auth/refresh` and `/auth/logout` manually via the "Try it out" panel, since Swagger's Authorize button doesn't manage refresh tokens for you.
6. Test blocking end-to-end: log in as an assistant in one browser tab (keep the access
   token), then as a manager in another tab call `POST /users/assistants/{id}/block`. Go
   back to the assistant's tab and try any protected request — it should now fail with 401,
   even though that access token hasn't expired yet. That's the `token_version` bump doing
   its job. Then unblock and confirm login works again.

---

## 17. Production hardening checklist (for later, not blocking now)

- **Rate-limit `/auth/login`** — brute-force protection. Not built here; `slowapi` or a
  reverse-proxy rule are natural fits later.
- **HTTPS everywhere**, even on an internal LAN tool — bearer tokens are only as safe as the
  transport carrying them.
- **Normalize usernames** (lowercase/trim) at the schema or service layer so `Doctor` and
  `doctor` can't become two different-looking accounts.
- **CORS**: not needed today since there's no frontend origin to allow. When you do add one,
  lock `allow_origins` down to that exact origin — don't leave it wildcarded.
- **Account lockout** after N failed logins — a natural follow-up once you have logging in place.

---

## 18. Where this leaves you for audit logging (later)

You mentioned wanting every transaction to show which assistant/manager made it. This auth
layer already gives you everything you'll need for that, with nothing further to build now:

- `require_roles(...)` and `get_current_user` return the acting `User` object in *every*
  protected route — `actor.username` is right there to pass into a future log call.
- `created_by_id` on `User` already tracks who created each account.
- `jti` on every issued token gives you a stable per-session correlation ID if you ever want
  to group actions by login session rather than just by user.
- The block/unblock endpoints already have `actor` (who blocked/unblocked) and `target`
  (who was affected) sitting right next to each other in `set_user_status` — a natural spot
  to drop in `log.write(actor, action="block_user", target=target)` once logging exists. No
  extra fields needed on `User` for this; if you want to know *who* blocked someone, that's
  an audit-log entry, not a new column.

Nothing here needs to change when you build the logging system — you'd just start calling it
from inside your `doctors`/`rooms`/`surgeries` services, passing in the `actor` you already
have from the dependency.

---

## 19. Explicitly out of scope (as requested)

- Doctors, rooms, surgeries — none of that is touched here.
- Writing actual audit log entries — only the groundwork (`created_by_id`, `actor` objects) is in place.
- Rate limiting, CORS config, account lockout — noted above as future work, not implemented.
- Self-registration / password-reset-by-email — deliberately absent; all accounts are created top-down by superadmin/manager.
