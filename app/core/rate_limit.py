from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings


def client_key(request: Request) -> str:
    """The identity the rate limiter counts against.

    `get_remote_address` reads the socket peer, which is correct only when
    clients connect to the app directly. Put a reverse proxy in front without
    accounting for it and every request appears to come from the proxy, so the
    whole clinic shares one bucket and five bad logins lock everybody out.
    Trust the forwarded header unconditionally instead and any client can put
    whatever it likes in X-Forwarded-For and sidestep the limit entirely.

    Neither default is safe for both deployments, so it is an explicit setting
    (TRUST_PROXY_HEADERS) rather than a guess. Only set it when a proxy you
    control *overwrites* X-Forwarded-For rather than appending to it.
    """
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Left-most entry is the original client; the rest are proxies.
            return forwarded.split(",")[0].strip()

    return get_remote_address(request)


# Reuses the same Redis instance as the rest of the app (see core/redis.py)
# instead of opening a second connection pool just for rate limiting.
limiter = Limiter(
    key_func=client_key,
    storage_uri=settings.redis_url,
    # The limiter is shared Redis state, so a test suite doing more than a
    # handful of logins a minute goes flaky against the live counter. Tests
    # set RATE_LIMIT_ENABLED=false; production leaves it on.
    enabled=settings.rate_limit_enabled,
)
