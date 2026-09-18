"""index consultations, surgeries and rooms

The three finance tables carried no indexes at all beyond their primary keys,
while every other table (duty_entries, salary_payments, pharmacy_entries,
expenses) got them when it was created. They are also the three tables that
every report, every Kvitansiyalar page load and every salary calculation
reads, so each of those was a sequential scan.

Three indexes per table, shaped to the queries that actually run:

* (is_voided, date) — the dominant listing/report predicate,
  `is_voided = false AND date >= :start AND date < :end`. The leading column
  also serves Audit Jurnali's `is_voided = true` scan.
* (doctor_id, is_voided, date) — app.salary.service._sum_doctor_share, which
  adds `doctor_id = :staff_id` to the same shape and runs once per doctor per
  Oyliklar load.
* (created_by_id) — the assistant ownership filter in
  _apply_assistant_ownership, and the "Kim qo'shgan" report filter.

Revision ID: a2c9e4b70d13
Revises: e1a4c7d90b26
Create Date: 2026-09-18

"""
from alembic import op

revision = "a2c9e4b70d13"
down_revision = "e1a4c7d90b26"
branch_labels = None
depends_on = None

_TABLES = ("consultations", "surgeries", "rooms")


def upgrade() -> None:
    for table in _TABLES:
        op.create_index(
            f"ix_{table}_voided_date", table, ["is_voided", "date"], unique=False
        )
        op.create_index(
            f"ix_{table}_doctor_voided_date",
            table,
            ["doctor_id", "is_voided", "date"],
            unique=False,
        )
        op.create_index(
            f"ix_{table}_created_by_id", table, ["created_by_id"], unique=False
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"ix_{table}_created_by_id", table_name=table)
        op.drop_index(f"ix_{table}_doctor_voided_date", table_name=table)
        op.drop_index(f"ix_{table}_voided_date", table_name=table)
