from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import VoidedRecordRead
from app.audit.voided import list_voided_records
from app.common.pagination import PaginatedResponse
from app.db.session import get_db
from app.users.dependencies import require_roles
from app.users.models import User, UserRoleEnum

router = APIRouter(tags=["Audit"])


@router.get("/voided-records", response_model=PaginatedResponse[VoidedRecordRead])
async def list_voided_records_endpoint(
    resource_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_roles(UserRoleEnum.SUPERADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Every voided record across all seven voidable tables.

    "Bekor qilingan yozuvlar" is the only place voided records are surfaced,
    so this is the one listing that spans them.
    """
    items, total = await list_voided_records(
        db,
        resource_type=resource_type,
        page=page,
        page_size=page_size,
    )

    pages = (total + page_size - 1) // page_size

    return PaginatedResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=pages,
    )
