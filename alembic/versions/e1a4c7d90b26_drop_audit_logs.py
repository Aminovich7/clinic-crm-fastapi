"""drop audit_logs

The audit trail was removed at the owner's request: recording stopped and the
existing history destroyed. "Who voided this and when" does not depend on it —
that lives on the records themselves via VoidableMixin (`voided_at`,
`voided_by_id`), which is what the "Bekor qilingan yozuvlar" page reads.

The downgrade recreates the table's structure but cannot bring back the rows;
they are gone deliberately.

Revision ID: e1a4c7d90b26
Revises: d7e9f1b3c5a7
Create Date: 2026-09-18

"""
import sqlalchemy as sa
from alembic import op

revision = "e1a4c7d90b26"
down_revision = "d7e9f1b3c5a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_audit_logs_actor_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_resource_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")


def downgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource_type", sa.String(length=50), nullable=False),
        sa.Column("resource_id", sa.String(length=64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_audit_logs_resource_type", "audit_logs", ["resource_type"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
