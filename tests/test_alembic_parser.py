from pathlib import Path

from schemaguard.migrations.alembic import parse_alembic
from schemaguard.migrations.changes import ChangeKind

FIXTURES = Path(__file__).parent / "fixtures" / "alembic"
SOURCE_FILE = "migration.py"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_rename_column():
    result = parse_alembic(load("rename_column.py"), SOURCE_FILE)

    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.RENAME_COLUMN
    assert change.table == "customers"
    assert change.column == "signup_date"
    assert change.new_name == "created_at"
    assert change.line == 18


def test_drop_column():
    result = parse_alembic(load("drop_column.py"), SOURCE_FILE)

    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.DROP_COLUMN
    assert change.table == "customers"
    assert change.column == "signup_date"
    assert change.line == 19


def test_drop_table():
    result = parse_alembic(load("drop_table.py"), SOURCE_FILE)

    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.DROP_TABLE
    assert change.table == "items"
    assert change.line == 19


def test_rename_table():
    result = parse_alembic(load("rename_table.py"), SOURCE_FILE)

    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.RENAME_TABLE
    assert change.table == "customers"
    assert change.new_name == "accounts"
    assert change.line == 18
