"""create pharmacy_entries and expenses

Revision ID: c4d6f8a0b2e4
Revises: 9b3e5d7f1a2c
Create Date: 2026-09-16 10:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d6f8a0b2e4'
down_revision: Union[str, Sequence[str], None] = '9b3e5d7f1a2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pharmacy_entries',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('medicine_cost', sa.Numeric(precision=12, scale=0), nullable=True),
        sa.Column('amount_paid', sa.Numeric(precision=12, scale=0), nullable=True),
        sa.Column('created_by_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_voided', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('voided_by_id', sa.Uuid(), nullable=True),
        sa.CheckConstraint('medicine_cost IS NULL OR medicine_cost >= 0', name='ck_pharmacy_entries_cost_non_negative'),
        sa.CheckConstraint('amount_paid IS NULL OR amount_paid >= 0', name='ck_pharmacy_entries_paid_non_negative'),
        sa.CheckConstraint('medicine_cost IS NOT NULL OR amount_paid IS NOT NULL', name='ck_pharmacy_entries_not_both_null'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['voided_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pharmacy_entries_date', 'pharmacy_entries', ['date'], unique=False)

    op.create_table(
        'expenses',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=0), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_voided', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('voided_by_id', sa.Uuid(), nullable=True),
        sa.CheckConstraint('amount >= 0', name='ck_expenses_amount_non_negative'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['voided_by_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_expenses_date', 'expenses', ['date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_expenses_date', table_name='expenses')
    op.drop_table('expenses')

    op.drop_index('ix_pharmacy_entries_date', table_name='pharmacy_entries')
    op.drop_table('pharmacy_entries')
