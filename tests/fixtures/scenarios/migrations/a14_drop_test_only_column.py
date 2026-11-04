"""drop customers.phone (only a source test reads it)"""

from alembic import op


def upgrade() -> None:
    op.drop_column("customers", "phone")
