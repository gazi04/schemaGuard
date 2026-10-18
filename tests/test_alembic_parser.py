from pathlib import Path

import pytest

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


@pytest.mark.parametrize(
    "call, keyword",
    [
        (
            'op.alter_column("customers", "a")',
            "op.alter_column has no supported keyword:",
        ),
        (
            'op.alter_column("customers", "a", new_column_name=x)',
            "op.alter_column new_column_name isn't a string literal:",
        ),
        (
            'op.alter_column("customers", column_name="a", new_column_name="b")',
            "op.alter_column not checked:",
        ),
        (
            'op.alter_column("customers", "a", **opts)',
            "op.alter_column **kwargs not checked:",
        ),
        ("op.drop_table(name)", "op.drop_table not checked:"),
        ('op.rename_table("customers")', "op.rename_table not checked:"),
        (
            'op.create_index("ix_email", "customers", ["email"])',
            "op.create_index not checked",
        ),
        ('print("hi")', "Non-op call not checked:"),
        ("x = 1", "Statement not checked:"),
    ],
)
def test_not_analyzed(call: str, keyword: str):
    source = f"def upgrade(): \n    {call}\n"
    result = parse_alembic(source, SOURCE_FILE)

    assert len(result.changes) == 0
    assert len(result.not_analyzed) == 1

    entry = result.not_analyzed[0]
    assert keyword in entry.reason
    assert entry.source_file == SOURCE_FILE
