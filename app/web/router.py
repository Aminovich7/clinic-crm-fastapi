import time

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Web"])
templates = Jinja2Templates(directory="app/templates")

# Cache-busting: appended as ?v=... to every /static/* URL in templates
# (see {{ asset_version }} usage). A fixed Cache-Control header alone
# cannot force an already-cached browser to re-fetch a stale file — it
# only prevents *future* staleness. Changing the URL itself is the only
# way to guarantee a client picks up a change immediately. This value is
# set once at process start, so every deploy/restart (including the dev
# --reload watcher) busts every static asset at once.
templates.env.globals["asset_version"] = str(int(time.time()))


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/dashboard")
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/staff-page")
async def staff_page(request: Request):
    return templates.TemplateResponse(request, "staff.html")


@router.get("/navbatchilik-page")
async def navbatchilik_page(request: Request):
    return templates.TemplateResponse(request, "navbatchilik.html")


@router.get("/salary-page")
async def salary_page(request: Request):
    return templates.TemplateResponse(request, "oyliklar.html")


@router.get("/pharmacy-page")
async def pharmacy_page(request: Request):
    return templates.TemplateResponse(request, "dorixona.html")


@router.get("/expenses-page")
async def expenses_page(request: Request):
    return templates.TemplateResponse(request, "harajatlar.html")


@router.get("/receipts")
async def receipts_page(request: Request):
    return templates.TemplateResponse(request, "receipts.html")


@router.get("/reports")
async def reports_page(request: Request):
    return templates.TemplateResponse(request, "reports.html")


@router.get("/audit-log")
async def audit_log_page(request: Request):
    return templates.TemplateResponse(request, "audit_log.html")


@router.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse(request, "settings.html")


@router.get("/users-page")
async def users_page(request: Request):
    return templates.TemplateResponse(request, "users.html")
