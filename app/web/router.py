from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["Web"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/dashboard")
async def dashboard_page(request: Request):
    return templates.TemplateResponse(request, "dashboard.html")


@router.get("/doctors-page")
async def doctors_page(request: Request):
    return templates.TemplateResponse(request, "doctors.html")


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
