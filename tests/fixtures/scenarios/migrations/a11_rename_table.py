"""rename orders to purchases"""

from alembic import op


def upgrade() -> None:
    op.rename_table("orders", "purchases")
