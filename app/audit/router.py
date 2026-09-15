import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import AuditLogRead
from app.audit.service import list_audit_logs
from app.common.pagination import PaginatedResponse
from app.db.session import get_db
from app.users.dependencies import require_roles
from app.users.models import User, UserRoleEnum

router = APIRouter(tags=["Audit"])


@router.get("/audit-logs", response_model=PaginatedResponse[AuditLogRead])
async def list_audit_logs_endpoint(
    actor_id: uuid.UUID | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    try:
        items, total = await list_audit_logs(
            db,
            actor_id=actor_id,
            resource_type=resource_type,
            resource_id=resource_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    pages = (total + page_size - 1) // page_size

    return PaginatedResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
    )
