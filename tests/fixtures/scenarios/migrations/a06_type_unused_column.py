"""widen customers.notes"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.alter_column("customers", "notes", type_=sa.Text())
