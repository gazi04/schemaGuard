"""autogenerate-style rename: drop name, add full_name"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.drop_column("customers", "name")
    op.add_column("customers", sa.Column("full_name", sa.String()))
