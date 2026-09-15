from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.audit.router import router as audit_router
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.redis import redis_client
from app.db.session import AsyncSessionLocal, get_db
from app.doctors.router import router as doctors_router
from app.finance.router import router as finance_router
from app.users.router import router as users_router
from app.users.seed import seed_superadmin


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        await seed_superadmin(db)
    yield


app = FastAPI(title="clinic-crm", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/health")
async def health():
    db_status = "ok"
    redis_status = "ok"

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    try:
        await redis_client.ping()
    except Exception:
        redis_status = "error"

    overall_ok = db_status == "ok" and redis_status == "ok"

    payload = {
        "status": "ok" if overall_ok else "error",
        "db": db_status,
        "redis": redis_status,
    }

    if not overall_ok:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=503, content=payload)

    return payload


app.include_router(users_router)
app.include_router(doctors_router)
app.include_router(finance_router)
app.include_router(audit_router)
