"""rename customers to accounts

Revision ID: a6b5c4d3e2f1
Revises:
Create Date: 2026-10-16 10:00:00.000000

"""

from alembic import op

revision = "a6b5c4d3e2f1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("customers", "accounts")


def downgrade() -> None:
    op.rename_table("accounts", "customers")
