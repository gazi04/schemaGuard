"""rename customers.email via raw SQL

Revision ID: b2c3d4e5f6a1
Revises:
Create Date: 2026-10-16 10:00:00.000000

"""

from alembic import op

revision = "b2c3d4e5f6a1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE customers RENAME COLUMN email TO email_address
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE customers RENAME COLUMN email_address TO email
        """
    )
