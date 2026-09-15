from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Reuses the same Redis instance as the rest of the app (see core/redis.py)
# instead of opening a second connection pool just for rate limiting.
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.redis_url)
