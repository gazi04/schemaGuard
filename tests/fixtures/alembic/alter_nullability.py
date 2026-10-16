"""make customers.email nullable

Revision ID: e5f6a1b2c3d4
Revises:
Create Date: 2026-10-16 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e5f6a1b2c3d4"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "customers",
        "email",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "customers",
        "email",
        existing_type=sa.String(length=255),
        nullable=False,
    )
