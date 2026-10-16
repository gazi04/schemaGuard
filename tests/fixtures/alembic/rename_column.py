"""rename customers.signup_date to created_at

Revision ID: c3d4e5f6a1b2
Revises:
Create Date: 2026-10-16 10:00:00.000000

"""

from alembic import op

revision = "c3d4e5f6a1b2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("customers", "signup_date", new_column_name="created_at")


def downgrade() -> None:
    op.alter_column("customers", "created_at", new_column_name="signup_date")
