"""create duty_entries and salary_payments

Revision ID: 9b3e5d7f1a2c
Revises: 7f1a9c2d4e6b
Create Date: 2026-09-16 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b3e5d7f1a2c'
down_revision: Union[str, Sequence[str], None] = '7f1a9c2d4e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'duty_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('staff_id', sa.Integer(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=0), nullable=False),
        sa.Column('created_by_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_voided', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('voided_by_id', sa.Uuid(), nullable=True),
        sa.CheckConstraint('amount >= 0', name='ck_duty_entries_amount_non_negative'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['voided_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_duty_entries_staff_id', 'duty_entries', ['staff_id'], unique=False)
    op.create_index('ix_duty_entries_date', 'duty_entries', ['date'], unique=False)

    op.create_table(
        'salary_payments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('staff_id', sa.Integer(), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column(
            'payment_type',
            sa.Enum('full', 'avans', name='salary_payment_type'),
            nullable=False,
        ),
        sa.Column('amount', sa.Numeric(precision=12, scale=0), nullable=False),
        sa.Column('created_by_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_voided', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('voided_by_id', sa.Uuid(), nullable=True),
        sa.CheckConstraint('amount >= 0', name='ck_salary_payments_amount_non_negative'),
        sa.CheckConstraint('period_start <= period_end', name='ck_salary_payments_period_valid'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['staff_id'], ['staff.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['voided_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_salary_payments_staff_id', 'salary_payments', ['staff_id'], unique=False)
    op.create_index(
        'ix_salary_payments_period',
        'salary_payments',
        ['staff_id', 'period_start', 'period_end'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_salary_payments_period', table_name='salary_payments')
    op.drop_index('ix_salary_payments_staff_id', table_name='salary_payments')
    op.drop_table('salary_payments')

    op.drop_index('ix_duty_entries_date', table_name='duty_entries')
    op.drop_index('ix_duty_entries_staff_id', table_name='duty_entries')
    op.drop_table('duty_entries')

    sa.Enum(name='salary_payment_type').drop(op.get_bind(), checkfirst=True)
