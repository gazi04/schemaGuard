"""create a table and drop an unused column"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.create_table("coupons", sa.Column("id", sa.Integer(), primary_key=True))
    op.drop_column("customers", "notes")
