"""Shared restore / hard-delete operations for VoidableMixin records.

Seven resource types carry VoidableMixin (consultations, surgeries, rooms,
duty entries, expenses, pharmacy entries and salary payments). Rather than
fourteen near-identical service functions, both operations live here.

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

def forbid_edit_if_voided(obj) -> None:
    """409 if `obj` is voided. Call before applying any update.

    Voiding is how a record is taken out of circulation, and Audit Jurnali —
    the only page that surfaces voided records — offers exactly two actions on
    them, restore and delete. Editing was never offered by the UI (every
    "Tahrirlash" button renders behind `!record.is_voided`) but nothing
    stopped a PATCH from reaching the service, and a record edited while
    voided comes back with different figures than the ones that were voided
    if a superadmin later restores it.
    """
    if obj.is_voided:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A voided record cannot be edited. Restore it first.",
        )

def hide_if_voided(obj, detail: str):
    """404 if `obj` is voided, else `obj`.

    The list endpoints all filter `is_voided == False`, so a voided record is
    already absent from every listing; the single-record getters returned it
    anyway. Voided records are surfaced through /voided-records
    (superadmin-only) and nowhere else, so this keeps the two consistent.

    Deliberately applied at the router, not inside `get_*_or_404`: restore and
    delete both load their target through those helpers and must keep seeing
    voided rows.
    """
    if obj.is_voided:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail)
    return obj

async def restore_voided_record(
    db: AsyncSession,
    *,
    actor: User,
    obj,
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
) -> None:
    """Permanently and irreversibly remove a voided record.

    Nothing of the record's contents is retained anywhere: the owner
    explicitly does not want deleted data kept. There is no audit-log copy
    either — the audit_logs table was dropped in migration e1a4c7d90b26 —
    so once this returns, the record's values are gone for good.
    """
    if not obj.is_voided:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only a voided record can be deleted. Void it first.",
        )

    await db.delete(obj)
    await db.commit()
