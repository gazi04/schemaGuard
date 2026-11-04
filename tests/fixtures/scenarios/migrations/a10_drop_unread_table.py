"""drop payments (a dbt source no model reads)"""

from alembic import op


def upgrade() -> None:
    op.drop_table("payments")
