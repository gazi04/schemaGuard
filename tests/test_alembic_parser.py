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


def test_add_column():
    result = parse_alembic(load("add_column.py"), SOURCE_FILE)

    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.ADD_COLUMN
    assert change.table == "customers"
    assert change.column == "signup_date"
    assert change.new_type == "sa.Date()"
    assert change.line == 19


@pytest.mark.parametrize(
    "call, new_type",
    [
        ('op.add_column("customers", sa.Column("x"))', None),
        ('op.add_column("customers", Column("x", Integer()))', "Integer()"),
    ],
)
def test_add_column_inline(call: str, new_type: str | None):
    source = f"def upgrade(): \n    {call}\n"
    result = parse_alembic(source, SOURCE_FILE)

    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.ADD_COLUMN
    assert change.table == "customers"
    assert change.column == "x"
    assert change.new_type == new_type
    assert change.source_file == SOURCE_FILE


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
        ('op.add_column("customers")', "op.add_column not checked:"),
        ('op.add_column(t, sa.Column("x"))', "op.add_column not checked:"),
        (
            'op.add_column("customers", col)',
            "op.add_column column isn't a Column() call:",
        ),
        (
            'op.add_column("customers", sa.Index("x"))',
            "op.add_column column isn't a Column() call:",
        ),
        (
            'op.add_column("customers", sa.Column())',
            "op.add_column Column(...) has no name:",
        ),
        (
            'op.add_column("customers", sa.Column(name))',
            "op.add_column column name isn't a string literal:",
        ),
        ("op.execute()", "op.execute not checked:"),
        (
            'op.execute(f"DROP TABLE {t}")',
            "op.execute argument isn't a string literal:",
        ),
        (
            'op.execute(sa.text("DROP TABLE x"))',
            "op.execute argument isn't a string literal:",
        ),
        ('op.execute("SELECT 1")', "Statement not checked: SELECT 1"),
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


def test_execute():
    result = parse_alembic(load("execute.py"), SOURCE_FILE)

    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.RENAME_COLUMN
    assert change.table == "customers"
    assert change.column == "email"
    assert change.new_name == "email_address"
    assert change.source_file == SOURCE_FILE
    assert change.line == 18


def test_execute_multiple_statements():
    call = 'op.execute("ALTER TABLE customers DROP COLUMN email; DROP TABLE orders")'
    source = f"def upgrade(): \n    {call}\n"
    result = parse_alembic(source, SOURCE_FILE)

    assert len(result.changes) == 2
    assert len(result.not_analyzed) == 0

    assert [c.kind for c in result.changes] == [
        ChangeKind.DROP_COLUMN,
        ChangeKind.DROP_TABLE,
    ]
    assert result.changes[0].table == "customers"
    assert result.changes[0].column == "email"
    assert result.changes[1].table == "orders"
    assert [c.line for c in result.changes] == [2, 2]
