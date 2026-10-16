"""drop items table

Revision ID: f6a1b2c3d4e5
Revises:
Create Date: 2026-10-16 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "f6a1b2c3d4e5"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("items")


def downgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
    )
