"""merge doctors into staff

Revision ID: 7f1a9c2d4e6b
Revises: 616148e27a8d
Create Date: 2026-09-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f1a9c2d4e6b'
down_revision: Union[str, Sequence[str], None] = '616148e27a8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table('doctors', 'staff')

    # ALTER TABLE ... ADD COLUMN needs the enum type to already exist —
    # unlike op.create_table, add_column does not create it implicitly.
    staff_role = sa.Enum('doctor', 'nurse', 'other', name='staff_role')
    staff_status = sa.Enum('active', 'inactive', name='staff_status')
    staff_role.create(op.get_bind(), checkfirst=True)
    staff_status.create(op.get_bind(), checkfirst=True)

    # role: every existing row was a doctor, so backfill via server_default,
    # then drop the default so future inserts must supply it explicitly
    # (same discipline this project already applies to minus_beshming).
    op.add_column(
        'staff',
        sa.Column(
            'role',
            sa.Enum('doctor', 'nurse', 'other', name='staff_role', create_type=False),
            nullable=False,
            server_default='doctor',
        ),
    )
    op.alter_column('staff', 'role', server_default=None)

    op.add_column(
        'staff',
        sa.Column('fixed_salary', sa.Numeric(precision=12, scale=0), nullable=True),
    )

    op.add_column(
        'staff',
        sa.Column(
            'status',
            sa.Enum('active', 'inactive', name='staff_status', create_type=False),
            nullable=False,
            server_default='active',
        ),
    )
    op.alter_column('staff', 'status', server_default=None)

    op.add_column('staff', sa.Column('hire_date', sa.Date(), nullable=True))

    op.alter_column(
        'staff',
        'specialty',
        existing_type=sa.String(length=50),
        nullable=True,
    )

    # Hand-added: autogenerate doesn't diff CheckConstraints.
    op.create_check_constraint(
        'ck_staff_fixed_salary_doctor_null',
        'staff',
        "role != 'doctor' OR fixed_salary IS NULL",
    )
    op.create_check_constraint(
        'ck_staff_fixed_salary_non_negative',
        'staff',
        'fixed_salary IS NULL OR fixed_salary >= 0',
    )

    # Repoint the 3 existing finance FKs from doctors.id to staff.id.
    # Column names are unchanged (doctor_id) — only the FK target moves.
    for table in ('consultations', 'surgeries', 'rooms'):
        op.drop_constraint(f'{table}_doctor_id_fkey', table, type_='foreignkey')
        op.create_foreign_key(
            f'{table}_doctor_id_fkey',
            table,
            'staff',
            ['doctor_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('consultations', 'surgeries', 'rooms'):
        op.drop_constraint(f'{table}_doctor_id_fkey', table, type_='foreignkey')
        op.create_foreign_key(
            f'{table}_doctor_id_fkey',
            table,
            'doctors',
            ['doctor_id'],
            ['id'],
            ondelete='SET NULL',
        )

    op.drop_constraint('ck_staff_fixed_salary_non_negative', 'staff', type_='check')
    op.drop_constraint('ck_staff_fixed_salary_doctor_null', 'staff', type_='check')

    op.alter_column(
        'staff',
        'specialty',
        existing_type=sa.String(length=50),
        nullable=False,
    )

    op.drop_column('staff', 'hire_date')
    op.drop_column('staff', 'status')
    op.drop_column('staff', 'fixed_salary')
    op.drop_column('staff', 'role')

    op.rename_table('staff', 'doctors')

    sa.Enum(name='staff_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='staff_role').drop(op.get_bind(), checkfirst=True)
