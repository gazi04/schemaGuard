"""make customers.email nullable"""

from alembic import op


def upgrade() -> None:
    op.alter_column("customers", "email", nullable=True)
