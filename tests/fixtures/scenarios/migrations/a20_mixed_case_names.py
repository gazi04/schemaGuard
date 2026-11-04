"""drop Customers.EMAIL (names compare case-insensitively)"""

from alembic import op


def upgrade() -> None:
    op.drop_column("Customers", "EMAIL")
