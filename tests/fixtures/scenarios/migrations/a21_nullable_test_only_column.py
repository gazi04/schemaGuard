"""make customers.phone nullable (source test on phone)"""

from alembic import op


def upgrade() -> None:
    op.alter_column("customers", "phone", nullable=True)
