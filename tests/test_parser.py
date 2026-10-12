from schemaguard.migrations.changes import ChangeKind, ChangeSet
from schemaguard.migrations.sql import parse_sql


def test_rename_query():
    query = "ALTER TABLE customers RENAME COLUMN name TO full_name"

    result = parse_sql(query, "source_file.sql")

    assert isinstance(result, ChangeSet)
    changes = result.changes[0]

    assert changes.kind is ChangeKind.RENAME_COLUMN
    assert changes.table == "customers"
    assert changes.column == "name"
    assert changes.new_name == "full_name"


def test_drop_column():
    query = "ALTER TABLE customers DROP COLUMN email"
    result = parse_sql(query, "source.sql")

    assert isinstance(result, ChangeSet)
    changes = result.changes[0]

    assert changes.kind is ChangeKind.DROP_COLUMN
    assert changes.table == "customers"
