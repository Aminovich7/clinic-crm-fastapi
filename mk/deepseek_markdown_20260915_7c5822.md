# Changes in Project vs. Reference Guides

This document tracks every deliberate deviation between your live implementation and the two reference documents:

- **Auth guide** — `v2-clinic_auth_guide.md`
- **Main logic guide** — `clinic_crm_fastapi_main_logic_guide_v2.md`

Each entry notes **what changed**, **where it lives**, and **why**, so future-you (or a reviewer) can see the reasoning without re-reading the whole conversation.

---

## 1. Auth module deviations

### 1.1 Enum names kept as `UserRoleEnum` / `UserStatusEnum`

| Guide used | Your project uses |
| :--- | :--- |
| `RoleEnum` | `UserRoleEnum` |
| `UserStatus` | `UserStatusEnum` |

**Where:** `app/users/models.py`

**Why:** Both names are valid. Your existing auth code already shipped with the longer names, and renaming would ripple through `dependencies.py`, `service.py`, `router.py`, and every import in `finance/`. Not worth the churn.

**Impact on finance guide:** The finance guide assumed `UserRoleEnum` (see section 32, 33, 173), so no changes needed there.

---

### 1.2 Added `full_name` field to `User`

| Guide | Your model |
| :--- | :--- |
| No `full_name` | `full_name: Mapped[str] = mapped_column(String(50))` |

**Where:** `app/users/models.py`

**Why:** Business need — every user should have a display name, not just a username. This is used by:

- `update_assistant_credentials` (schema accepts `full_name`)
- `update_manager_credentials`
- Any future audit log / report that wants "who did this" to be human-readable

**Impact:** `UserOut` schema should include `full_name` so the frontend can display it. Check that `app/users/schemas.py` reflects this.

---

### 1.3 `Uuid(as_uuid=True)` instead of postgresql-dialect `UUID`

| Guide imported | Your model imports |
| :--- | :--- |
| `from sqlalchemy.dialects.postgresql import UUID` | `from sqlalchemy import Uuid` |

**Where:** `app/users/models.py`

**Why:** `sqlalchemy.Uuid` is the **dialect-agnostic** version (SQLAlchemy 2.0+). It works on PostgreSQL, SQLite, and MySQL. The dialect-specific `postgresql.UUID` is only useful if you need PostgreSQL-only features (e.g., `UUID` with specific server-side defaults). You don't. Using the generic version keeps the models portable and avoids an unnecessary PostgreSQL import.

**Impact on finance guide:** Same convention applied to Finance models — `created_by_id`, `voided_by_id` are `Uuid(as_uuid=True)`, not `postgresql.UUID`.

---

### 1.4 `Base` lives in `app.db.base`, not `app.core.database`

| Auth guide path | Your project path |
| :--- | :--- |
| `app/core/database.py` (with `Base`, `engine`, `AsyncSessionLocal`, `get_db`) | `app/db/base.py` (`Base`) and `app/db/session.py` (engine, session) |

**Where:** `app/db/base.py`, `app/db/session.py`, `app/db/all_models.py`

**Why:** This matches the **main logic guide's** prescribed folder structure (section 4). The auth guide was written before the main logic guide formalized the layout, so its `core/database.py` is superseded.

**Import convention everywhere:**

```python
from app.db.base import Base
from app.db.session import get_db
```

Not:

```python
from app.core.database import Base   # do NOT use
```

---

### 1.5 `authenticate_user` also checks `status`

**Status:** Kept as in guide.

Your `authenticate_user` returns `None` if `user.status != UserStatusEnum.APPROVED`. This matches the auth guide section 12. No change — noting it here because it interacts with the finance blocking behavior (a blocked assistant cannot log in, so they can never create finance records).

---

## 2. Finance module deviations

### 2.1 `minus_beshming` — schema default only, no model default, no server default

| Layer | Guide | Your project |
| :--- | :--- | :--- |
| Pydantic schema | `default=Decimal("5000.00")` | `default=Decimal("5000")` ✅ kept |
| SQLAlchemy model | `default=Decimal("5000.00")`, `server_default="5000.00"` | **removed** |
| PostgreSQL column | `server_default='5000.00'` | **removed** |

**Where:** `app/finance/schemas.py` (default kept), `app/finance/models.py` (defaults removed), migration file (no `server_default`).

**Why:**

1. You explicitly did **not** want a `server_default` — so no DB-level default.
2. Keeping the default in the **schema only** gives the frontend a clean way to:
   - Omit the field → server injects 5000
   - Send `null` → stored as `NULL` (treated as `0` in calculations)
   - Send any explicit value → stored as-is
3. Single source of truth for the default (the schema), so if the business later changes it, there's one place to edit.

**Impact:**

- Migration file must **not** contain `server_default="5000"` for `minus_beshming`.
- `app/finance/models.py` `minus_beshming` column has `nullable=True` but no `default=` and no `server_default=`.

---

### 2.2 Money precision: `Numeric(12, 0)` instead of `Numeric(10, 2)`

| Field | Guide | Your project |
| :--- | :--- | :--- |
| `amount` | `Numeric(10, 2)` | `Numeric(12, 0)` |
| `minus_beshming` | `Numeric(10, 2)` | `Numeric(12, 0)` |
| `surgery_expense` | `Numeric(10, 2)` | `Numeric(12, 0)` |
| `doctor_percent` | `Numeric(5, 2)` | `Numeric(5, 2)` (unchanged) |

**Where:** `app/finance/models.py`

**Why:** Uzbek soums are whole numbers. No decimals needed. `Numeric(12, 0)` stores up to 12 digits with **zero** decimal places, giving room for larger amounts (up to 999,999,999,999) without a fractional part.

**Impact on `calculations.py`:**

`money()` must quantize to **integer**, not two decimals:

```python
ONE = Decimal("1")
HUNDRED = Decimal("100")

def money(value: Decimal) -> Decimal:
    return value.quantize(ONE, rounding=ROUND_HALF_UP)
```

Not:

```python
TWO_PLACES = Decimal("0.01")
def money(value): return value.quantize(TWO_PLACES, ...)   # WRONG for this project
```

**Impact on schemas:** `Decimal` fields remain `Decimal`, but responses will naturally be integers (e.g., `"47500"` not `"47500.00"`).

**Impact on tests:** Any test expecting `Decimal("47500.00")` must expect `Decimal("47500")` instead.

---

### 2.3 Consultation table name — typo fix

During autogenerate, the log showed:

```
Detected added table 'consulations'    # typo
```

The model had `__tablename__ = "consulations"` (missing the "t").

**Fix:** Change to `__tablename__ = "consultations"` **before** running `alembic upgrade head`.

**Verification:** After regeneration, the log should say `Detected added table 'consultations'`.

---

### 2.4 `system_settings` table and dynamic default — **not implemented**

The guide discussed an optional dynamic default flow (system_settings table + superadmin API to change the global `minus_beshming` default). You decided **not** to implement this. So:

- ❌ No `SystemSetting` model in `app/finance/models.py`
- ❌ No `get_global_minus_beshming_default()` helper in `app/finance/service.py`
- ❌ No `PATCH /admin/settings/minus-beshming-default` endpoint
- ❌ No `system_settings` table in the migration

**Why:** Simpler. The default is hardcoded in the schema. If the business later needs a dynamic default, a new migration + endpoint can be added without touching existing code.

---

## 3. Permission changes

### 3.1 Assistants can read doctors

| Endpoint | Guide | Your project |
| :--- | :--- | :--- |
| `GET /doctors` | SUPERADMIN, MANAGER | **+ ASSISTANT** |
| `GET /doctors/{id}` | SUPERADMIN, MANAGER | **+ ASSISTANT** |
| `POST /doctors` | SUPERADMIN, MANAGER | unchanged |
| `PATCH /doctors/{id}` | SUPERADMIN, MANAGER | unchanged |
| `DELETE /doctors/{id}` | SUPERADMIN, MANAGER | unchanged |

**Where:** `app/doctors/router.py`

**Why:** Assistants need to pick a doctor when creating a receipt. Rather than building a dedicated `/doctors/options` endpoint (guide section 31), you chose **Option A** — reuse the existing read endpoints. Simpler, fewer endpoints, and doctor data isn't sensitive.

**Long-term note:** If doctor data later becomes sensitive or the payload is too heavy, migrate to a narrow `/doctors/options` endpoint. For now, this is fine.

---

### 3.2 `DELETE /doctors/{doctor_id}` — physical delete is allowed

**Where:** `app/doctors/router.py` + `app/doctors/service.py`

**Design:**

```python
# service.py
async def delete_doctor(
    db: AsyncSession,
    doctor: Doctor,
) -> None:
    await db.delete(doctor)
    await db.commit()

# router.py
@router.delete("/{doctor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doctor_endpoint(
    doctor_id: int,
    _: User = Depends(require_roles(UserRoleEnum.SUPERADMIN, UserRoleEnum.MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    doctor = await get_doctor(db, doctor_id)
    await delete_doctor(db, doctor)
```

**Why physical delete for doctors but not finance:**

- Doctors are **not** financial records. They have no `is_voided` field and no audit-sensitive payload.
- The `ON DELETE SET NULL` FK on `consultations.doctor_id`, `surgeries.doctor_id`, `rooms.doctor_id` **preserves financial history** — the receipt keeps its `amount`, `doctor_percent`, etc., and simply loses the link to the doctor.
- The guide (section 67) explicitly endorses this pattern.

**Contrast:** Finance records (`consultations`, `surgeries`, `rooms`) use **void/archive**, not physical delete (guide section 99). Do **not** add `DELETE /consultations/{id}` endpoints.

---

## 4. Testing / verification decisions

### 4.1 Rounding tests must expect integers

Old guide test (section 73):

```python
assert result["doctor_share"] == Decimal("47500.00")
```

Your version:

```python
assert result["doctor_share"] == Decimal("47500")
```

Same for all calculation tests, `expense`, `clinic_profit`, etc.

### 4.2 Migration inspection checklist additions

Beyond the guide's section 70 checklist, verify:

- [ ] `consultations` (not `consulations`) table name
- [ ] `Numeric(12, 0)` on money columns (not `Numeric(10, 2)`)
- [ ] No `server_default` on `minus_beshming`
- [ ] No `default=` on `minus_beshming` in the model

---

## 5. Open items / pending decisions

| # | Item | Status | Notes |
| :--- | :--- | :--- | :--- |
| 1 | Money fields in `ConsultationCreate`/`Read` typed as `Decimal` — but should the JSON serializer emit ints or `"47500"` strings? | Open | FastAPI serializes `Decimal` as string by default. Decide whether the frontend prefers ints (send `"47500"` and parse) or keep as string. |
| 2 | Should `minus_beshming` responses be `null` or `0` when not set on the record? | Open | Schema currently allows `Decimal \| None`. Consider whether to coerce `NULL → 0` at read time for cleaner frontend code. |
| 3 | Audit logging | Deferred | Not in scope now (guide section 117). Actor is already available in every service call. |
| 4 | `system_settings` dynamic default | Skipped | Can be added later as a new migration without touching existing code. |
| 5 | `/doctors/options` endpoint | Skipped | Reuse existing `GET /doctors` for now. Migrate later if needed. |

---

## 6. Summary table — quick reference

| Area | Guide assumed | Your project | Reason |
| :--- | :--- | :--- | :--- |
| Enum names | `RoleEnum`, `UserStatus` | `UserRoleEnum`, `UserStatusEnum` | Kept existing auth names |
| User model extra field | — | `full_name` | Business need |
| UUID type | `postgresql.UUID` | `sqlalchemy.Uuid` | Dialect-agnostic |
| Base location | `core/database.py` | `db/base.py`, `db/session.py` | Main logic guide's layout |
| `minus_beshming` defaults | model + server | schema only | Your explicit choice |
| Money precision | `Numeric(10, 2)` | `Numeric(12, 0)` | Uzbek soums (no decimals) |
| `money()` rounding | `Decimal("0.01")` | `Decimal("1")` | Integer soums |
| Assistant read doctors | No (or via `/options`) | Yes, reuse `GET /doctors` | Simpler MVP |
| Doctor DELETE | Allowed | 204 No Content | REST convention |
| `system_settings` | Optional | Not implemented | Simpler, deferrable |
| Finance DELETE | Not allowed (void instead) | Not allowed | Guide respected |

---

*Last updated: when the doctor vertical slice was completed and finance models were first generated.*