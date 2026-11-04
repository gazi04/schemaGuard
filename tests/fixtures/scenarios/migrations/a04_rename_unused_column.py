"""rename customers.notes to remarks"""

from alembic import op


def upgrade() -> None:
    op.alter_column("customers", "notes", new_column_name="remarks")
