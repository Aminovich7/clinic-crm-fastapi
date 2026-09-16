from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.audit.router import router as audit_router
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.redis import redis_client
from app.db.session import AsyncSessionLocal, get_db
from app.duty.router import router as duty_router
from app.expenses.router import router as expenses_router
from app.finance.router import router as finance_router
from app.pharmacy.router import router as pharmacy_router
from app.salary.router import router as salary_router
from app.staff.router import router as staff_router
from app.users.router import router as users_router
from app.users.seed import seed_superadmin
from app.web.router import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        await seed_superadmin(db)
    yield


app = FastAPI(title="clinic-crm", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


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
app.include_router(staff_router)
app.include_router(finance_router)
app.include_router(duty_router)
app.include_router(salary_router)
app.include_router(pharmacy_router)
app.include_router(expenses_router)
app.include_router(audit_router)
app.include_router(web_router)
