"""touch alembic_version (ignored in the config)"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.alter_column("alembic_version", "version_num", type_=sa.String(64))
