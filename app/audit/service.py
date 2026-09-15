from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.users.models import User

CLINIC_TZ = ZoneInfo("Asia/Tashkent")


async def record_audit_event(
    db: AsyncSession,
    *,
    actor: User | None,
    action: str,
    resource_type: str,
    resource_id,
    metadata: dict | None = None,
) -> None:
    """Queue an audit row on the given session. Caller commits.

    Must be called before the mutation's commit() so the audit row and the
    business row land in the same transaction.
    """
    db.add(
        AuditLog(
            actor_id=actor.id if actor is not None else None,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            metadata_=metadata,
        )
    )


async def list_audit_logs(
    db: AsyncSession,
    *,
    actor_id=None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int,
    page_size: int,
) -> tuple[list[AuditLog], int]:
    stmt = select(AuditLog)

    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)

    if resource_type is not None:
        stmt = stmt.where(AuditLog.resource_type == resource_type)

    if resource_id is not None:
        stmt = stmt.where(AuditLog.resource_id == resource_id)

    if date_from is not None and date_to is not None and date_from > date_to:
        raise ValueError("date_from cannot be after date_to")

    if date_from is not None:
        start = datetime.combine(date_from, time.min, tzinfo=CLINIC_TZ)
        stmt = stmt.where(AuditLog.created_at >= start)

    if date_to is not None:
        end_exclusive = datetime.combine(
            date_to + timedelta(days=1), time.min, tzinfo=CLINIC_TZ
        )
        stmt = stmt.where(AuditLog.created_at < end_exclusive)

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    return list(result.scalars().all()), total
