"""make customers.email NOT NULL"""

from alembic import op


def upgrade() -> None:
    op.alter_column("customers", "email", nullable=False)
