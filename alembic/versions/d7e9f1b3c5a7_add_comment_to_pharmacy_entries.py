"""add comment to pharmacy_entries

Revision ID: d7e9f1b3c5a7
Revises: c4d6f8a0b2e4
Create Date: 2026-09-17 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e9f1b3c5a7'
down_revision: Union[str, Sequence[str], None] = 'c4d6f8a0b2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'pharmacy_entries',
        sa.Column('comment', sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('pharmacy_entries', 'comment')
