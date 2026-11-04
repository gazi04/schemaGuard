"""rename customers.name to full_name"""

from alembic import op


def upgrade() -> None:
    op.alter_column("customers", "name", new_column_name="full_name")
