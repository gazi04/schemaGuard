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
    assert changes.column == "email"


def test_add_column():
    query = "ALTER TABLE customers ADD COLUMN age INT"
    result = parse_sql(query, "source.sql")

    assert isinstance(result, ChangeSet)
    changes = result.changes[0]

    assert changes.kind is ChangeKind.ADD_COLUMN
    assert changes.table == "customers"
    assert changes.column == "age"


def test_alter_column_type():
    query = "ALTER TABLE customers ALTER COLUMN year TYPE VARCHAR(4)"
    result = parse_sql(query, "source.sql")

    assert isinstance(result, ChangeSet)
    changes = result.changes[0]

    assert changes.kind is ChangeKind.ALTER_TYPE
    assert changes.table == "customers"
    assert changes.column == "year"
    assert changes.new_type == "VARCHAR(4)"
    assert changes.nullable is None


def test_alter_column_nullable():
    query = "ALTER TABLE customers ALTER COLUMN year SET NOT NULL"
    result = parse_sql(query, "source.sql")

    assert isinstance(result, ChangeSet)
    changes = result.changes[0]

    assert changes.kind is ChangeKind.ALTER_NULLABILITY
    assert changes.table == "customers"
    assert changes.column == "year"
    assert changes.new_type is None
    assert changes.nullable is False

    query = "ALTER TABLE customers ALTER COLUMN year DROP NOT NULL"
    result = parse_sql(query, "source.sql")

    assert isinstance(result, ChangeSet)
    changes = result.changes[0]

    assert changes.kind is ChangeKind.ALTER_NULLABILITY
    assert changes.table == "customers"
    assert changes.column == "year"
    assert changes.new_type is None
    assert changes.nullable is True


def test_rename_table():
    query = "ALTER TABLE customers RENAME TO users"
    result = parse_sql(query, "source.sql")

    assert isinstance(result, ChangeSet)
    changes = result.changes[0]

    assert changes.kind is ChangeKind.RENAME_TABLE
    assert changes.table == "customers"
    assert changes.new_name == "users"


