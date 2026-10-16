"""drop signup_date from customers

Revision ID: b2c3d4e5f6a1
Revises:
Create Date: 2026-10-16 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("customers", "signup_date")


def downgrade() -> None:
    op.add_column("customers", sa.Column("signup_date", sa.Date(), nullable=True))
