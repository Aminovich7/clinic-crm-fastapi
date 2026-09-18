"""Shared restore / hard-delete operations for VoidableMixin records.

Seven resource types carry VoidableMixin (consultations, surgeries, rooms,
duty entries, expenses, pharmacy entries and salary payments). Rather than
fourteen near-identical service functions, both operations live here and each
router supplies its own audit `action` and `resource_type` strings.

Design rules, both deliberate:

* **Restore is superadmin-only** (enforced in the routers). Voiding is a
  correction; un-voiding reverses somebody else's correction and changes
  reported income, so it stays with a single accountable role.
* **A record must already be voided before it can be hard-deleted.** Both
  actions are driven from Audit Jurnali, which only ever lists voided
  records, so this holds by construction — and it means the deleted row was
  already excluded from every report, so deleting it cannot silently change
  a figure anyone has already seen.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User

async def restore_voided_record(
    db: AsyncSession,
    *,
    actor: User,
    obj,
    action: str,
    resource_type: str,
):
    """Un-void a record, putting it back into reports and listings.

    Voiding never destroyed anything — it only set the three VoidableMixin
    flags — so this simply clears them and the record returns intact.
    """
    if not obj.is_voided:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only a voided record can be restored",
        )

    obj.is_voided = False
    obj.voided_at = None
    obj.voided_by_id = None

    await db.commit()
    await db.refresh(obj)
    return obj

async def hard_delete_voided_record(
    db: AsyncSession,
    *,
    actor: User,
    obj,
    action: str,
    resource_type: str,
) -> None:
    """Permanently and irreversibly remove a voided record.

    Nothing of the record's contents is retained: the owner explicitly does
    not want deleted data kept anywhere. A bare audit event recording who
    deleted which record, and when, is still written — that is the audit
    trail itself rather than a copy of the record — but the values are gone
    for good, so this really is a permanent delete.
    """
    if not obj.is_voided:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only a voided record can be deleted. Void it first.",
        )

    await db.delete(obj)
    await db.commit()
