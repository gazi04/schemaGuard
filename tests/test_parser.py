from schemaguard.migrations.changes import ChangeKind, ChangeSet
from schemaguard.migrations.sql import parse_sql

DUMMY_FILE_NAME = "source.sql"


def test_rename_query():
    query = "ALTER TABLE customers RENAME COLUMN name TO full_name"

    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes

    change = result.changes[0]
    assert change.kind is ChangeKind.RENAME_COLUMN
    assert change.table == "customers"
    assert change.column == "name"
    assert change.new_name == "full_name"
    assert change.source_file == DUMMY_FILE_NAME


def test_drop_column():
    query = "ALTER TABLE customers DROP COLUMN email"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes

    change = result.changes[0]
    assert change.kind is ChangeKind.DROP_COLUMN
    assert change.table == "customers"
    assert change.column == "email"


def test_add_column():
    query = "ALTER TABLE customers ADD COLUMN age INT"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes

    change = result.changes[0]
    assert change.kind is ChangeKind.ADD_COLUMN
    assert change.table == "customers"
    assert change.column == "age"


def test_alter_column_type():
    query = "ALTER TABLE customers ALTER COLUMN year TYPE VARCHAR(4)"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes

    change = result.changes[0]
    assert change.kind is ChangeKind.ALTER_TYPE
    assert change.table == "customers"
    assert change.column == "year"
    assert change.new_type == "VARCHAR(4)"
    assert change.nullable is None


def test_alter_column_nullable():
    query = "ALTER TABLE customers ALTER COLUMN year SET NOT NULL"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes

    change = result.changes[0]
    assert change.kind is ChangeKind.ALTER_NULLABILITY
    assert change.table == "customers"
    assert change.column == "year"
    assert change.new_type is None
    assert change.nullable is False

    query = "ALTER TABLE customers ALTER COLUMN year DROP NOT NULL"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes

    change = result.changes[0]
    assert change.kind is ChangeKind.ALTER_NULLABILITY
    assert change.table == "customers"
    assert change.column == "year"
    assert change.new_type is None
    assert change.nullable is True


def test_rename_table():
    query = "ALTER TABLE customers RENAME TO users"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes

    change = result.changes[0]
    assert change.kind is ChangeKind.RENAME_TABLE
    assert change.table == "customers"
    assert change.new_name == "users"


def test_drop_columns():
    query = "ALTER TABLE customers DROP COLUMN email, DROP COLUMN age"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes

    change = result.changes[0]
    assert change.kind is ChangeKind.DROP_COLUMN
    assert change.table == "customers"
    assert change.column == "email"

    change = result.changes[1]
    assert change.kind is ChangeKind.DROP_COLUMN
    assert change.table == "customers"
    assert change.column == "age"


def test_drop_constraint():
    query = "ALTER TABLE customers DROP CONSTRAINT fk_id"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes == ()


def test_drop_table():
    query = "DROP TABLE orders"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes

    change = result.changes[0]
    assert change.kind is ChangeKind.DROP_TABLE
    assert change.table == "orders"
    assert change.source_file == DUMMY_FILE_NAME

    query = "DROP TABLE orders, customers, items"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert result.changes

    change = result.changes[0]
    assert change.kind is ChangeKind.DROP_TABLE
    assert change.table == "orders"
    assert change.source_file == DUMMY_FILE_NAME

    change = result.changes[1]
    assert change.kind is ChangeKind.DROP_TABLE
    assert change.table == "customers"
    assert change.source_file == DUMMY_FILE_NAME

    change = result.changes[2]
    assert change.kind is ChangeKind.DROP_TABLE
    assert change.table == "items"
    assert change.source_file == DUMMY_FILE_NAME
