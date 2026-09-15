# Clinic CRM — FastAPI Main Logic Guide
## Production-style implementation of Doctors, Consultations, Surgeries, Rooms, and Reports

> **Purpose:** This guide is the next phase after your completed authentication/authorization layer. It converts the existing Django finance behavior into a clean, async FastAPI + SQLAlchemy 2.0 implementation while teaching the architecture and reasoning behind each decision.
>
> **Important:** This guide assumes your current auth code is already working. It does **not** replace your JWT, Redis, user, or role implementation.

---

# 1. What We Are Building

Your clinic CRM is not really a CRUD project.

The database contains three kinds of financial records:

```text
                    ┌──────────────┐
                    │    Doctor    │
                    └──────┬───────┘
                           │
             ┌─────────────┼─────────────┐
             │             │             │
             ▼             ▼             ▼
      ┌───────────┐ ┌───────────┐ ┌───────────┐
      │Consultation│ │  Surgery  │ │   Room    │
      └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
            │             │             │
            └─────────────┼─────────────┘
                          ▼
                   Section Reports
                          │
                          ▼
                    Total Dashboard
```

The important relationship is:

```text
records
   ↓
business calculations
   ↓
section reports
   ↓
total report
```

That means we must **not** put the business formulas directly inside route handlers.

The architecture will be:

```text
HTTP request
    ↓
Router
    ↓
Authentication / role dependency
    ↓
Service
    ↓
Repository-style SQLAlchemy query code
    ↓
PostgreSQL
    ↓
Service result
    ↓
Pydantic response schema
    ↓
HTTP response
```

The existing project architecture already defines `app.db.base`, `app.db.session`, `app.db.all_models`, `app.users`, `app.core.security`, and `app.core.redis`. Keep those boundaries rather than creating another database base/session/auth system.

---

# 2. The Rules We Must Preserve

These rules come directly from the existing project requirements:

- Doctors and finance records use integer auto-increment IDs to reduce storage/index overhead. User IDs remain UUIDs as already implemented in the auth layer.
- Clinic timezone is `Asia/Tashkent`.
- Reports use the business `date`, not `created_at`.
- Date ranges are inclusive.
- Money uses PostgreSQL `NUMERIC`.
- Python calculations use `Decimal`.
- Money is calculated/represented to two decimal places.
- Doctor percentage is between `0` and `100`.
- Consultation type is either `korik` or `qaytakorik`.
- `minus_beshming` is optional and currently defaults to `5000`.
- Room records have no expense.
- Doctor deletion must not delete financial history.
- Finance records require `created_by_id` because assistants can only see records they created.
- Financial records should be voided/archived rather than physically deleted.
- Superadmin sees and manages everything.
- Manager can manage doctors and finance records according to the existing permissions.
- Assistant can create finance records and read only their own records.
- Assistants cannot update/delete finance records.
- Manager and superadmin can update/void/delete according to the agreed business rules.
- Receipt numbers are not unique.

The source implementation explicitly describes the feature as a financial workflow rather than simple CRUD, and the three finance types feed section reports and then a total dashboard.

---

# 3. First Architectural Decision: Do Not Modify Auth Unnecessarily

You already have:

```text
app/
├── core/
│   ├── security.py
│   └── redis.py
├── db/
│   ├── base.py
│   ├── session.py
│   └── all_models.py
└── users/
    ├── models.py
    ├── schemas.py
    ├── dependencies.py
    ├── service.py
    └── router.py
```

Your `User` model already contains:

```python
created_by_id
token_version
role
status
```

Your auth dependency already gives protected routes:

```python
current_user: User = Depends(get_current_user)
```

and role-protected routes:

```python
actor: User = Depends(
    require_roles(
        UserRoleEnum.SUPERADMIN,
        UserRoleEnum.MANAGER,
    )
)
```

For the finance domain, **reuse this**.

Do not create:

```text
finance_auth.py
finance_permissions.py
finance_jwt.py
```

just because we are creating a new module.

Authentication is a cross-cutting concern. The users module already owns it.

---

# 4. Final Folder Structure

I recommend this structure:

```text
app/
├── main.py
│
├── core/
│   ├── config.py
│   ├── redis.py
│   └── security.py
│
├── db/
│   ├── base.py
│   ├── session.py
│   └── all_models.py
│
├── users/
│   ├── models.py
│   ├── schemas.py
│   ├── dependencies.py
│   ├── service.py
│   └── router.py
│
├── doctors/
│   ├── __init__.py
│   ├── models.py
│   ├── schemas.py
│   ├── service.py
│   └── router.py
│
└── finance/
    ├── __init__.py
    ├── models.py
    ├── schemas.py
    ├── calculations.py
    ├── dependencies.py
    ├── service.py
    ├── reports.py
    └── router.py
```

Why this split?

### `doctors/`

Doctor is a real domain entity.

It has its own:

- persistence model
- schemas
- CRUD service
- router

### `finance/`

Consultation, surgery, room, and reporting all belong to the financial domain, so they can share a bounded module.

Do not create a giant:

```text
utils.py
```

with random finance formulas.

Financial rules belong in:

```text
finance/calculations.py
```

---

# 5. Before Coding: Understand the Domain

## 5.1 Doctor

Fields:

```text
id
first_name
last_name
specialty
created_at
updated_at
```

Display name:

```python
f"{last_name} {first_name}"
```

One doctor can be connected to many:

```text
consultations
surgeries
rooms
```

---

# 6. Consultation Business Logic

Consultation has:

```text
type
receipt_number
date
amount
doctor_percent
minus_beshming
doctor_id
created_by_id
created_at
updated_at
```

Types:

```python
korik
qaytakorik
```

Formula:

```text
minus = minus_beshming or 0

doctor_share =
    (amount - minus) * doctor_percent / 100

clinic_profit =
    amount - doctor_share - minus

expense =
    minus
```

Example:

```text
amount = 100000
minus_beshming = 5000
doctor_percent = 50

doctor_share = (100000 - 5000) * 50 / 100
             = 47500

clinic_profit = 100000 - 47500 - 5000
              = 47500
```

---

# 7. Surgery Business Logic

Fields:

```text
receipt_number
date
amount
surgery_expense
doctor_percent
doctor_id
created_by_id
created_at
updated_at
```

Formula:

```text
expense = surgery_expense or 0

doctor_share =
    (amount - expense) * doctor_percent / 100

clinic_profit =
    amount - doctor_share - expense
```

Example:

```text
amount = 2000000
surgery_expense = 300000
doctor_percent = 40

doctor_share =
    (2000000 - 300000) * 40 / 100
    = 680000

clinic_profit =
    2000000 - 680000 - 300000
    = 1020000
```

---

# 8. Room Business Logic

Fields:

```text
receipt_number
date
amount
doctor_percent
doctor_id
created_by_id
created_at
updated_at
```

Room deliberately has **no expense field**.

Formula:

```text
doctor_share =
    amount * doctor_percent / 100

clinic_profit =
    amount - doctor_share

expense = 0
```

---

# 9. The Important Missing Field: `created_by_id`

The authentication design says assistants must only see records they created.

Therefore every financial row needs:

```text
created_by_id -> users.id
```

This should be:

```text
NOT NULL
```

because every finance record must have an actor.

This is different from:

```text
doctor_id
```

because:

- `doctor_id` = the doctor who earns the share.
- `created_by_id` = the authenticated user who entered the record.

Example:

```text
Assistant Rustam enters a receipt
Doctor Aliyev receives 40%

created_by_id = Rustam
doctor_id     = Aliyev
doctor_percent = 40
```

This distinction becomes extremely important later for permissions and audit history.

---

# 10. Finance Record Lifecycle

The original API list contains DELETE routes, but the confirmed business rule is:

```text
finance records use void/archive rather than physical deletion
```

We therefore implement lifecycle state explicitly.

For each financial record:

```text
ACTIVE
   │
   ▼
VOIDED
```

A voided record:

- stays in PostgreSQL
- keeps its original information
- is excluded from normal financial reports
- is not treated as current income

Recommended fields:

```python
is_voided
voided_at
voided_by_id
```

This is intentionally different from deleting the row.

Why?

Suppose:

```text
Assistant created receipt #500
Manager later finds an error
```

Deleting it would destroy historical evidence.

Voiding keeps:

```text
who created it
what it contained
when it was created
who voided it
when it was voided
```

Later, this also gives you a natural foundation for audit logs.

---

# 11. Model Design

## 11.1 `doctors/models.py`

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    first_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    specialty: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

### Why integer IDs?

Your existing users use UUIDs, and the main architecture decision says doctors and finance records use integer IDs while users continue to use UUIDs.

This intentionally differs from the UUID strategy used by `users`: the original Django finance tables also used integer IDs, and that is appropriate here.

---

# 12. Finance Models

We will use one `finance/models.py` initially.

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConsultationType(str, enum.Enum):
    KORIK = "korik"
    QAYTAKORIK = "qaytakorik"


class Consultation(Base):
    __tablename__ = "consultations"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_consultations_amount_non_negative",
        ),
        CheckConstraint(
            "doctor_percent >= 0 AND doctor_percent <= 100",
            name="ck_consultations_doctor_percent_range",
        ),
        CheckConstraint(
            "minus_beshming >= 0",
            name="ck_consultations_minus_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    type: Mapped[ConsultationType] = mapped_column(
        Enum(
            ConsultationType,
            name="consultation_type",
        ),
        nullable=False,
    )

    receipt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    doctor_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    minus_beshming: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        default=5000,
        server_default="5000",
    )

    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "doctors.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    is_voided: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
        nullable=False,
    )

    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Surgery(Base):
    __tablename__ = "surgeries"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_surgeries_amount_non_negative",
        ),
        CheckConstraint(
            "surgery_expense >= 0",
            name="ck_surgeries_expense_non_negative",
        ),
        CheckConstraint(
            "doctor_percent >= 0 AND doctor_percent <= 100",
            name="ck_surgeries_doctor_percent_range",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    receipt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    surgery_expense: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    doctor_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "doctors.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    is_voided: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
        nullable=False,
    )

    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Room(Base):
    __tablename__ = "rooms"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_rooms_amount_non_negative",
        ),
        CheckConstraint(
            "doctor_percent >= 0 AND doctor_percent <= 100",
            name="ck_rooms_doctor_percent_range",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    receipt_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    doctor_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "doctors.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    is_voided: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
        nullable=False,
    )

    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

## Important correction

SQLAlchemy's `Numeric` returns `Decimal` values from PostgreSQL. For the model annotations, it is better to be explicit about that.

A stronger version is:

```python
from decimal import Decimal

amount: Mapped[Decimal] = mapped_column(
    Numeric(10, 2),
    nullable=False,
)
```

Use this form in your actual project.

So the final model should use:

```python
from decimal import Decimal

amount: Mapped[Decimal]
doctor_percent: Mapped[Decimal]
surgery_expense: Mapped[Decimal]
minus_beshming: Mapped[Decimal | None]
```

rather than `float`.

---

# 13. Why `NUMERIC` + `Decimal` Matters

Never do this:

```python
doctor_share = amount * percent / 100
```

when `amount` and `percent` are Python floats.

Financial calculations should not depend on binary floating-point representation.

Use:

```python
from decimal import Decimal

doctor_share = (
    amount * percent
) / Decimal("100")
```

PostgreSQL:

```sql
NUMERIC(10, 2)
```

Python:

```python
Decimal
```

Think of the pipeline as:

```text
PostgreSQL NUMERIC
       ↓
Python Decimal
       ↓
Decimal calculation
       ↓
Decimal response
```

---

# 14. Build `all_models.py`

Your project already uses an explicit model-registration file.

Add:

```python
from app.users.models import User
from app.doctors.models import Doctor
from app.finance.models import Consultation, Room, Surgery

__all__ = [
    "User",
    "Doctor",
    "Consultation",
    "Surgery",
    "Room",
]
```

The imports matter even if your editor says they are unused.

Alembic needs the models registered on:

```python
Base.metadata
```

before autogeneration.

---

# 15. Pydantic Schema Design

Never expose one ORM model as both request and response schema.

We want:

```text
Create
Update
Read
```

These are different contracts.

The client must not submit:

```text
id
created_by_id
created_at
updated_at
is_voided
voided_by_id
calculated doctor share
clinic profit
```

Those belong to the server.

---

# 16. Shared Schema Utilities

Create:

```text
app/finance/schemas.py
```

Start with imports:

```python
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.finance.models import ConsultationType
```

Pagination:

```python
class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
```

The client can request:

```text
page=1&page_size=20
```

but not:

```text
page_size=1000000
```

---

# 17. Doctor Schemas

Create:

```python
class DoctorCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    specialty: str = Field(min_length=1, max_length=50)


class DoctorUpdate(BaseModel):
    first_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    last_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )
    specialty: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
    )


class DoctorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_name: str
    last_name: str
    specialty: str
    created_at: datetime
    updated_at: datetime
```

---

# 18. Consultation Schemas

```python
class ConsultationCreate(BaseModel):
    type: ConsultationType
    receipt_number: int = Field(gt=0)
    date: datetime
    amount: Decimal = Field(ge=0)
    doctor_percent: Decimal = Field(ge=0, le=100)
    minus_beshming: Decimal | None = Field(
        default=Decimal("5000.00"),
        ge=0,
    )
    doctor_id: int | None = None
```

Update:

```python
class ConsultationUpdate(BaseModel):
    type: ConsultationType | None = None
    receipt_number: int | None = Field(default=None, gt=0)
    date: datetime | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    doctor_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    minus_beshming: Decimal | None = Field(
        default=None,
        ge=0,
    )
    doctor_id: int | None = None
```

Read:

```python
class ConsultationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: ConsultationType
    receipt_number: int
    date: datetime
    amount: Decimal
    doctor_percent: Decimal
    minus_beshming: Decimal | None
    doctor_id: int | None
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
```

---

# 19. The PATCH Problem: `None` vs Omitted

This is an important senior-level topic.

Consider:

```json
{}
```

versus:

```json
{
    "doctor_id": null
}
```

They are not the same.

First means:

```text
Do not change doctor_id
```

Second means:

```text
Remove doctor_id
```

With Pydantic:

```python
data.model_dump(exclude_unset=True)
```

distinguishes them.

Service example:

```python
changes = data.model_dump(exclude_unset=True)

for field, value in changes.items():
    setattr(record, field, value)
```

Do not do:

```python
if data.doctor_id:
    record.doctor_id = data.doctor_id
```

because an explicit `None` means “clear the relationship”, while an omitted value means “leave it unchanged”.

---

# 20. Surgery Schemas

```python
class SurgeryCreate(BaseModel):
    receipt_number: int = Field(gt=0)
    date: datetime
    amount: Decimal = Field(ge=0)
    surgery_expense: Decimal = Field(ge=0)
    doctor_percent: Decimal = Field(ge=0, le=100)
    doctor_id: int | None = None


class SurgeryUpdate(BaseModel):
    receipt_number: int | None = Field(default=None, gt=0)
    date: datetime | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    surgery_expense: Decimal | None = Field(default=None, ge=0)
    doctor_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    doctor_id: int | None = None


class SurgeryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: int
    date: datetime
    amount: Decimal
    surgery_expense: Decimal
    doctor_percent: Decimal
    doctor_id: int | None
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
```

---

# 21. Room Schemas

```python
class RoomCreate(BaseModel):
    receipt_number: int | None = Field(
        default=None,
        gt=0,
    )
    date: datetime
    amount: Decimal = Field(ge=0)
    doctor_percent: Decimal = Field(ge=0, le=100)
    doctor_id: int | None = None


class RoomUpdate(BaseModel):
    receipt_number: int | None = Field(
        default=None,
        gt=0,
    )
    date: datetime | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    doctor_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    doctor_id: int | None = None


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: int | None
    date: datetime
    amount: Decimal
    doctor_percent: Decimal
    doctor_id: int | None
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
```

---

# 22. Pagination Response

A useful common response:

```python
from typing import Generic, TypeVar

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    pages: int
```

Calculation:

```python
pages = (total + page_size - 1) // page_size
```

Example:

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total": 43,
  "pages": 3
}
```

---

# 23. Keep Financial Calculations Pure

Create:

```text
app/finance/calculations.py
```

This file must not import:

```text
FastAPI
SQLAlchemy
AsyncSession
Redis
HTTPException
```

Pure calculation code is one of the most important architectural boundaries in this project.

---

# 24. Money Rounding Policy

The confirmed policy is:

```text
ROUND_HALF_UP
```

and:

> Calculate each receipt's doctor share, round that receipt's share to two decimals, then aggregate those rounded shares.

Create:

```python
from decimal import Decimal, ROUND_HALF_UP


TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal("100")


def money(value: Decimal) -> Decimal:
    return value.quantize(
        TWO_PLACES,
        rounding=ROUND_HALF_UP,
    )
```

Then:

```python
def consultation_totals(
    amount: Decimal,
    minus_beshming: Decimal | None,
    doctor_percent: Decimal,
) -> dict[str, Decimal]:

    minus = minus_beshming or Decimal("0.00")

    doctor_share = money(
        (amount - minus) * doctor_percent / HUNDRED
    )

    clinic_profit = money(
        amount - doctor_share - minus
    )

    return {
        "income": money(amount),
        "doctor_share": doctor_share,
        "expense": money(minus),
        "clinic_profit": clinic_profit,
    }
```

Surgery:

```python
def surgery_totals(
    amount: Decimal,
    surgery_expense: Decimal | None,
    doctor_percent: Decimal,
) -> dict[str, Decimal]:

    expense = surgery_expense or Decimal("0.00")

    doctor_share = money(
        (amount - expense) * doctor_percent / HUNDRED
    )

    clinic_profit = money(
        amount - doctor_share - expense
    )

    return {
        "income": money(amount),
        "doctor_share": doctor_share,
        "expense": money(expense),
        "clinic_profit": clinic_profit,
    }
```

Room:

```python
def room_totals(
    amount: Decimal,
    doctor_percent: Decimal,
) -> dict[str, Decimal]:

    doctor_share = money(
        amount * doctor_percent / HUNDRED
    )

    clinic_profit = money(
        amount - doctor_share
    )

    return {
        "income": money(amount),
        "doctor_share": doctor_share,
        "expense": Decimal("0.00"),
        "clinic_profit": clinic_profit,
    }
```

---

# 25. Why Round Each Receipt?

Imagine two receipts generate:

```text
receipt 1 = 0.005
receipt 2 = 0.005
```

If you sum first:

```text
0.005 + 0.005 = 0.010
```

then round:

```text
0.01
```

But if each payable share is rounded:

```text
receipt 1 -> 0.01
receipt 2 -> 0.01

sum = 0.02
```

The confirmed business policy chooses the second behavior.

This is why:

```python
doctor_share = money(calculation)
```

happens inside the calculation function.

---

# 26. Validate Business Relationships in Services

Pydantic can tell us:

```text
doctor_id is an integer ID
```

It cannot tell us:

```text
does this doctor actually exist?
```

That is a database/business rule.

Create a helper:

```python
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.doctors.models import Doctor


async def get_doctor_or_404(
    db: AsyncSession,
    doctor_id,
) -> Doctor:

    doctor = await db.get(Doctor, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    return doctor
```

Use it from finance services.

---

# 27. Doctor Service

Create:

```text
app/doctors/service.py
```

Imports:

```python
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.doctors.models import Doctor
from app.doctors.schemas import DoctorCreate, DoctorUpdate
```

Create:

```python
async def create_doctor(
    db: AsyncSession,
    data: DoctorCreate,
) -> Doctor:

    doctor = Doctor(
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        specialty=data.specialty.strip(),
    )

    db.add(doctor)

    await db.commit()
    await db.refresh(doctor)

    return doctor
```

Get:

```python
async def get_doctor(
    db: AsyncSession,
    doctor_id: int,
) -> Doctor:

    doctor = await db.get(Doctor, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    return doctor
```

Update:

```python
async def update_doctor(
    db: AsyncSession,
    doctor: Doctor,
    data: DoctorUpdate,
) -> Doctor:

    changes = data.model_dump(exclude_unset=True)

    for field, value in changes.items():
        if isinstance(value, str):
            value = value.strip()

        setattr(doctor, field, value)

    await db.commit()
    await db.refresh(doctor)

    return doctor
```

---

# 28. Doctor Listing

```python
from sqlalchemy import select


async def list_doctors(
    db: AsyncSession,
    *,
    search: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Doctor], int]:

    stmt = select(Doctor)

    if search:
        search_value = f"%{search.strip()}%"

        stmt = stmt.where(
            or_(
                Doctor.first_name.ilike(search_value),
                Doctor.last_name.ilike(search_value),
                Doctor.specialty.ilike(search_value),
            )
        )

    count_stmt = select(func.count()).select_from(
        stmt.order_by(None).subquery()
    )

    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        stmt
        .order_by(
            Doctor.last_name.asc(),
            Doctor.first_name.asc(),
            Doctor.id.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await db.execute(stmt)

    return list(result.scalars().all()), total
```

---

# 29. Why We Add an ID Tie-Breaker

Do not sort only:

```python
.order_by(Doctor.last_name)
```

Use:

```python
.order_by(
    Doctor.last_name,
    Doctor.first_name,
    Doctor.id,
)
```

The ID makes ordering deterministic when two records have the same names.

This matters for pagination.

Without stable ordering, page 2 can produce surprising duplicates/missing records between requests.

---

# 30. Doctor Router

Create:

```text
app/doctors/router.py
```

```python
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.doctors.schemas import (
    DoctorCreate,
    DoctorRead,
    DoctorUpdate,
    PaginatedResponse,
)
from app.doctors.service import (
    create_doctor,
    get_doctor,
    list_doctors,
    update_doctor,
)
from app.users.dependencies import require_roles
from app.users.models import User, UserRoleEnum


router = APIRouter(
    prefix="/doctors",
    tags=["Doctors"],
)
```

Create:

```python
@router.post(
    "",
    response_model=DoctorRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_doctor_endpoint(
    data: DoctorCreate,
    _: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    return await create_doctor(db, data)
```

Read:

```python
@router.get(
    "/{doctor_id}",
    response_model=DoctorRead,
)
async def get_doctor_endpoint(
    doctor_id: int,
    _: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    return await get_doctor(db, doctor_id)
```

Update:

```python
@router.patch(
    "/{doctor_id}",
    response_model=DoctorRead,
)
async def update_doctor_endpoint(
    doctor_id: int,
    data: DoctorUpdate,
    _: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    doctor = await get_doctor(db, doctor_id)

    return await update_doctor(
        db,
        doctor,
        data,
    )
```

List:

```python
@router.get(
    "",
    response_model=PaginatedResponse[DoctorRead],
)
async def list_doctors_endpoint(
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_doctors(
        db,
        search=search,
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
```

---

# 31. Who Can See Doctors?

The project requirements explicitly give managers and superadmins doctor-management responsibilities.

Assistants do not need unrestricted doctor CRUD.

Later, if the UI needs an assistant to choose a doctor while creating a receipt, create a narrow endpoint such as:

```text
GET /doctors/options
```

rather than giving assistants permission to modify doctors.

This is a good example of **capability-oriented API design**.

---

# 32. Finance Authorization

Create:

```text
app/finance/dependencies.py
```

We will reuse the existing `get_current_user`.

A useful dependency:

```python
from fastapi import Depends, HTTPException, status

from app.users.dependencies import get_current_user
from app.users.models import User, UserRoleEnum


async def require_finance_read_access(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role in (
        UserRoleEnum.SUPERADMIN,
        UserRoleEnum.MANAGER,
        UserRoleEnum.ASSISTANT,
    ):
        return current_user

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to view finance records",
    )
```

Why not simply use:

```python
require_roles(SUPERADMIN, MANAGER, ASSISTANT)
```

everywhere?

Because some finance permissions depend on the **record owner**.

For example:

```text
Manager:
    can see every record

Assistant:
    can see only records where
    created_by_id == current_user.id
```

Role is not enough.

This is called **object-level authorization**.

---

# 33. Object-Level Authorization

For assistants, query the database with:

```python
where(
    record.created_by_id == current_user.id
)
```

Do not:

1. fetch every record
2. return them
3. filter in Python

Bad:

```python
records = await get_all_records()
records = [
    record
    for record in records
    if record.created_by_id == user.id
]
```

Good:

```python
stmt = select(Consultation).where(
    Consultation.created_by_id == user.id
)
```

Authorization should happen as close to the database query as practical.

---

# 34. Consultation Service

Create:

```text
app/finance/service.py
```

Start with:

```python
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.doctors.models import Doctor
from app.finance.models import Consultation, ConsultationType
from app.finance.schemas import ConsultationCreate, ConsultationUpdate
from app.users.models import User, UserRoleEnum
```

Create:

```python
async def create_consultation(
    db: AsyncSession,
    *,
    actor: User,
    data: ConsultationCreate,
) -> Consultation:

    if data.doctor_id is not None:
        doctor = await db.get(Doctor, data.doctor_id)

        if doctor is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Doctor not found",
            )

    record = Consultation(
        type=data.type,
        receipt_number=data.receipt_number,
        date=data.date,
        amount=data.amount,
        doctor_percent=data.doctor_percent,
        minus_beshming=data.minus_beshming,
        doctor_id=data.doctor_id,
        created_by_id=actor.id,
    )

    db.add(record)

    await db.commit()
    await db.refresh(record)

    return record
```

---

# 35. Expense > Income

This is one of the remaining product decisions from the project requirements.

For this implementation guide, we will use:

```text
expense > income → reject with 422
```

because allowing:

```text
amount = 100000
expense = 250000
```

creates:

```text
negative doctor-share base
negative clinic profit
```

which is almost certainly not intended for a clinic receipt.

Implement:

```python
def validate_expense(
    *,
    amount,
    expense,
) -> None:

    if expense > amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense cannot exceed amount",
        )
```

Consultation:

```python
minus_beshming <= amount
```

Surgery:

```python
surgery_expense <= amount
```

If your final business rule says otherwise, this is the one place you change and then update the tests.

---

# 36. Consultation Update

When updating a consultation, validate the **final state**, not only the incoming field.

Example:

Current:

```text
amount = 100000
minus = 5000
```

Client sends:

```json
{
    "minus_beshming": 150000
}
```

If you validate only:

```python
new_minus >= 0
```

you miss the business rule.

Instead:

```python
changes = data.model_dump(exclude_unset=True)

new_amount = changes.get(
    "amount",
    consultation.amount,
)

new_minus = changes.get(
    "minus_beshming",
    consultation.minus_beshming,
)

if new_minus is not None and new_minus > new_amount:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="minus_beshming cannot exceed amount",
    )
```

This is a general engineering lesson:

> Validate state transitions, not just individual fields.

---

# 37. Transaction Pattern

For one coherent write:

```python
db.add(record)
await db.commit()
await db.refresh(record)
return record
```

For multiple dependent writes, the outer service should own the transaction.

Avoid:

```python
service_a():
    await db.commit()

service_b():
    await db.commit()
```

when they are logically one operation.

A partial commit is often worse than a transaction failure.

---

# 38. Finance List Queries

Consultations need:

```text
doctor_id
type
date_from
date_to
page
page_size
```

The original behavior sorts by:

```text
date DESC
```

Use:

```python
stmt = (
    select(Consultation)
    .order_by(
        Consultation.date.desc(),
        Consultation.id.desc(),
    )
)
```

Then add filters.

---

# 39. Shared Date Filtering

Create:

```text
app/finance/reports.py
```

First define:

```python
from datetime import date, datetime, time
from zoneinfo import ZoneInfo


CLINIC_TZ = ZoneInfo("Asia/Tashkent")
```

Build the range:

```python
def build_date_range(
    date_from: date | None,
    date_to: date | None,
) -> tuple[datetime | None, datetime | None]:

    if date_from is not None and date_to is not None:
        if date_from > date_to:
            raise ValueError(
                "date_from cannot be after date_to"
            )

    start = None

    if date_from is not None:
        start = datetime.combine(
            date_from,
            time.min,
            tzinfo=CLINIC_TZ,
        )

    end = None

    if date_to is not None:
        end = datetime.combine(
            date_to,
            time.min,
            tzinfo=CLINIC_TZ,
        )

    return start, end
```

We will use an exclusive end:

```text
date >= start
date < end + 1 day
```

So for:

```text
date_from = 2026-01-01
date_to   = 2026-01-31
```

the database condition is conceptually:

```text
2026-01-01 00:00:00
≤ date
< 2026-02-01 00:00:00
```

This avoids fragile:

```text
23:59:59.999999
```

logic.

---

# 40. Async Date Filter Helper

```python
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


CLINIC_TZ = ZoneInfo("Asia/Tashkent")


def get_business_datetime_range(
    date_from: date | None,
    date_to: date | None,
) -> tuple[datetime | None, datetime | None]:

    if (
        date_from is not None
        and date_to is not None
        and date_from > date_to
    ):
        raise ValueError(
            "date_from cannot be after date_to"
        )

    start = (
        datetime.combine(
            date_from,
            time.min,
            tzinfo=CLINIC_TZ,
        )
        if date_from
        else None
    )

    end_exclusive = (
        datetime.combine(
            date_to + timedelta(days=1),
            time.min,
            tzinfo=CLINIC_TZ,
        )
        if date_to
        else None
    )

    return start, end_exclusive
```

Use it like:

```python
start, end = get_business_datetime_range(
    date_from,
    date_to,
)

if start:
    stmt = stmt.where(Model.date >= start)

if end:
    stmt = stmt.where(Model.date < end)
```

---

# 41. Report Schema Design

Create:

```text
app/finance/schemas.py
```

Common doctor share:

```python
class DoctorShareReport(BaseModel):
    doctor_id: int
    name: str
    total_share: Decimal
    count: int
```

Consultation type summary:

```python
class ConsultationTypeSummary(BaseModel):
    total: Decimal
    count: int
```

Consultation report:

```python
class ConsultationReport(BaseModel):
    korik: ConsultationTypeSummary
    qayta_korik: ConsultationTypeSummary

    total_income: Decimal
    total_doctor_share: Decimal
    total_clinic_profit: Decimal
    total_consultation_expense: Decimal

    doctor_shares: list[DoctorShareReport]
```

Surgery:

```python
class SurgeryReport(BaseModel):
    surgery_total_income: Decimal
    surgery_total_doctor_share: Decimal
    surgery_total_clinic_profit: Decimal
    surgery_total_expense: Decimal

    surgery_doctor_shares: list[DoctorShareReport]
```

Room:

```python
class RoomReport(BaseModel):
    room_total_income: Decimal
    room_total_doctor_share: Decimal
    room_total_clinic_profit: Decimal

    room_doctor_shares: list[DoctorShareReport]
```

Total dashboard:

```python
class TotalReport(BaseModel):
    consultation_income: Decimal
    consultation_doctor_share: Decimal
    consultation_expense: Decimal
    consultation_clinic_profit: Decimal

    surgery_income: Decimal
    surgery_doctor_share: Decimal
    surgery_expense: Decimal
    surgery_clinic_profit: Decimal

    room_income: Decimal
    room_doctor_share: Decimal
    room_clinic_profit: Decimal

    total_income: Decimal
    total_doctor_share: Decimal
    total_expense: Decimal
    total_clinic_profit: Decimal
```

---

# 42. Report Query Strategy

Start with correctness.

The intended first implementation is:

```text
1. Select records
2. Apply date filter
3. Load required doctors
4. Run pure calculation functions
5. Group by doctor
6. Build typed response
```

Do not prematurely force everything into SQL.

The source Django implementation calculates much of this business logic in Python loops, so a service-layer translation is natural.

Later, when the database becomes large:

```text
measure query count
measure latency
profile
then optimize
```

Do not optimize a problem that has not been measured.

---

# 43. Avoid the N+1 Problem

Bad:

```python
for consultation in consultations:
    doctor = await db.get(
        Doctor,
        consultation.doctor_id,
    )
```

That produces:

```text
1 query for consultations
+ N doctor queries
```

For 1000 records:

```text
1001 queries
```

Instead collect doctor IDs:

```python
doctor_ids = {
    record.doctor_id
    for record in records
    if record.doctor_id is not None
}
```

Then:

```python
doctors_stmt = select(Doctor).where(
    Doctor.id.in_(doctor_ids)
)

doctors = (
    await db.execute(doctors_stmt)
).scalars().all()
```

Build:

```python
doctor_map = {
    doctor.id: doctor
    for doctor in doctors
}
```

Then:

```python
doctor = doctor_map.get(record.doctor_id)
```

Now the operation is:

```text
1 query for records
1 query for doctors
```

instead of:

```text
1 + N
```

---

# 44. Consultation Report Algorithm

```python
async def build_consultation_report(
    db: AsyncSession,
    *,
    date_from,
    date_to,
    actor: User,
) -> ConsultationReport:
    ...
```

Build query:

```python
stmt = select(Consultation).where(
    Consultation.is_voided.is_(False)
)
```

Apply assistant ownership:

```python
if actor.role == UserRoleEnum.ASSISTANT:
    stmt = stmt.where(
        Consultation.created_by_id == actor.id
    )
```

Apply date:

```python
start, end = get_business_datetime_range(
    date_from,
    date_to,
)

if start:
    stmt = stmt.where(
        Consultation.date >= start
    )

if end:
    stmt = stmt.where(
        Consultation.date < end
    )
```

Load:

```python
records = (
    await db.execute(stmt)
).scalars().all()
```

---

# 45. Consultation Aggregation

Initialize:

```python
from decimal import Decimal


zero = Decimal("0.00")

korik_total = zero
korik_count = 0

qaytakorik_total = zero
qaytakorik_count = 0

total_doctor_share = zero
total_clinic_profit = zero
total_expense = zero
```

Doctor grouping:

```python
doctor_groups: dict[int, dict] = {}
```

Loop:

```python
for record in records:

    totals = consultation_totals(
        record.amount,
        record.minus_beshming,
        record.doctor_percent,
    )

    if record.type == ConsultationType.KORIK:
        korik_total += record.amount
        korik_count += 1

    elif record.type == ConsultationType.QAYTAKORIK:
        qaytakorik_total += record.amount
        qaytakorik_count += 1

    total_doctor_share += totals["doctor_share"]
    total_clinic_profit += totals["clinic_profit"]
    total_expense += totals["expense"]

    if record.doctor_id is not None:
        group = doctor_groups.setdefault(
            record.doctor_id,
            {
                "total_share": zero,
                "count": 0,
            },
        )

        group["total_share"] += totals["doctor_share"]
        group["count"] += 1
```

---

# 46. Doctor Names for Reports

Load the doctors in one query:

```python
doctor_ids = set(doctor_groups)

if doctor_ids:
    doctors_stmt = select(Doctor).where(
        Doctor.id.in_(doctor_ids)
    )

    doctors = (
        await db.execute(doctors_stmt)
    ).scalars().all()

    doctor_map = {
        doctor.id: doctor
        for doctor in doctors
    }
else:
    doctor_map = {}
```

Convert groups:

```python
doctor_shares = []

for doctor_id, group in doctor_groups.items():

    doctor = doctor_map.get(doctor_id)

    if doctor is None:
        continue

    doctor_shares.append(
        DoctorShareReport(
            doctor_id=doctor.id,
            name=f"{doctor.last_name} {doctor.first_name}",
            total_share=money(
                group["total_share"]
            ),
            count=group["count"],
        )
    )
```

---

# 47. Do Not Rely on Doctor Rows Existing

A doctor can later be deleted.

The database `ON DELETE SET NULL` keeps the receipt.

That means:

```text
old finance row
      │
      └── doctor_id = NULL
```

Therefore reports must handle:

```python
record.doctor_id is None
```

Do not assume every financial record has a doctor forever.

---

# 48. Consultation Report Return

```python
return ConsultationReport(
    korik=ConsultationTypeSummary(
        total=money(korik_total),
        count=korik_count,
    ),
    qayta_korik=ConsultationTypeSummary(
        total=money(qaytakorik_total),
        count=qaytakorik_count,
    ),
    total_income=money(
        korik_total + qaytakorik_total
    ),
    total_doctor_share=money(
        total_doctor_share
    ),
    total_clinic_profit=money(
        total_clinic_profit
    ),
    total_consultation_expense=money(
        total_expense
    ),
    doctor_shares=doctor_shares,
)
```

---

# 49. Surgery Report

The surgery report follows the same pattern.

Query active records:

```python
stmt = select(Surgery).where(
    Surgery.is_voided.is_(False)
)
```

Restrict assistants:

```python
if actor.role == UserRoleEnum.ASSISTANT:
    stmt = stmt.where(
        Surgery.created_by_id == actor.id
    )
```

Apply date filter.

Then:

```python
total_income = Decimal("0.00")
total_doctor_share = Decimal("0.00")
total_expense = Decimal("0.00")
total_clinic_profit = Decimal("0.00")
```

Loop:

```python
for record in records:

    totals = surgery_totals(
        record.amount,
        record.surgery_expense,
        record.doctor_percent,
    )

    total_income += totals["income"]
    total_doctor_share += totals["doctor_share"]
    total_expense += totals["expense"]
    total_clinic_profit += totals["clinic_profit"]
```

Then group by doctor exactly as in consultations.

---

# 50. Room Report

Room has no expense.

Query:

```python
stmt = select(Room).where(
    Room.is_voided.is_(False)
)
```

Assistant filter:

```python
if actor.role == UserRoleEnum.ASSISTANT:
    stmt = stmt.where(
        Room.created_by_id == actor.id
    )
```

Loop:

```python
total_income = Decimal("0.00")
total_doctor_share = Decimal("0.00")
total_clinic_profit = Decimal("0.00")

for record in records:

    totals = room_totals(
        record.amount,
        record.doctor_percent,
    )

    total_income += totals["income"]
    total_doctor_share += totals["doctor_share"]
    total_clinic_profit += totals["clinic_profit"]
```

There is no room expense accumulator.

That is intentional.

---

# 51. The Most Important Report Rule

Do not write this:

```python
total_doctor_share = ...
```

separately in:

```text
consultation report
surgery report
room report
total report
```

That creates four versions of the same business logic.

Instead:

```text
calculation functions
      ↓
section reports
      ↓
total report
```

The total report composes trusted section results.

---

# 52. Total Report

Build:

```python
consultation = await build_consultation_report(...)
surgery = await build_surgery_report(...)
room = await build_room_report(...)
```

Then:

```python
return TotalReport(
    consultation_income=consultation.total_income,
    consultation_doctor_share=consultation.total_doctor_share,
    consultation_expense=consultation.total_consultation_expense,
    consultation_clinic_profit=consultation.total_clinic_profit,

    surgery_income=surgery.surgery_total_income,
    surgery_doctor_share=surgery.surgery_total_doctor_share,
    surgery_expense=surgery.surgery_total_expense,
    surgery_clinic_profit=surgery.surgery_total_clinic_profit,

    room_income=room.room_total_income,
    room_doctor_share=room.room_total_doctor_share,
    room_clinic_profit=room.room_total_clinic_profit,

    total_income=money(
        consultation.total_income
        + surgery.surgery_total_income
        + room.room_total_income
    ),

    total_doctor_share=money(
        consultation.total_doctor_share
        + surgery.surgery_total_doctor_share
        + room.room_total_doctor_share
    ),

    total_expense=money(
        consultation.total_consultation_expense
        + surgery.surgery_total_expense
    ),

    total_clinic_profit=money(
        consultation.total_clinic_profit
        + surgery.surgery_total_clinic_profit
        + room.room_total_clinic_profit
    ),
)
```

This gives you a powerful invariant:

```text
dashboard totals
=
section totals
```

---

# 53. Report Permissions

Protected report endpoints:

```text
SUPERADMIN
MANAGER
ASSISTANT
```

But visibility differs:

```text
Superadmin:
    all records

Manager:
    all records

Assistant:
    own records only
```

The report service therefore receives:

```python
actor: User
```

and applies ownership restrictions.

Do not trust a query parameter like:

```text
?created_by_id=<uuid>
```

for authorization.

The server must derive ownership from:

```python
current_user.id
```

---

# 54. List Endpoint Design

Consultations:

```text
GET /consultations
```

Query parameters:

```text
doctor_id
type
date_from
date_to
page
page_size
```

Example:

```text
GET /consultations?doctor_id=<uuid>&type=korik&page=1&page_size=20
```

Surgeries:

```text
GET /surgeries
```

Parameters:

```text
doctor_id
date_from
date_to
page
page_size
```

Rooms:

```text
GET /rooms
```

Parameters:

```text
doctor_id
date_from
date_to
page
page_size
```

---

# 55. Stable Finance Ordering

Use:

```python
.order_by(
    Model.date.desc(),
    Model.id.desc(),
)
```

The second field is the tie-breaker.

This is better than:

```python
.order_by(Model.date.desc())
```

because two records can have exactly the same timestamp.

---

# 56. Generic Filtering Pattern

A consultation list function can look like:

```python
stmt = select(Consultation).where(
    Consultation.is_voided.is_(False)
)

if actor.role == UserRoleEnum.ASSISTANT:
    stmt = stmt.where(
        Consultation.created_by_id == actor.id
    )

if doctor_id is not None:
    stmt = stmt.where(
        Consultation.doctor_id == doctor_id
    )

if consultation_type is not None:
    stmt = stmt.where(
        Consultation.type == consultation_type
    )

if date_from is not None:
    stmt = stmt.where(
        Consultation.date >= start
    )

if date_to is not None:
    stmt = stmt.where(
        Consultation.date < end
    )
```

This is a good pattern because each condition is independently understandable.

---

# 57. Finance Router Permission Matrix

## Consultation

```text
POST
    SUPERADMIN
    MANAGER
    ASSISTANT

GET
    SUPERADMIN
    MANAGER
    ASSISTANT (own only)

PATCH
    SUPERADMIN
    MANAGER

VOID
    SUPERADMIN
    MANAGER

DELETE
    Do not physically delete finance rows
```

## Surgery

Same pattern.

## Room

Same pattern.

---

# 58. Creating a Finance Record

The route should be thin:

```python
@router.post(
    "",
    response_model=ConsultationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_consultation_endpoint(
    data: ConsultationCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_consultation(
        db,
        actor=actor,
        data=data,
    )
```

Notice what the router does not do.

It does not:

```text
hash anything
calculate shares
query the doctor
write SQL
perform loops
commit manually
```

That belongs in the service.

---

# 59. PATCH Consultation

```python
@router.patch(
    "/{consultation_id}",
    response_model=ConsultationRead,
)
async def update_consultation_endpoint(
    consultation_id: int,
    data: ConsultationUpdate,
    actor: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    consultation = await get_consultation_or_404(
        db,
        consultation_id,
    )

    return await update_consultation(
        db,
        consultation=consultation,
        data=data,
    )
```

Authorization is enforced before the service runs.

---

# 60. Why Services Should Not Depend on FastAPI `Request`

Prefer:

```python
async def update_consultation(
    db,
    consultation,
    data,
)
```

Not:

```python
async def update_consultation(
    request: Request,
    ...
)
```

Business services should be testable without HTTP.

This makes:

```python
pytest
```

much easier.

---

# 61. Voiding a Finance Record

```python
from datetime import datetime, timezone


async def void_consultation(
    db: AsyncSession,
    *,
    consultation: Consultation,
    actor: User,
) -> Consultation:

    if consultation.is_voided:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Consultation is already voided",
        )

    consultation.is_voided = True
    consultation.voided_at = datetime.now(
        timezone.utc
    )
    consultation.voided_by_id = actor.id

    await db.commit()
    await db.refresh(consultation)

    return consultation
```

The report query excludes:

```python
Consultation.is_voided.is_(False)
```

This gives you historical preservation without corrupting reports.

---

# 62. Why `409 Conflict` for Already Voided?

This is different from invalid input.

```text
400/422
    input itself is invalid

404
    resource doesn't exist

409
    resource exists but its current state conflicts
    with the requested operation

403
    user isn't allowed

401
    authentication failed
```

For example:

```text
POST /consultations/{id}/void
```

when it is already voided is naturally:

```text
409 Conflict
```

---

# 63. Get-or-404 Helpers

Use helpers to eliminate repeated boilerplate:

```python
async def get_surgery_or_404(
    db: AsyncSession,
    surgery_id: int,
) -> Surgery:

    surgery = await db.get(
        Surgery,
        surgery_id,
    )

    if surgery is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Surgery not found",
        )

    return surgery
```

Same for rooms.

Do not turn this into a giant generic abstraction too early.

Three clear functions are better than a clever generic repository nobody understands.

---

# 64. Error Handling

For duplicate/conflicting data:

```python
from sqlalchemy.exc import IntegrityError

try:
    await db.commit()
except IntegrityError:
    await db.rollback()

    raise HTTPException(
        status_code=409,
        detail="Database constraint violated",
    )
```

The rollback matters.

After a SQLAlchemy transaction fails, the session is not automatically usable for another database operation.

This is an important SQLAlchemy rule:

```text
IntegrityError
    ↓
rollback()
    ↓
session usable again
```

---

# 65. Do Not Catch Every Exception

Avoid:

```python
except Exception:
    raise HTTPException(...)
```

This hides real programming bugs.

Catch known database/business failures:

```python
except IntegrityError:
```

and let unexpected exceptions surface to your error logging/monitoring.

A broken application should not pretend every bug is a client `400`.

---

# 66. Database Constraints vs Pydantic Validation

Use both.

## Pydantic

Good for:

```text
request payload
>= 0
<= 100
string lengths
enum values
UUID syntax
```

## Database

Good for:

```text
amount >= 0
doctor_percent between 0 and 100
foreign keys
ON DELETE SET NULL
NOT NULL
enum constraints
```

Why duplicate some validation?

Because application validation protects the API.

Database constraints protect the data.

A future script, migration, admin tool, or background job could bypass your Pydantic layer.

---

# 67. Doctor Deletion

Because finance history must survive:

```sql
FOREIGN KEY (doctor_id)
REFERENCES doctors(id)
ON DELETE SET NULL
```

Then:

```text
Doctor A
    ↓
Consultation 1
Consultation 2
Surgery 3
```

After deleting Doctor A:

```text
Consultation 1 doctor_id = NULL
Consultation 2 doctor_id = NULL
Surgery 3 doctor_id = NULL
```

but the financial rows still exist.

This is exactly the historical behavior we want.

---

# 68. What About `created_by_id`?

Do not set:

```sql
ON DELETE CASCADE
```

because deleting a user should not destroy financial records.

The user is an actor/history reference.

Keep the financial record.

The exact deletion policy for users may be restricted by your auth layer; do not design finance around cascading destruction.

---

# 69. Migration

After models are complete:

```bash
alembic revision --autogenerate -m "add clinic finance models"
```

Before running the migration, inspect it.

You should see:

```text
create doctors
create consultations
create surgeries
create rooms
create enum types
create foreign keys
create check constraints
```

Then:

```bash
alembic upgrade head
```

Verify:

```bash
alembic current
alembic history
```

Never blindly trust autogenerate.

It is a diff generator, not a business-rule engine.

---

# 70. Migration Review Checklist

Inspect:

```text
integer auto-increment primary keys for doctors/finance
NUMERIC(10,2)
NUMERIC(5,2)
NOT NULL
ON DELETE SET NULL
created_by_id foreign key
voided_by_id foreign key
enum values
check constraints
server defaults
indexes
```

Especially verify:

```text
consultation_type
user_role
user_status
```

Do not accidentally create a second copy of existing user enums.

---

# 71. Suggested Indexes

At minimum consider:

```text
consultations.date
consultations.doctor_id
consultations.created_by_id

surgeries.date
surgeries.doctor_id
surgeries.created_by_id

rooms.date
rooms.doctor_id
rooms.created_by_id
```

For assistant filtering:

```text
created_by_id
```

is important.

For reporting:

```text
date
```

is important.

Do not add 20 indexes without measuring.

Indexes speed reads but increase write cost and storage.

---

# 72. Testing Strategy

Do not start with API tests.

Start with:

```text
pure calculation tests
```

then:

```text
service tests
```

then:

```text
API tests
```

Why?

If a report says:

```text
doctor_share = 680000
```

we first want to know:

```text
is the formula correct?
```

before debugging:

```text
router
dependency
database
serialization
```

---

# 73. Calculation Tests

Create:

```text
tests/
└── finance/
    └── test_calculations.py
```

```python
from decimal import Decimal

from app.finance.calculations import (
    consultation_totals,
    room_totals,
    surgery_totals,
)
```

Consultation:

```python
def test_consultation_totals():
    result = consultation_totals(
        Decimal("100000.00"),
        Decimal("5000.00"),
        Decimal("50.00"),
    )

    assert result["doctor_share"] == Decimal(
        "47500.00"
    )

    assert result["clinic_profit"] == Decimal(
        "47500.00"
    )

    assert result["expense"] == Decimal(
        "5000.00"
    )
```

---

# 74. Zero Deduction

```python
def test_consultation_without_deduction():

    result = consultation_totals(
        Decimal("100000.00"),
        None,
        Decimal("50.00"),
    )

    assert result["doctor_share"] == Decimal(
        "50000.00"
    )

    assert result["clinic_profit"] == Decimal(
        "50000.00"
    )
```

---

# 75. Surgery Test

```python
def test_surgery_totals():

    result = surgery_totals(
        Decimal("2000000.00"),
        Decimal("300000.00"),
        Decimal("40.00"),
    )

    assert result["doctor_share"] == Decimal(
        "680000.00"
    )

    assert result["clinic_profit"] == Decimal(
        "1020000.00"
    )

    assert result["expense"] == Decimal(
        "300000.00"
    )
```

---

# 76. Room Test

```python
def test_room_totals():

    result = room_totals(
        Decimal("500000.00"),
        Decimal("20.00"),
    )

    assert result["doctor_share"] == Decimal(
        "100000.00"
    )

    assert result["clinic_profit"] == Decimal(
        "400000.00"
    )

    assert result["expense"] == Decimal(
        "0.00"
    )
```

---

# 77. 0% and 100% Tests

```python
def test_doctor_percentage_zero():

    result = room_totals(
        Decimal("100000.00"),
        Decimal("0.00"),
    )

    assert result["doctor_share"] == Decimal("0.00")
    assert result["clinic_profit"] == Decimal("100000.00")
```

```python
def test_doctor_percentage_hundred():

    result = room_totals(
        Decimal("100000.00"),
        Decimal("100.00"),
    )

    assert result["doctor_share"] == Decimal("100000.00")
    assert result["clinic_profit"] == Decimal("0.00")
```

These are boundary tests.

Boundary tests are extremely valuable for percentage rules.

---

# 78. Rounding Test

```python
def test_doctor_share_rounds_per_receipt():

    result = room_totals(
        Decimal("100.01"),
        Decimal("33.33"),
    )

    assert result["doctor_share"] == Decimal("33.33")
```

Add a more explicit half-up fixture:

```python
def test_round_half_up():

    result = room_totals(
        Decimal("100.00"),
        Decimal("12.345"),
    )

    assert result["doctor_share"] == Decimal(
        "12.35"
    )
```

Your actual database precision will normally constrain stored percentages to two decimals, but keeping the calculation function independently tested makes its rounding rule obvious.

---

# 79. Expense Validation Tests

If you adopt the guide's chosen policy:

```text
expense > amount → 422
```

test it at the service/API boundary.

Example:

```python
def test_surgery_expense_cannot_exceed_amount(client, manager_token):
    response = client.post(
        "/surgeries",
        headers=manager_token,
        json={
            "receipt_number": 1,
            "date": "2026-01-01T10:00:00+05:00",
            "amount": "100000.00",
            "surgery_expense": "150000.00",
            "doctor_percent": "50.00",
            "doctor_id": None,
        },
    )

    assert response.status_code == 422
```

---

# 80. Report Fixture Design

A strong test fixture should contain:

```text
Doctor A
Doctor B
one record with no doctor

Consultation korik
Consultation qaytakorik
Surgery
Room

different percentages
different expenses
different dates

record exactly on date_from
record exactly on date_to

voided record
```

This lets you test both calculation and filtering.

---

# 81. Test Date Boundaries

Create:

```text
2026-01-01 00:00:00
2026-01-31 23:59:59
2026-02-01 00:00:00
```

Ask:

```text
date_from=2026-01-01
date_to=2026-01-31
```

Expected:

```text
include first
include last
exclude February
```

This is one of the most common report bugs.

---

# 82. Empty Reports

No records should produce:

```text
0.00
```

not:

```text
null
```

Example:

```json
{
  "total_income": "0.00",
  "total_doctor_share": "0.00",
  "total_expense": "0.00",
  "total_clinic_profit": "0.00"
}
```

Reports should be easy for frontend code to consume.

---

# 83. Assistant Visibility Test

Create:

```text
assistant_a
assistant_b
```

Then:

```text
assistant_a creates consultation #1
assistant_b creates consultation #2
```

When assistant A asks:

```text
GET /consultations
```

the response must contain:

```text
#1
```

and not:

```text
#2
```

The manager sees both.

This is an authorization test, not merely a filtering test.

---

# 84. Assistant Update Test

Assistant creates:

```text
consultation #1
```

Then assistant calls:

```text
PATCH /consultations/{id}
```

Expected:

```text
403
```

Even if the assistant created it.

The rule is:

```text
creator != editor
```

for assistants.

---

# 85. Manager Update Test

Manager updates assistant-created record:

```text
PATCH /consultations/{id}
```

Expected:

```text
200
```

This verifies object ownership does not accidentally block managers.

---

# 86. Superadmin Test

Superadmin should be able to:

```text
create doctors
create finance records
view all records
update records
void records
view all reports
```

This is your full-access integration test.

---

# 87. Void Test

Create receipt:

```text
amount = 100000
```

Report:

```text
100000
```

Void receipt.

Report becomes:

```text
0
```

But database still contains the row.

Then query directly:

```text
record exists = true
is_voided = true
```

This proves the archive/void model is working.

---

# 88. Dashboard Consistency Test

Suppose:

```text
consultation_income = 500000
surgery_income = 2000000
room_income = 300000
```

Then:

```text
total_income = 2800000
```

Test the invariant:

```python
assert total.total_income == (
    consultation.total_income
    + surgery.surgery_total_income
    + room.room_total_income
)
```

Repeat for:

```text
doctor_share
expense
clinic_profit
```

The dashboard should never disagree with its sections.

---

# 89. API Test Layout

Recommended:

```text
tests/
├── conftest.py
│
├── auth/
│   └── ...
│
├── doctors/
│   ├── test_create.py
│   ├── test_list.py
│   ├── test_update.py
│   └── test_permissions.py
│
└── finance/
    ├── test_calculations.py
    ├── test_consultations.py
    ├── test_surgeries.py
    ├── test_rooms.py
    ├── test_reports.py
    └── test_permissions.py
```

This is easier to navigate than one 2000-line test file.

---

# 90. Test the Service Layer Without HTTP

A senior-level project should not require HTTP for every test.

For example:

```python
record = await create_consultation(
    db,
    actor=manager,
    data=payload,
)
```

This directly tests:

```text
service
database
business rules
```

without:

```text
HTTP parsing
routing
Swagger
```

Then API tests verify the HTTP boundary.

This gives you two different kinds of confidence.

---

# 91. Router Tests Should Be Thin

The router's job is primarily:

```text
path parameters
request parsing
dependency injection
response model
status codes
```

Do not write tests around implementation details such as:

```text
internal dictionary structure
private helper names
```

Test behavior.

---

# 92. Report Performance

The first correct version might do:

```text
consultation query
doctor query

surgery query
doctor query

room query
doctor query
```

That can be improved later.

But measure first.

Useful things to measure:

```text
query count
endpoint latency
rows returned
report duration
```

Only after you know the bottleneck should you introduce more sophisticated SQL aggregation.

---

# 93. Why Not Immediately Use SQL `SUM()`?

Because the business rule contains:

```text
per-receipt Decimal calculation
per-receipt rounding
doctor grouping
different formulas by record type
nullable doctors
void filtering
```

A giant SQL query could become difficult to reason about.

Start with:

```text
correctness
```

Then optimize selectively.

---

# 94. When SQL Aggregation Becomes Worthwhile

If you eventually have millions of records and reports are slow:

```text
profile
   ↓
identify bottleneck
   ↓
introduce database aggregation
   ↓
compare results against trusted Python implementation
```

Do not remove the pure calculation functions.

They remain the reference behavior used by tests.

---

# 95. Report Router

Create:

```text
app/finance/router.py
```

Consultation report:

```python
@router.get(
    "/reports/consultations",
    response_model=ConsultationReport,
)
async def consultation_report_endpoint(
    date_from: date | None = None,
    date_to: date | None = None,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await build_consultation_report(
            db,
            date_from=date_from,
            date_to=date_to,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )
```

Do the same for:

```text
/reports/surgeries
/reports/rooms
/reports/total
```

---

# 96. Router Prefixes

I recommend:

```text
/doctors
/consultations
/surgeries
/rooms
/reports
```

instead of:

```text
/finance/consultations
```

because consultation itself is already a domain resource.

Then your API becomes:

```text
GET /doctors
GET /consultations
GET /surgeries
GET /rooms

GET /reports/consultations
GET /reports/surgeries
GET /reports/rooms
GET /reports/total
```

This closely follows the requested API contract.

---

# 97. Main Router Registration

Your existing `main.py` can become:

```python
from app.doctors.router import router as doctors_router
from app.finance.router import router as finance_router
from app.users.router import router as users_router
```

Then:

```python
app.include_router(users_router)
app.include_router(doctors_router)
app.include_router(finance_router)
```

Do not move auth into finance.

---

# 98. Recommended Router Organization

Inside finance router:

```python
router = APIRouter(tags=["Finance"])
```

Then resource paths:

```python
@router.get("/consultations")
@router.post("/consultations")
@router.get("/consultations/{consultation_id}")
@router.patch("/consultations/{consultation_id}")
@router.post("/consultations/{consultation_id}/void")
```

Repeat for surgery and room.

Reports remain:

```python
@router.get("/reports/consultations")
@router.get("/reports/surgeries")
@router.get("/reports/rooms")
@router.get("/reports/total")
```

---

# 99. Do Not Keep Physical DELETE Endpoints for Finance

The source endpoint list contains DELETE routes because it mirrors the original CRUD interface.

The later confirmed business rule says:

```text
Financial records use a void/archive workflow
rather than physical deletion.
```

Therefore the production API should prefer:

```text
POST /consultations/{id}/void
POST /surgeries/{id}/void
POST /rooms/{id}/void
```

and not:

```text
DELETE /consultations/{id}
```

This is an intentional design improvement over naive CRUD.

---

# 100. What a Good Finance Service Looks Like

A good service should answer:

```text
Can this operation happen?
What related data must exist?
What business rules apply?
What database changes are required?
What transaction boundary is needed?
```

A route should answer:

```text
What HTTP method?
What path?
Which dependency?
Which schema?
What response/status?
```

This division is one of the biggest steps from beginner FastAPI to professional FastAPI.

---

# 101. Suggested Service API

Your service module should eventually expose functions like:

```python
create_consultation(...)
get_consultation_or_404(...)
list_consultations(...)
update_consultation(...)
void_consultation(...)

create_surgery(...)
get_surgery_or_404(...)
list_surgeries(...)
update_surgery(...)
void_surgery(...)

create_room(...)
get_room_or_404(...)
list_rooms(...)
update_room(...)
void_room(...)
```

Report functions:

```python
build_consultation_report(...)
build_surgery_report(...)
build_room_report(...)
build_total_report(...)
```

Pure calculations stay separate.

---

# 102. Avoid a Giant Generic CRUD Base

It may be tempting to create:

```python
BaseCRUDService[Model]
```

for every finance model.

Do not do that yet.

Why?

Because these entities have different business rules:

```text
Consultation:
    type
    minus_beshming

Surgery:
    surgery_expense

Room:
    no expense
```

Their differences are exactly where business logic lives.

Abstraction should follow stable similarity, not theoretical similarity.

---

# 103. Use Shared Helpers Carefully

Good shared helper:

```python
get_business_datetime_range(...)
```

Good shared helper:

```python
money(...)
```

Good shared helper:

```python
load_doctors(...)
```

Bad shared helper:

```python
do_everything_finance(...)
```

The goal is reuse without hiding the domain.

---

# 104. Doctor Search

Original behavior allows:

```text
GET /doctors?search=cardio
```

You can search:

```python
Doctor.first_name.ilike(...)
Doctor.last_name.ilike(...)
Doctor.specialty.ilike(...)
```

A future frontend can search:

```text
cardio
Aliyev
Vali
```

without needing three separate endpoints.

---

# 105. Data Ownership Model

Think of every finance record as having two dimensions:

```text
WHO RECEIVES THE SHARE?
        ↓
     doctor_id

WHO ENTERED IT?
        ↓
   created_by_id
```

This is fundamental.

For example:

```text
Doctor:
    Dr. Aliyev

Created by:
    Assistant Aziz

Amount:
    200000

Doctor percent:
    40%
```

These are not interchangeable identities.

---

# 106. Why We Do Not Store Calculated Profit

Do not add:

```text
doctor_share
clinic_profit
total_expense
```

to the database unless the business specifically requires them persisted.

They are derived from:

```text
amount
expense
doctor_percent
```

Storing derived values creates synchronization problems:

```text
amount changes
    ↓
doctor_share must change
    ↓
profit must change
```

If you calculate from source values, there is one source of truth.

---

# 107. Exception: Audit/Accounting Requirements

If the business later requires legally frozen accounting documents, then persisted calculated snapshots may become appropriate.

But that would be a new product requirement.

Do not add accounting complexity before it is needed.

---

# 108. Business Date vs Created Date

This distinction is critical.

Suppose a receipt is created:

```text
2026-02-01 01:00
```

but the business date is:

```text
2026-01-31
```

The report should use:

```text
date = 2026-01-31
```

not:

```text
created_at = 2026-02-01
```

Therefore:

```text
created_at
    = database/audit timestamp

date
    = business transaction date
```

Never mix these concepts.

---

# 109. Timezone

The clinic timezone is:

```text
Asia/Tashkent
```

Do not let one endpoint interpret:

```text
2026-01-31
```

in UTC while another interprets it in Tashkent.

That produces inconsistent reports around midnight.

Use the same shared helper everywhere.

---

# 110. API Date Inputs

Reports:

```python
date_from: date | None = None
date_to: date | None = None
```

Records:

```python
date: datetime
```

That makes sense because:

```text
record = exact business timestamp
report = business-day range
```

---

# 111. Date Range Errors

Reject:

```text
date_from > date_to
```

with:

```text
422
```

Example:

```text
date_from=2026-02-01
date_to=2026-01-01
```

Response:

```json
{
  "detail": "date_from cannot be after date_to"
}
```

---

# 112. Report Empty Range

If a valid range contains nothing:

```text
HTTP 200
```

not:

```text
404
```

because the report itself exists.

It simply contains zero values.

---

# 113. Security of Calculated Fields

A client must not send:

```json
{
  "amount": "100000",
  "doctor_percent": "50",
  "doctor_share": "999999"
}
```

Ignore/reject calculated fields entirely.

The backend is authoritative.

Likewise:

```text
created_by_id
```

must always come from:

```python
actor.id
```

Never from request JSON.

---

# 114. Security of Role Fields

A finance request must never accept:

```json
{
  "role": "superadmin"
}
```

Your user role system already handles authorization.

Finance code should only inspect:

```python
actor.role
```

from the authenticated user.

---

# 115. What Happens When a Manager Creates a Record?

Example:

```text
Manager #1
    ↓
POST /consultations
    ↓
created_by_id = Manager #1
```

If later the manager asks:

```text
GET /consultations
```

they see all records because their role grants global visibility.

But the row still remembers:

```text
created_by_id = manager #1
```

This is useful for audit logs later.

---

# 116. What Happens When an Assistant Creates a Record?

```text
Assistant #7
    ↓
POST /consultations
    ↓
created_by_id = assistant #7
```

The assistant can see it because:

```python
created_by_id == current_user.id
```

The assistant cannot change it.

The assistant cannot see:

```text
records created by assistant #8
records created by manager
records created by superadmin
```

unless your final business rules explicitly change that behavior.

---

# 117. Future Audit Log Integration

Your auth layer already provides the actor:

```python
actor: User
```

Finance services should therefore be written in a way that later allows:

```python
await audit_log.create(
    actor=actor,
    action="create_consultation",
    target_id=record.id,
)
```

without changing the architecture.

Do not implement a full audit subsystem in this phase unless it is required.

But leave the actor available at service boundaries.

---

# 118. Logging

Do not log:

```text
passwords
JWT tokens
Redis secrets
full authorization headers
```

Safe application logging can include:

```text
user_id
role
operation
resource_type
resource_id
status
duration
```

For example:

```text
user=uuid...
role=manager
action=create_consultation
resource=uuid...
```

---

# 119. Transaction Logging

For financial operations, useful logs are:

```text
create
update
void
```

and possibly:

```text
report generated
```

But do not log every database query manually.

Let SQLAlchemy/database tooling handle SQL diagnostics during development.

---

# 120. Testing the Database Constraint

You should test that:

```text
doctor deleted
```

does not delete:

```text
consultation
surgery
room
```

Expected:

```text
doctor_id = NULL
```

This proves the behavior is implemented at the database level.

---

# 121. Testing `ON DELETE SET NULL`

Integration test concept:

```python
doctor = Doctor(...)
db.add(doctor)
await db.commit()

consultation = Consultation(
    doctor_id=doctor.id,
    ...
)

db.add(consultation)
await db.commit()

await db.delete(doctor)
await db.commit()

await db.refresh(consultation)

assert consultation.doctor_id is None
```

The exact behavior should ultimately be verified against PostgreSQL, not only SQLite.

---

# 122. Why PostgreSQL Should Be Used for Integration Tests

Your production database is:

```text
PostgreSQL
```

and you rely on:

```text
NUMERIC
ENUM
UUID
FOREIGN KEY
ON DELETE
```

Therefore a production-faithful test database matters.

A unit test for:

```python
consultation_totals()
```

doesn't care about PostgreSQL.

An integration test for:

```text
foreign keys and enum behavior
```

does.

Use the right test level for the right problem.

---

# 123. Test Layers

Think in four levels:

```text
Level 1
pure functions

Level 2
service + database

Level 3
HTTP/API

Level 4
full system/infrastructure
```

You do not need every test at every level.

---

# 124. Testing With Async

Your project is async.

Therefore test services with:

```python
pytest.mark.asyncio
```

or your configured async test mode.

Do not convert your service layer to synchronous code merely to make testing easier.

Your production architecture should remain async end to end.

---

# 125. API Contract Example

Create consultation:

```http
POST /consultations
Authorization: Bearer <access-token>
Content-Type: application/json
```

```json
{
  "type": "korik",
  "receipt_number": 1001,
  "date": "2026-01-15T10:30:00+05:00",
  "amount": "100000.00",
  "doctor_percent": "50.00",
  "minus_beshming": "5000.00",
  "doctor_id": 1
}
```

Response:

```json
{
  "id": 1,
  "type": "korik",
  "receipt_number": 1001,
  "date": "2026-01-15T10:30:00+05:00",
  "amount": "100000.00",
  "doctor_percent": "50.00",
  "minus_beshming": "5000.00",
  "doctor_id": 1,
  "created_by_id": "UUID",
  "is_voided": false,
  "voided_at": null,
  "voided_by_id": null,
  "created_at": "...",
  "updated_at": "..."
}
```

Calculated report values belong in reports, not the raw receipt response unless the frontend explicitly needs them.

---

# 126. Should Raw Receipt Responses Include Calculated Totals?

There are two reasonable choices.

### Option A — Keep CRUD response raw

```text
amount
doctor_percent
expense
```

and calculated values appear in reports.

### Option B — Expose computed fields

```text
doctor_share
clinic_profit
```

The source requirements mainly define these calculations for reports.

For the first implementation, I recommend **Option A** to keep persistence and reporting contracts separate.

If the frontend later needs per-receipt calculated values, add a dedicated read DTO:

```text
ConsultationDetail
```

with calculated fields generated from the same pure calculation functions.

Do not duplicate the formulas.

---

# 127. Add a Detail Calculation Later

Example:

```python
class ConsultationDetail(ConsultationRead):
    doctor_share: Decimal
    expense: Decimal
    clinic_profit: Decimal
```

Build it:

```python
totals = consultation_totals(
    consultation.amount,
    consultation.minus_beshming,
    consultation.doctor_percent,
)
```

Then:

```python
return ConsultationDetail(
    **ConsultationRead.model_validate(
        consultation
    ).model_dump(),
    doctor_share=totals["doctor_share"],
    expense=totals["expense"],
    clinic_profit=totals["clinic_profit"],
)
```

One formula.

Multiple consumers.

---

# 128. Pagination Query Count

A list endpoint usually needs:

```text
1 query for COUNT
1 query for page data
```

This is acceptable for the first implementation.

Later you may optimize with database/window techniques if measurement shows the count query is expensive.

Do not remove total-count information merely to avoid a second query unless the product does not need it.

---

# 129. Offset Pagination

The first API can use:

```text
page
page_size
offset
limit
```

Formula:

```python
offset = (page - 1) * page_size
```

This is simple and matches the requested behavior.

At very large datasets, cursor pagination may become attractive, but do not redesign the API before you need it.

---

# 130. Query Safety

Never concatenate SQL strings like:

```python
f"SELECT * FROM consultations WHERE doctor_id = '{doctor_id}'"
```

Use SQLAlchemy expressions:

```python
Consultation.doctor_id == doctor_id
```

SQLAlchemy handles bound parameters.

---

# 131. Validation of String Fields

For names:

```python
value = value.strip()
```

Do not allow:

```text
"      "
```

Pydantic can enforce:

```python
min_length=1
```

but whitespace should also be normalized.

For usernames, your auth layer should similarly normalize according to its existing policy.

Do not introduce a separate username normalization policy in finance.

---

# 132. Receipt Numbers

The requirements explicitly say:

```text
receipt numbers do not need uniqueness constraints
```

Therefore:

```python
receipt_number = Column(Integer)
```

without:

```text
UNIQUE
```

Do not invent uniqueness.

Two records may legitimately carry the same check/receipt number.

---

# 133. Consultation Type Enum

Use:

```python
class ConsultationType(str, enum.Enum):
    KORIK = "korik"
    QAYTAKORIK = "qaytakorik"
```

Then Pydantic automatically validates:

```json
"type": "korik"
```

and rejects:

```json
"type": "something_else"
```

This is better than accepting arbitrary strings.

---

# 134. Money Limits

The requirements use:

```text
NUMERIC(10, 2)
```

which means the database column has a defined precision/scale.

Keep the Pydantic contract aligned with your database policy.

If the clinic later needs much larger monetary values, change the database precision deliberately through a migration rather than silently allowing larger API values.

---

# 135. Percentage Limits

Database:

```sql
NUMERIC(5, 2)
```

Business rule:

```text
0 <= doctor_percent <= 100
```

Both matter.

An API client can never send:

```text
100.01
```

because Pydantic rejects it.

The database also protects the row.

---

# 136. `minus_beshming` Type

The original Django behavior describes it as an integer defaulting to `5000`.

The FastAPI architecture specifies money fields as:

```text
NUMERIC(10,2)
```

For a cleaner financial model, this guide stores:

```text
Decimal
```

so the system can represent:

```text
5000.00
```

consistently.

This is a deliberate normalization of the financial domain.

If the business guarantees it must always be an integer amount, you can enforce that separately.

---

# 137. Remaining Product Decisions

There are four decisions still called out in the requirements:

```text
1. Should minus_beshming remain 5000?
2. What happens when expense > income?
3. Is business date entered by user or defaulted by server?
4. Is a full audit history required before production?
```

For this guide we choose:

```text
minus_beshming:
    default 5000.00

expense > income:
    reject with 422

business date:
    explicitly supplied by API

full audit history:
    architecture prepared, implementation deferred
```

These are implementation choices, not claims that the original Django project permanently decided them.

If the actual clinic owner chooses differently, update the policy and corresponding tests before production.

---

# 138. Why Business Date Should Be Explicit

The source logic reports by business date.

That makes an explicit request field safer:

```json
{
    "date": "2026-09-07T19:30:00+05:00"
}
```

The server's:

```text
created_at
```

should never silently become the transaction date.

This is especially important when a user enters yesterday's receipt today.

---

# 139. Service Transaction Pattern

A clean create service:

```python
async def create_room(
    db: AsyncSession,
    *,
    actor: User,
    data: RoomCreate,
) -> Room:

    if data.doctor_id:
        await get_doctor_or_404(
            db,
            data.doctor_id,
        )

    record = Room(
        receipt_number=data.receipt_number,
        date=data.date,
        amount=data.amount,
        doctor_percent=data.doctor_percent,
        doctor_id=data.doctor_id,
        created_by_id=actor.id,
    )

    db.add(record)

    await db.commit()
    await db.refresh(record)

    return record
```

One operation.

One commit.

One returned entity.

---

# 140. Avoid Commit Inside Validation Helpers

This is bad:

```python
async def get_doctor_or_404(...):
    ...
    await db.commit()
```

Validation helpers should not unexpectedly mutate transactions.

Keep helpers:

```text
read-only
```

unless their name clearly indicates a write.

---

# 141. Avoid Global Session Objects

Do not do:

```python
db = AsyncSessionLocal()
```

at module import time.

Your existing dependency:

```python
async def get_db():
    ...
```

already provides the correct request lifecycle.

Always inject the session.

---

# 142. Avoid Model-Level Business Methods for This Project

You could write:

```python
consultation.calculate_profit()
```

but for this project the source architecture already defines pure calculation functions.

Keep:

```python
consultation_totals(...)
```

outside SQLAlchemy models.

Why?

Models then remain persistence-focused.

This also allows:

```text
unit tests
report services
detail DTOs
```

to use the same pure functions.

---

# 143. Report Service vs Report Router

Router:

```text
parse dates
get actor
get db
call service
return response
```

Service:

```text
query
filter
load doctors
calculate
group
compose
```

This makes reports easy to test directly.

---

# 144. Total Report Should Reuse Section Services

A dangerous implementation is:

```python
build_total_report():
    query consultations
    calculate consultation
    query surgeries
    calculate surgery
    query rooms
    calculate room
```

while separately maintaining:

```python
build_consultation_report()
build_surgery_report()
build_room_report()
```

This can eventually diverge.

Prefer:

```text
section report services
       ↓
total report composition
```

One calculation source.

---

# 145. Potential Performance Tradeoff

Reusing section reports may mean the total report performs multiple queries.

That is acceptable initially because the priority is correctness.

Later, you can introduce a report query layer that fetches the required datasets in one controlled operation while preserving the same calculation layer.

Again:

```text
measure first
```

---

# 146. Safe Migration Workflow

Before migration:

```bash
alembic current
```

Then:

```bash
alembic revision --autogenerate -m "add doctors and finance"
```

Open the generated file.

Read it.

Then:

```bash
alembic upgrade head
```

Verify:

```bash
alembic current
```

Do not delete migration history to "fix" a development mistake.

Your auth guide already notes that migration history should not be casually deleted/reordered.

---

# 147. Never Use `docker compose down -v` to Troubleshoot

This deletes PostgreSQL volumes/data.

Use:

```bash
docker compose down
```

rather than:

```bash
docker compose down -v
```

unless you intentionally want to destroy the database.

For migration/debugging work, protecting data is part of engineering discipline.

---

# 148. Build Order

Implement in this exact order:

```text
1. Doctor model
2. Doctor schemas
3. Doctor service
4. Doctor router
5. Doctor tests

6. Finance models
7. Alembic migration

8. Calculation functions
9. Calculation tests

10. Consultation vertical slice
11. Surgery vertical slice
12. Room vertical slice

13. Shared date filtering
14. Section reports
15. Total report

16. Permissions
17. Void/archive workflow

18. Integration tests
19. Query/performance review
20. Logging/audit preparation
```

This minimizes the number of moving pieces when debugging.

---

# 149. What "Vertical Slice" Means

A vertical slice means completing one feature from:

```text
database
   ↓
schema
   ↓
service
   ↓
router
   ↓
test
```

before moving on.

For example:

```text
Doctor
```

should be fully usable before you start trying to build:

```text
reports
```

This is much easier to debug than creating 20 empty files first.

---

# 150. First Milestone

Your first milestone is:

```text
Doctor CRUD works
```

Definition of done:

```text
POST /doctors
GET /doctors
GET /doctors/{id}
PATCH /doctors/{id}

Manager can do it
Superadmin can do it
Assistant cannot modify doctors

Pagination works
Search works
404 works
```

Then stop and test before building finance.

---

# 151. Second Milestone

Pure calculations:

```text
consultation_totals
surgery_totals
room_totals
```

Definition of done:

```text
correct formulas
Decimal
ROUND_HALF_UP
0%
100%
zero expense
default deduction
rounding tests
expense policy tests
```

No database required for these tests.

---

# 152. Third Milestone

Consultations.

Definition of done:

```text
create
read
list
filter
patch
void
assistant ownership
manager access
superadmin access
doctor relationship
date filter
```

Then copy the conceptual pattern to:

```text
surgery
room
```

Do not literally copy-and-paste blindly. Compare the business differences.

---

# 153. Fourth Milestone

Reports.

Start:

```text
consultation report
```

Then:

```text
surgery report
room report
```

Finally:

```text
total report
```

The total report should be the easiest report once the section reports are correct.

---

# 154. Endpoint Summary

## Doctors

```text
GET    /doctors
POST   /doctors
GET    /doctors/{doctor_id}
PATCH  /doctors/{doctor_id}
```

## Consultations

```text
GET    /consultations
POST   /consultations
GET    /consultations/{consultation_id}
PATCH  /consultations/{consultation_id}
POST   /consultations/{consultation_id}/void
```

## Surgeries

```text
GET    /surgeries
POST   /surgeries
GET    /surgeries/{surgery_id}
PATCH  /surgeries/{surgery_id}
POST   /surgeries/{surgery_id}/void
```

## Rooms

```text
GET    /rooms
POST   /rooms
GET    /rooms/{room_id}
PATCH  /rooms/{room_id}
POST   /rooms/{room_id}/void
```

## Reports

```text
GET /reports/consultations
GET /reports/surgeries
GET /reports/rooms
GET /reports/total
```

---

# 155. Example Report Requests

Consultations for January:

```text
GET /reports/consultations
    ?date_from=2026-01-01
    &date_to=2026-01-31
```

All finance:

```text
GET /reports/total
    ?date_from=2026-01-01
    &date_to=2026-01-31
```

The same range must be applied consistently to:

```text
consultations
surgeries
rooms
```

---

# 156. Expected Total Formula

The dashboard must satisfy:

```text
total_income
    =
    consultation_income
    + surgery_income
    + room_income
```

```text
total_doctor_share
    =
    consultation_share
    + surgery_share
    + room_share
```

```text
total_expense
    =
    consultation_expense
    + surgery_expense
```

```text
total_clinic_profit
    =
    consultation_profit
    + surgery_profit
    + room_profit
```

And:

```text
room_expense = 0
```

always.

---

# 157. Data Flow Example

Suppose today contains:

```text
Consultation:
    100000
    deduction 5000
    doctor 50%

Surgery:
    2000000
    expense 300000
    doctor 40%

Room:
    500000
    doctor 20%
```

Consultation:

```text
income = 100000
doctor = 47500
expense = 5000
profit = 47500
```

Surgery:

```text
income = 2000000
doctor = 680000
expense = 300000
profit = 1020000
```

Room:

```text
income = 500000
doctor = 100000
expense = 0
profit = 400000
```

Dashboard:

```text
income:
    2,600,000

doctor:
    827,500

expense:
    305,000

profit:
    1,467,500
```

Always verify these totals using the exact Decimal implementation rather than manually maintaining parallel formulas.

---

# 158. Senior-Level Invariants

A strong engineer starts thinking in invariants.

Examples:

```text
doctor_percent ∈ [0, 100]

amount >= 0

expense >= 0

expense <= amount
```

for this guide's chosen policy.

And:

```text
clinic_profit
=
income - doctor_share - expense
```

For total:

```text
total_profit
=
total_income
-
total_doctor_share
-
total_expense
```

These should be tested.

---

# 159. Another Important Invariant

For consultation:

```text
amount
=
doctor_share
+
clinic_profit
+
minus_beshming
```

For surgery:

```text
amount
=
doctor_share
+
clinic_profit
+
surgery_expense
```

For room:

```text
amount
=
doctor_share
+
clinic_profit
```

These are excellent property-style test ideas.

---

# 160. Why This Matters

Suppose a future developer changes:

```python
clinic_profit = amount - doctor_share
```

for consultations.

The normal example tests might still pass for:

```text
minus_beshming = 0
```

but fail to represent the actual business rule.

The invariant test:

```text
amount =
    doctor_share
    + clinic_profit
    + expense
```

would catch the regression.

---

# 161. Code Review Checklist

When reviewing every PR, ask:

### Models

```text
Is persistence correct?
Are constraints in the database?
Are relationships nullable where required?
```

### Schemas

```text
Can a client submit server-owned fields?
Are numeric bounds enforced?
Does PATCH distinguish omitted vs null?
```

### Services

```text
Is business logic here?
Is the transaction coherent?
Are relationships validated?
```

### Routers

```text
Is the route thin?
Is authorization applied?
Is the correct response schema returned?
```

### Reports

```text
Are voided records excluded?
Are date semantics consistent?
Are calculations reused?
Are Decimal values preserved?
```

---

# 162. Common Beginner Mistakes to Avoid

## Mistake 1: Calculating inside the router

Bad:

```python
@router.get(...)
async def report(...):
    for record in records:
        ...
```

Move this to:

```text
finance/reports.py
```

---

## Mistake 2: Using floats

Bad:

```python
amount: float
```

Prefer:

```python
amount: Decimal
```

---

## Mistake 3: Trusting `created_by_id` from the client

Bad:

```python
created_by_id=data.created_by_id
```

Correct:

```python
created_by_id=actor.id
```

---

## Mistake 4: Using Python-only foreign-key logic

Bad:

```python
if doctor:
    ...
```

and relying on that for deletion history.

Database must enforce:

```text
ON DELETE SET NULL
```

---

## Mistake 5: Physical deletion of finance rows

Avoid:

```python
await db.delete(record)
```

for normal finance lifecycle operations.

Void instead.

---

## Mistake 6: N+1 doctor queries

Never call:

```python
await db.get(Doctor, ...)
```

inside a report loop.

---

## Mistake 7: Repeating formulas

One trusted calculation layer.

---

## Mistake 8: Returning `null` totals

Empty reports use:

```text
0.00
```

---

# 163. How This Moves You Toward Senior/Middle Engineering

The goal is not:

```text
"I can write a FastAPI CRUD endpoint."
```

The goal is:

```text
"I can design a system whose behavior stays correct as it grows."
```

You are practicing:

```text
domain modeling
transaction boundaries
authorization
object-level permissions
database constraints
Decimal arithmetic
time-zone semantics
stable pagination
N+1 prevention
pure business logic
API contracts
migration discipline
test layering
```

Those are much more important than memorizing FastAPI decorators.

---

# 164. Your Mental Model

For every feature, ask these questions in order:

```text
1. What is the domain object?

2. What are its invariants?

3. Who is allowed to act?

4. What data is user input?

5. What data is server-owned?

6. What must be atomic?

7. What belongs in the database?

8. What belongs in pure Python?

9. What must be tested independently?

10. What happens when something is deleted?
```

This thought process is more transferable than any particular code template.

---

# 165. Final Architecture

The complete application should look conceptually like:

```text
                         ┌───────────────┐
                         │    FastAPI    │
                         └───────┬───────┘
                                 │
                          authentication
                                 │
                     ┌───────────▼───────────┐
                     │      Users/Auth       │
                     │ JWT + Redis + Roles   │
                     └───────────┬───────────┘
                                 │
                     ┌───────────▼───────────┐
                     │       Routers         │
                     └───────────┬───────────┘
                                 │
                     ┌───────────▼───────────┐
                     │       Services        │
                     └───────┬─────┬─────────┘
                             │     │
              ┌──────────────┘     └──────────────┐
              ▼                                   ▼
      ┌───────────────┐                  ┌────────────────┐
      │   PostgreSQL  │                  │ Pure Financial │
      │ SQLAlchemy    │                  │  Calculations  │
      └───────────────┘                  └───────┬────────┘
                                                 │
                                      ┌──────────▼──────────┐
                                      │       Reports       │
                                      └──────────┬──────────┘
                                                 │
                                      ┌──────────▼──────────┐
                                      │   Total Dashboard   │
                                      └─────────────────────┘
```

---

# 166. Definition of Done

This phase is complete when:

## Database

```text
[ ] doctors table exists
[ ] consultations table exists
[ ] surgeries table exists
[ ] rooms table exists

[ ] Integer auto-increment IDs for doctors and finance records
[ ] NUMERIC money
[ ] Decimal usage
[ ] doctor FKs are nullable
[ ] ON DELETE SET NULL
[ ] created_by_id is non-null
[ ] void fields exist
[ ] constraints exist
```

## Doctors

```text
[ ] CRUD works
[ ] search works
[ ] pagination works
[ ] role authorization works
```

## Consultations

```text
[ ] create
[ ] read
[ ] list
[ ] filter
[ ] update
[ ] void
[ ] ownership filtering
```

## Surgeries

```text
[ ] create
[ ] read
[ ] list
[ ] filter
[ ] update
[ ] void
```

## Rooms

```text
[ ] create
[ ] read
[ ] list
[ ] filter
[ ] update
[ ] void
```

## Calculations

```text
[ ] Decimal
[ ] HALF_UP
[ ] per-receipt doctor share rounding
[ ] consultation formula
[ ] surgery formula
[ ] room formula
```

## Reports

```text
[ ] consultation report
[ ] surgery report
[ ] room report
[ ] total report
[ ] shared date filtering
[ ] doctor grouping
[ ] empty ranges
[ ] voided records excluded
```

## Security

```text
[ ] assistant sees own records
[ ] assistant cannot update
[ ] manager sees all
[ ] superadmin sees all
[ ] created_by_id never comes from client
```

## Tests

```text
[ ] calculation tests
[ ] validation tests
[ ] CRUD tests
[ ] permissions
[ ] date boundaries
[ ] N+1 review
[ ] doctor deletion behavior
[ ] void workflow
[ ] dashboard consistency
```

---

# 167. The Development Sequence I Want You to Follow

Do **not** create all the files and paste all the code at once.

Work in this sequence:

```text
PHASE 1
Doctor model
        ↓
migration
        ↓
Doctor schemas
        ↓
Doctor service
        ↓
Doctor router
        ↓
Doctor tests

PHASE 2
Financial models
        ↓
migration
        ↓
inspect migration carefully

PHASE 3
Pure Decimal calculations
        ↓
calculation tests

PHASE 4
Consultation vertical slice

PHASE 5
Surgery vertical slice

PHASE 6
Room vertical slice

PHASE 7
Shared date filtering

PHASE 8
Section reports

PHASE 9
Total report

PHASE 10
Void workflow

PHASE 11
Authorization edge cases

PHASE 12
Performance and query review

PHASE 13
Audit/logging integration
```

At the end of every phase:

```text
run tests
inspect SQL/migrations where relevant
verify behavior in Swagger
only then move forward
```

---

# 168. Final Engineering Principle

The most important lesson in this project is:

```text
Do not make the code "work".

Make the business rules impossible to accidentally break.
```

That means:

```text
Pydantic
    protects requests

SQLAlchemy/PostgreSQL constraints
    protect data

services
    protect business rules

dependencies
    protect permissions

pure calculation functions
    protect financial formulas

tests
    protect behavior

migrations
    protect database evolution
```

When these layers are clear, the project becomes much easier to extend.

---

# 169. Next Implementation Target

The immediate coding target should be:

```text
PHASE 1 — DOCTOR VERTICAL SLICE
```

Implement only:

```text
app/doctors/models.py
app/doctors/schemas.py
app/doctors/service.py
app/doctors/router.py
```

Then:

```text
Alembic migration
pytest tests
Swagger verification
```

Do not begin consultations until Doctor CRUD is correct.

Once the Doctor slice is stable, the rest of the financial system has a solid foundation.


---

# 170. Complete Reference Implementation

The sections above teach the architecture. This section gives you a concrete implementation target for the first production-style version.

Use these files as the reference implementation, then write them yourself rather than treating the guide as a code dump.

## 170.1 Final `finance/models.py`

```python
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConsultationType(str, enum.Enum):
    KORIK = "korik"
    QAYTAKORIK = "qaytakorik"


class Consultation(Base):
    __tablename__ = "consultations"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_consultations_amount_non_negative",
        ),
        CheckConstraint(
            "doctor_percent >= 0 AND doctor_percent <= 100",
            name="ck_consultations_doctor_percent_range",
        ),
        CheckConstraint(
            "minus_beshming >= 0",
            name="ck_consultations_minus_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    type: Mapped[ConsultationType] = mapped_column(
        Enum(ConsultationType, name="consultation_type"),
        nullable=False,
    )

    receipt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    doctor_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    minus_beshming: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        default=Decimal("5000.00"),
        server_default="5000.00",
    )

    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    is_voided: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
        nullable=False,
    )

    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Surgery(Base):
    __tablename__ = "surgeries"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_surgeries_amount_non_negative",
        ),
        CheckConstraint(
            "surgery_expense >= 0",
            name="ck_surgeries_expense_non_negative",
        ),
        CheckConstraint(
            "doctor_percent >= 0 AND doctor_percent <= 100",
            name="ck_surgeries_doctor_percent_range",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    receipt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    surgery_expense: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    doctor_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    is_voided: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
        nullable=False,
    )

    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Room(Base):
    __tablename__ = "rooms"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_rooms_amount_non_negative",
        ),
        CheckConstraint(
            "doctor_percent >= 0 AND doctor_percent <= 100",
            name="ck_rooms_doctor_percent_range",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    receipt_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    doctor_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("doctors.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    is_voided: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
        nullable=False,
    )

    voided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
```

## 170.2 Complete calculations

```python
from decimal import Decimal, ROUND_HALF_UP


HUNDRED = Decimal("100")
TWO_PLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(
        TWO_PLACES,
        rounding=ROUND_HALF_UP,
    )


def consultation_totals(
    amount: Decimal,
    minus_beshming: Decimal | None,
    doctor_percent: Decimal,
) -> dict[str, Decimal]:

    minus = minus_beshming or Decimal("0.00")

    doctor_share = money(
        (amount - minus) * doctor_percent / HUNDRED
    )

    clinic_profit = money(
        amount - doctor_share - minus
    )

    return {
        "income": money(amount),
        "doctor_share": doctor_share,
        "expense": money(minus),
        "clinic_profit": clinic_profit,
    }


def surgery_totals(
    amount: Decimal,
    surgery_expense: Decimal | None,
    doctor_percent: Decimal,
) -> dict[str, Decimal]:

    expense = surgery_expense or Decimal("0.00")

    doctor_share = money(
        (amount - expense) * doctor_percent / HUNDRED
    )

    clinic_profit = money(
        amount - doctor_share - expense
    )

    return {
        "income": money(amount),
        "doctor_share": doctor_share,
        "expense": money(expense),
        "clinic_profit": clinic_profit,
    }


def room_totals(
    amount: Decimal,
    doctor_percent: Decimal,
) -> dict[str, Decimal]:

    doctor_share = money(
        amount * doctor_percent / HUNDRED
    )

    clinic_profit = money(
        amount - doctor_share
    )

    return {
        "income": money(amount),
        "doctor_share": doctor_share,
        "expense": Decimal("0.00"),
        "clinic_profit": clinic_profit,
    }
```

## 170.3 Finance schemas

```python
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from app.finance.models import ConsultationType


T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
    pages: int


class ConsultationCreate(BaseModel):
    type: ConsultationType
    receipt_number: int = Field(gt=0)
    date: datetime
    amount: Decimal = Field(ge=0)
    doctor_percent: Decimal = Field(ge=0, le=100)
    minus_beshming: Decimal | None = Field(
        default=Decimal("5000.00"),
        ge=0,
    )
    doctor_id: int | None = None


class ConsultationUpdate(BaseModel):
    type: ConsultationType | None = None
    receipt_number: int | None = Field(default=None, gt=0)
    date: datetime | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    doctor_percent: Decimal | None = Field(
        default=None,
        ge=0,
        le=100,
    )
    minus_beshming: Decimal | None = Field(
        default=None,
        ge=0,
    )
    doctor_id: int | None = None


class ConsultationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: ConsultationType
    receipt_number: int
    date: datetime
    amount: Decimal
    doctor_percent: Decimal
    minus_beshming: Decimal | None
    doctor_id: int | None
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class SurgeryCreate(BaseModel):
    receipt_number: int = Field(gt=0)
    date: datetime
    amount: Decimal = Field(ge=0)
    surgery_expense: Decimal = Field(ge=0)
    doctor_percent: Decimal = Field(ge=0, le=100)
    doctor_id: int | None = None


class SurgeryUpdate(BaseModel):
    receipt_number: int | None = Field(default=None, gt=0)
    date: datetime | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    surgery_expense: Decimal | None = Field(default=None, ge=0)
    doctor_percent: Decimal | None = Field(default=None, ge=0, le=100)
    doctor_id: int | None = None


class SurgeryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: int
    date: datetime
    amount: Decimal
    surgery_expense: Decimal
    doctor_percent: Decimal
    doctor_id: int | None
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class RoomCreate(BaseModel):
    receipt_number: int | None = Field(default=None, gt=0)
    date: datetime
    amount: Decimal = Field(ge=0)
    doctor_percent: Decimal = Field(ge=0, le=100)
    doctor_id: int | None = None


class RoomUpdate(BaseModel):
    receipt_number: int | None = Field(default=None, gt=0)
    date: datetime | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    doctor_percent: Decimal | None = Field(default=None, ge=0, le=100)
    doctor_id: int | None = None


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_number: int | None
    date: datetime
    amount: Decimal
    doctor_percent: Decimal
    doctor_id: int | None
    created_by_id: uuid.UUID
    is_voided: bool
    voided_at: datetime | None
    voided_by_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
```

## 170.4 Date filtering helper

```python
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


CLINIC_TZ = ZoneInfo("Asia/Tashkent")


def business_datetime_range(
    date_from: date | None,
    date_to: date | None,
) -> tuple[datetime | None, datetime | None]:

    if (
        date_from is not None
        and date_to is not None
        and date_from > date_to
    ):
        raise ValueError(
            "date_from cannot be after date_to"
        )

    start = (
        datetime.combine(
            date_from,
            time.min,
            tzinfo=CLINIC_TZ,
        )
        if date_from
        else None
    )

    end = (
        datetime.combine(
            date_to + timedelta(days=1),
            time.min,
            tzinfo=CLINIC_TZ,
        )
        if date_to
        else None
    )

    return start, end
```

## 170.5 Doctor lookup helper

```python
import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.doctors.models import Doctor


async def require_doctor(
    db: AsyncSession,
    doctor_id: int | None,
) -> None:

    if doctor_id is None:
        return

    doctor = await db.get(
        Doctor,
        doctor_id,
    )

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )
```

## 170.6 Expense policy

```python
from decimal import Decimal

from fastapi import HTTPException, status


def require_expense_not_greater_than_income(
    *,
    amount: Decimal,
    expense: Decimal,
) -> None:

    if expense > amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Expense cannot exceed amount",
        )
```

Consultation:

```python
require_expense_not_greater_than_income(
    amount=data.amount,
    expense=data.minus_beshming or Decimal("0.00"),
)
```

Surgery:

```python
require_expense_not_greater_than_income(
    amount=data.amount,
    expense=data.surgery_expense,
)
```

---

# 171. Complete Consultation Service

```python
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.doctors.models import Doctor
from app.finance.calculations import money
from app.finance.models import Consultation
from app.finance.schemas import (
    ConsultationCreate,
    ConsultationUpdate,
)
from app.users.models import User, UserRoleEnum


async def create_consultation(
    db: AsyncSession,
    *,
    actor: User,
    data: ConsultationCreate,
) -> Consultation:

    await require_doctor(db, data.doctor_id)

    require_expense_not_greater_than_income(
        amount=data.amount,
        expense=data.minus_beshming or Decimal("0.00"),
    )

    record = Consultation(
        type=data.type,
        receipt_number=data.receipt_number,
        date=data.date,
        amount=data.amount,
        doctor_percent=data.doctor_percent,
        minus_beshming=data.minus_beshming,
        doctor_id=data.doctor_id,
        created_by_id=actor.id,
    )

    db.add(record)

    await db.commit()
    await db.refresh(record)

    return record


async def get_consultation_or_404(
    db: AsyncSession,
    consultation_id: int,
) -> Consultation:

    record = await db.get(
        Consultation,
        consultation_id,
    )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Consultation not found",
        )

    return record


async def update_consultation(
    db: AsyncSession,
    *,
    consultation: Consultation,
    data: ConsultationUpdate,
) -> Consultation:

    changes = data.model_dump(
        exclude_unset=True,
    )

    final_amount = changes.get(
        "amount",
        consultation.amount,
    )

    final_minus = changes.get(
        "minus_beshming",
        consultation.minus_beshming,
    )

    if final_minus is not None:
        require_expense_not_greater_than_income(
            amount=final_amount,
            expense=final_minus,
        )

    if "doctor_id" in changes:
        await require_doctor(
            db,
            changes["doctor_id"],
        )

    for field, value in changes.items():
        setattr(
            consultation,
            field,
            value,
        )

    await db.commit()
    await db.refresh(consultation)

    return consultation


async def list_consultations(
    db: AsyncSession,
    *,
    actor: User,
    doctor_id: int | None,
    consultation_type,
    date_from,
    date_to,
    page: int,
    page_size: int,
):
    stmt = select(Consultation).where(
        Consultation.is_voided.is_(False)
    )

    if actor.role == UserRoleEnum.ASSISTANT:
        stmt = stmt.where(
            Consultation.created_by_id == actor.id
        )

    if doctor_id is not None:
        stmt = stmt.where(
            Consultation.doctor_id == doctor_id
        )

    if consultation_type is not None:
        stmt = stmt.where(
            Consultation.type == consultation_type
        )

    start, end = business_datetime_range(
        date_from,
        date_to,
    )

    if start is not None:
        stmt = stmt.where(
            Consultation.date >= start
        )

    if end is not None:
        stmt = stmt.where(
            Consultation.date < end
        )

    count_stmt = select(
        func.count()
    ).select_from(
        stmt.order_by(None).subquery()
    )

    total = (
        await db.execute(count_stmt)
    ).scalar_one()

    stmt = (
        stmt
        .order_by(
            Consultation.date.desc(),
            Consultation.id.desc(),
        )
        .offset(
            (page - 1) * page_size
        )
        .limit(page_size)
    )

    result = await db.execute(stmt)

    return list(result.scalars().all()), total


async def void_consultation(
    db: AsyncSession,
    *,
    consultation: Consultation,
    actor: User,
) -> Consultation:

    if consultation.is_voided:
        raise HTTPException(
            status_code=409,
            detail="Consultation is already voided",
        )

    consultation.is_voided = True
    consultation.voided_at = datetime.now(timezone.utc)
    consultation.voided_by_id = actor.id

    await db.commit()
    await db.refresh(consultation)

    return consultation
```

---

# 172. Building Surgery and Room Services

Do not blindly make generic CRUD.

Their create/update services follow the same transaction pattern, but their business validation differs.

Surgery:

```python
async def create_surgery(
    db,
    *,
    actor,
    data,
):
    await require_doctor(db, data.doctor_id)

    require_expense_not_greater_than_income(
        amount=data.amount,
        expense=data.surgery_expense,
    )

    record = Surgery(
        receipt_number=data.receipt_number,
        date=data.date,
        amount=data.amount,
        surgery_expense=data.surgery_expense,
        doctor_percent=data.doctor_percent,
        doctor_id=data.doctor_id,
        created_by_id=actor.id,
    )

    db.add(record)

    await db.commit()
    await db.refresh(record)

    return record
```

Room:

```python
async def create_room(
    db,
    *,
    actor,
    data,
):
    await require_doctor(db, data.doctor_id)

    record = Room(
        receipt_number=data.receipt_number,
        date=data.date,
        amount=data.amount,
        doctor_percent=data.doctor_percent,
        doctor_id=data.doctor_id,
        created_by_id=actor.id,
    )

    db.add(record)

    await db.commit()
    await db.refresh(record)

    return record
```

Notice the important difference:

```text
Surgery:
    validates expense

Room:
    has no expense
```

---

# 173. Complete Permission Matrix

| Operation | Superadmin | Manager | Assistant |
|---|---:|---:|---:|
| View all doctors | Yes | Yes | No |
| Create doctor | Yes | Yes | No |
| Update doctor | Yes | Yes | No |
| View all finance | Yes | Yes | No |
| Create consultation | Yes | Yes | Yes |
| Create surgery | Yes | Yes | Yes |
| Create room | Yes | Yes | Yes |
| View own finance | Yes | Yes | Yes |
| View other users' assistant records | Yes | Yes | No |
| Update finance | Yes | Yes | No |
| Void finance | Yes | Yes | No |
| Section reports | Yes | Yes | Own records |
| Total report | Yes | Yes | Own records |

This is the practical interpretation of the confirmed permission rules.

---

# 174. Full Finance Router Pattern

```python
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.finance.models import ConsultationType
from app.finance.schemas import (
    ConsultationCreate,
    ConsultationRead,
    ConsultationUpdate,
    PaginatedResponse,
)
from app.finance.service import (
    create_consultation,
    get_consultation_or_404,
    list_consultations,
    update_consultation,
    void_consultation,
)
from app.users.dependencies import (
    get_current_user,
    require_roles,
)
from app.users.models import User, UserRoleEnum


router = APIRouter(
    tags=["Finance"],
)
```

Create:

```python
@router.post(
    "/consultations",
    response_model=ConsultationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_consultation_endpoint(
    data: ConsultationCreate,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_consultation(
        db,
        actor=actor,
        data=data,
    )
```

List:

```python
@router.get(
    "/consultations",
    response_model=PaginatedResponse[ConsultationRead],
)
async def list_consultations_endpoint(
    doctor_id: int | None = None,
    type: ConsultationType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await list_consultations(
        db,
        actor=actor,
        doctor_id=doctor_id,
        consultation_type=type,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )

    return PaginatedResponse(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        pages=(total + page_size - 1) // page_size,
    )
```

Get:

```python
@router.get(
    "/consultations/{consultation_id}",
    response_model=ConsultationRead,
)
async def get_consultation_endpoint(
    consultation_id: int,
    actor: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    record = await get_consultation_or_404(
        db,
        consultation_id,
    )

    if (
        actor.role == UserRoleEnum.ASSISTANT
        and record.created_by_id != actor.id
    ):
        from fastapi import HTTPException

        raise HTTPException(
            status_code=403,
            detail="You do not have permission to view this record",
        )

    return record
```

Update:

```python
@router.patch(
    "/consultations/{consultation_id}",
    response_model=ConsultationRead,
)
async def update_consultation_endpoint(
    consultation_id: int,
    data: ConsultationUpdate,
    actor: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    record = await get_consultation_or_404(
        db,
        consultation_id,
    )

    return await update_consultation(
        db,
        consultation=record,
        data=data,
    )
```

Void:

```python
@router.post(
    "/consultations/{consultation_id}/void",
    response_model=ConsultationRead,
)
async def void_consultation_endpoint(
    consultation_id: int,
    actor: User = Depends(
        require_roles(
            UserRoleEnum.SUPERADMIN,
            UserRoleEnum.MANAGER,
        )
    ),
    db: AsyncSession = Depends(get_db),
):
    record = await get_consultation_or_404(
        db,
        consultation_id,
    )

    return await void_consultation(
        db,
        consultation=record,
        actor=actor,
    )
```

Repeat the exact HTTP pattern for surgery and room while keeping their service/business rules separate.

---

# 175. Report Implementation Pattern

A report function should look like:

```python
async def build_surgery_report(
    db: AsyncSession,
    *,
    actor: User,
    date_from: date | None,
    date_to: date | None,
) -> SurgeryReport:

    stmt = select(Surgery).where(
        Surgery.is_voided.is_(False)
    )

    if actor.role == UserRoleEnum.ASSISTANT:
        stmt = stmt.where(
            Surgery.created_by_id == actor.id
        )

    start, end = business_datetime_range(
        date_from,
        date_to,
    )

    if start is not None:
        stmt = stmt.where(
            Surgery.date >= start
        )

    if end is not None:
        stmt = stmt.where(
            Surgery.date < end
        )

    records = (
        await db.execute(stmt)
    ).scalars().all()

    total_income = Decimal("0.00")
    total_doctor_share = Decimal("0.00")
    total_expense = Decimal("0.00")
    total_clinic_profit = Decimal("0.00")

    for record in records:
        totals = surgery_totals(
            record.amount,
            record.surgery_expense,
            record.doctor_percent,
        )

        total_income += totals["income"]
        total_doctor_share += totals["doctor_share"]
        total_expense += totals["expense"]
        total_clinic_profit += totals["clinic_profit"]

    return SurgeryReport(
        surgery_total_income=money(total_income),
        surgery_total_doctor_share=money(
            total_doctor_share
        ),
        surgery_total_expense=money(
            total_expense
        ),
        surgery_total_clinic_profit=money(
            total_clinic_profit
        ),
        surgery_doctor_shares=[],
    )
```

Then add the doctor grouping described earlier.

---

# 176. More Important Than the Code: Know Why It Is Structured This Way

The service receives:

```python
actor: User
```

because:

```text
authorization
    is part of the business operation
```

The service receives:

```python
data
```

because:

```text
the service operates on validated input
```

The service receives:

```python
db
```

because:

```text
persistence belongs below the HTTP layer
```

The router does not receive a prebuilt SQL query because:

```text
the router should not know persistence rules
```

---

# 177. Complete Testing Roadmap

Run:

```bash
pytest tests/finance/test_calculations.py -q
```

first.

Then:

```bash
pytest tests/doctors -q
```

Then:

```bash
pytest tests/finance/test_consultations.py -q
```

Then:

```bash
pytest tests/finance/test_surgeries.py -q
```

Then:

```bash
pytest tests/finance/test_rooms.py -q
```

Then:

```bash
pytest tests/finance/test_reports.py -q
```

Finally:

```bash
pytest -q
```

The order matters because failures become easier to localize.

---

# 178. Coverage

Your project uses coverage reporting.

Run:

```bash
coverage run -m pytest
```

Then:

```bash
coverage report
```

Generate HTML:

```bash
coverage html
```

Open:

```text
htmlcov/index.html
```

Do not chase 100% coverage blindly.

Prioritize:

```text
financial formulas
permissions
business validation
report filtering
void behavior
database relationships
```

---

# 179. What High-Value Tests Look Like

Bad coverage:

```python
def test_function_exists():
    ...
```

Good coverage:

```python
def test_expense_exceeding_income_is_rejected():
    ...
```

Good:

```python
def test_assistant_cannot_view_other_assistant_record():
    ...
```

Good:

```python
def test_voided_receipt_is_excluded_from_report():
    ...
```

Good:

```python
def test_doctor_deletion_preserves_finance_row():
    ...
```

Test business consequences.

---

# 180. Production Readiness Review

Before calling this module "done", inspect:

```text
[ ] no finance business logic in routers
[ ] no float money calculations
[ ] every report excludes voided records
[ ] assistants are filtered server-side
[ ] client cannot provide created_by_id
[ ] expense policy has tests
[ ] date semantics are centralized
[ ] doctor deletion preserves history
[ ] migrations are reviewed
[ ] no physical finance DELETE
[ ] Decimal rounding has tests
[ ] total report reconciles section reports
```

---

# 181. Your Next Learning Exercise

After implementing the Doctor slice, do the Consultation slice yourself.

Before looking at the reference code, write:

```text
Model
Schema
Service
Router
Tests
Migration
```

Then compare your implementation against the architecture.

The question should not be:

```text
"Did I type the same code?"
```

The question should be:

```text
"Did I preserve the same invariants and boundaries?"
```

That is the difference between copying code and engineering software.

---

# 182. Final Project Philosophy

Use this project to learn five things deeply:

```text
1. SQLAlchemy 2.0 async
2. FastAPI dependency-driven authorization
3. Service-layer domain logic
4. Decimal-safe financial calculations
5. Database-backed correctness
```

Do not measure your progress by the number of endpoints you can produce.

Measure it by whether you can explain:

```text
why a field exists
why a query is written that way
why a transaction starts/ends there
why a permission belongs in a dependency
why a formula belongs in a pure function
why a record is voided instead of deleted
why a date boundary is implemented with an exclusive end
```

When you can explain those decisions without looking at the guide, you are learning the engineering skill rather than memorizing FastAPI syntax.

---

# 183. Source Alignment

This implementation preserves the documented source behavior and architecture:

- Doctor is the shared parent entity for consultation, surgery, and room records.
- Finance records use nullable doctor references with `SET NULL`.
- Consultation, surgery, and room formulas remain separate.
- Reports use business dates.
- Date ranges are inclusive.
- Monetary calculations use Decimal.
- Doctor shares are rounded per receipt before aggregation.
- Empty report totals are zero.
- The total report is composed from the three sections.
- Integer IDs are used for doctors and finance records; user IDs remain UUIDs.
- Assistant visibility is ownership-based.
- Financial history is preserved through void/archive behavior.

Where this guide makes an implementation choice for a previously open requirement, the choice is explicitly marked: expense greater than income is rejected, business date is supplied by the client, and full audit-log writing is deferred.
