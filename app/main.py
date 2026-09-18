from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles as _StaticFiles
from starlette.types import Scope
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.users.dependencies import get_optional_current_user
from app.users.models import User
from app.users.router import router as users_router
from app.users.seed import seed_superadmin
from app.web.router import router as web_router


class StaticFiles(_StaticFiles):
    """Forces revalidation on every static asset request.

    Without an explicit Cache-Control header, browsers apply heuristic
    caching to /static/js/*.js and can keep serving a stale script for a
    long time after a deploy, even across normal (non-hard) reloads — this
    has already caused confusion twice (see plan.md Session 10 and 12).
    `no-cache` still lets the browser cache the file, it just forces a
    conditional GET (If-None-Match/If-Modified-Since) on every request, so
    an unchanged file still gets a cheap 304 while a changed one is never
    served stale.
    """

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        await seed_superadmin(db)
    yield


# /docs, /redoc and /openapi.json are off unless DOCS_ENABLED is set. They
# otherwise let anyone enumerate every route, including the superadmin-only
# ones, before authenticating.
app = FastAPI(
    title="clinic-crm",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# The app serves its own scripts, styles and fonts and talks to nothing but
# itself, so every directive can be 'self' with no exceptions. Keeping it
# that strict is what makes it worth having: it means an injected <script>,
# an inline handler or a call out to an attacker-controlled host is refused
# by the browser even if something did slip past the output escaping in
# nav.js's escapeHtml(). frame-ancestors 'none' is the modern
# X-Frame-Options and stops the UI being framed for clickjacking.
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "form-action 'self'",
        "base-uri 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
    ]
)

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    # Redundant with frame-ancestors for current browsers, kept for older ones.
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    # This app has no use for any of them; denying them costs nothing.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
}


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)

    for header, value in SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)

    # HSTS only makes sense once TLS actually terminates in front of the app,
    # and sending it over plain HTTP on localhost would pin developers into
    # https://localhost. Gate it on the request actually having arrived over
    # TLS (directly, or per a trusted proxy's X-Forwarded-Proto).
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    is_https = request.url.scheme == "https" or (
        settings.trust_proxy_headers and forwarded_proto.split(",")[0].strip() == "https"
    )
    if is_https:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/health")
async def health(
    verbose: bool = False,
    viewer: User | None = Depends(get_optional_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Liveness probe.

    Deliberately unauthenticated so container orchestrators and uptime checks
    can reach it, but the per-component breakdown is not public: which of
    Postgres or Redis is down is useful reconnaissance for an attacker, and a
    bare up/down is all an anonymous caller needs. `?verbose=1` with a valid
    access token returns the detail.
    """
    db_status = "ok"
    redis_status = "ok"

    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    try:
        await redis_client.ping()
    except Exception:
        redis_status = "error"

    overall_ok = db_status == "ok" and redis_status == "ok"
    payload = {"status": "ok" if overall_ok else "error"}

    if verbose and viewer is not None:
        payload |= {"db": db_status, "redis": redis_status}

    if not overall_ok:
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
