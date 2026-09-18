import redis.asyncio as redis

from app.core.config import settings

redis_client = redis.from_url(settings.redis_url, decode_responses=True)

# There is deliberately no token_version cache here any more.
#
# It used to mirror users.token_version into Redis, but get_current_user
# loads the User row on every request regardless, so the cache never saved a
# query — it could only ever disagree with the row that had just been
# fetched. Whichever order the two writes went in, one crash between them
# left the two permanently out of step: cache-then-commit could lock a user
# out of an account whose password had not actually changed, and
# commit-then-cache could keep an old session alive after a password change.
# The database row is now the single source of truth, which removes the
# divergence rather than choosing which way it fails.
#
# The blocklist below is different and stays: it holds jti values that exist
# nowhere else, and losing it degrades gracefully (a revoked token becomes
# valid again only until it expires, which is 15 minutes for an access token).
_BLOCKLIST_PREFIX = "blocklist:"


async def blocklist_token(jti: str, ttl_seconds: int) -> None:
    if ttl_seconds > 0:
        await redis_client.set(f"{_BLOCKLIST_PREFIX}{jti}", "1", ex=ttl_seconds)


async def is_token_blocklisted(jti: str) -> bool:
    return await redis_client.exists(f"{_BLOCKLIST_PREFIX}{jti}") == 1
