"""drop audit_log.message (table not in the config)"""

from alembic import op


def upgrade() -> None:
    op.drop_column("audit_log", "message")
