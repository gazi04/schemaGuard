"""drop customers.email through raw SQL"""

from alembic import op


def upgrade() -> None:
    op.execute("ALTER TABLE customers DROP COLUMN email")
