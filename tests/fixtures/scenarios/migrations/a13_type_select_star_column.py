"""change orders.amount type"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.alter_column("orders", "amount", type_=sa.Numeric(12, 2))
