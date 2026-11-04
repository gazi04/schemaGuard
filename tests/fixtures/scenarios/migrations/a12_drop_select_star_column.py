"""drop orders.status (stg_orders uses select *)"""

from alembic import op


def upgrade() -> None:
    op.drop_column("orders", "status")
