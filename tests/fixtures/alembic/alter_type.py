"""change orders.amount from Integer to BigInteger

Revision ID: d4e5f6a1b2c3
Revises:
Create Date: 2026-10-16 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a1b2c3"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "orders",
        "amount",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
    )


def downgrade() -> None:
    op.alter_column(
        "orders",
        "amount",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
    )
