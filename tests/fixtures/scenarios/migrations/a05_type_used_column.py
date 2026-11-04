"""widen customers.id"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.alter_column(
        "customers", "id", existing_type=sa.Integer(), type_=sa.BigInteger()
    )
