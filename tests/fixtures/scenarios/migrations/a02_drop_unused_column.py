"""drop customers.notes (no model or test reads it)"""

from alembic import op


def upgrade() -> None:
    op.drop_column("customers", "notes")
