"""add customers.loyalty_tier"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column("customers", sa.Column("loyalty_tier", sa.String(20)))
