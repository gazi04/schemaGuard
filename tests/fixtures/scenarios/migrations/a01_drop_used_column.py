"""drop customers.email (read by stg_customers)"""

from alembic import op


def upgrade() -> None:
    op.drop_column("customers", "email")
