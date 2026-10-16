"""add signup_date to customers

Revision ID: a1b2c3d4e5f6
Revises:
Create Date: 2026-10-16 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("signup_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "signup_date")
