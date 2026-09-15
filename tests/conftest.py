import os

# Must run before anything imports app.core.config, which reads these once at
# module import. The limiter is backed by shared Redis state, so leaving it on
# makes any suite performing more than five logins a minute fail on the sixth
# with a 429 that has nothing to do with the code under test.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.users.seed import seed_superadmin


@pytest_asyncio.fixture(autouse=True)
async def _reset_redis_connections():
    """Drop Redis connections between tests.

    app.core.redis builds one module-level client, whose pool binds its
    sockets to whichever event loop first used them. pytest-asyncio runs each
    test on a fresh loop, so without this the second test to touch Redis —
    any test that logs in, logs out or blocks a user — fails with "attached to
    a different loop" / "Event loop is closed" rather than anything to do with
    the code under test. Closing the pool after each test makes the next one
    reconnect on its own loop.
    """
    yield

    from app.core.redis import redis_client

    try:
        await redis_client.aclose()
    except Exception:
        pass


@pytest_asyncio.fixture
async def test_db_engine():
    """Create an in-memory test database engine."""
    # No hardcoded fallback: the previous default embedded a real database
    # password in this file, which then travelled into git history.
    test_db_url = os.getenv("TEST_DATABASE_URL")
    if not test_db_url:
        raise RuntimeError(
            "TEST_DATABASE_URL is not set. It is defined in .env and passed "
            "into the container by docker-compose; run the suite with "
            "'docker compose exec web python -m pytest'."
        )

    engine = create_async_engine(
        test_db_url,
        echo=False,
        poolclass=NullPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async session for tests."""
    from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionType

    async_session = AsyncSession(test_db_engine, expire_on_commit=False)

    yield async_session

    await async_session.rollback()
    await async_session.close()


@pytest_asyncio.fixture
async def seeded_db(test_db) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database with superadmin seeded."""
    await seed_superadmin(test_db)
    yield test_db


@pytest_asyncio.fixture
async def test_client(test_db_engine) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client that uses the test database."""
    async def override_get_db():
        async with AsyncSession(test_db_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


async def _login(client: AsyncClient, username: str, password: str) -> str:
    """Log in over HTTP and return the access token."""
    response = await client.post(
        "/auth/login", data={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def superadmin_token(test_client, seeded_db) -> str:
    # Read from settings rather than hardcoded here: the literal password used
    # to sit in this file, which put it in git history alongside the copy in
    # .env.example.
    return await _login(
        test_client, settings.superadmin_username, settings.superadmin_password
    )


@pytest_asyncio.fixture
async def authenticated_client(test_client, superadmin_token) -> AsyncClient:
    """Provide an authenticated HTTP client as superadmin."""
    test_client.headers["Authorization"] = f"Bearer {superadmin_token}"
    return test_client


def auth(token: str) -> dict[str, str]:
    """Authorization header for a one-off request as a specific user."""
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def role_tokens(test_client, superadmin_token) -> dict[str, str]:
    """A live access token for each of the three roles.

    Created through the real endpoints rather than by inserting rows, so the
    tokens exercise the same creation path the application uses.
    """
    tokens = {"superadmin": superadmin_token}

    created = await test_client.post(
        "/users/managers",
        headers=auth(superadmin_token),
        json={"username": "test-manager", "full_name": "Test Manager", "password": "manager-pw-123"},
    )
    assert created.status_code == 201, created.text
    tokens["manager"] = await _login(test_client, "test-manager", "manager-pw-123")

    created = await test_client.post(
        "/users/assistants",
        headers=auth(superadmin_token),
        json={"username": "test-assistant", "full_name": "Test Assistant", "password": "assistant-pw-123"},
    )
    assert created.status_code == 201, created.text
    tokens["assistant"] = await _login(test_client, "test-assistant", "assistant-pw-123")

    return tokens


@pytest.fixture
def anyio_backend():
    """Use asyncio backend for pytest-asyncio."""
    return "asyncio"
