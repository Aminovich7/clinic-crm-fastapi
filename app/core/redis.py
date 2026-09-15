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
