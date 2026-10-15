import pytest

from schemaguard.migrations.changes import ChangeKind, ChangeSet
from schemaguard.migrations.sql import parse_sql

DUMMY_FILE_NAME = "source.sql"


def test_rename_query():
    query = "ALTER TABLE customers RENAME COLUMN name TO full_name"

    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

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
    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.DROP_COLUMN
    assert change.table == "customers"
    assert change.column == "email"


def test_add_column():
    query = "ALTER TABLE customers ADD COLUMN age INT"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.ADD_COLUMN
    assert change.table == "customers"
    assert change.column == "age"


def test_alter_column_type():
    query = "ALTER TABLE customers ALTER COLUMN year TYPE VARCHAR(4)"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

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
    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.ALTER_NULLABILITY
    assert change.table == "customers"
    assert change.column == "year"
    assert change.new_type is None
    assert change.nullable is False

    query = "ALTER TABLE customers ALTER COLUMN year DROP NOT NULL"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

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
    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.RENAME_TABLE
    assert change.table == "customers"
    assert change.new_name == "users"


def test_drop_columns():
    query = "ALTER TABLE customers DROP COLUMN email, DROP COLUMN age"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 2
    assert len(result.not_analyzed) == 0

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
    assert len(result.changes) == 0
    assert len(result.not_analyzed) == 1

    entry = result.not_analyzed[0]
    assert "DROP CONSTRAINT" in entry.reason
    assert entry.source_file == DUMMY_FILE_NAME


def test_drop_table():
    query = "DROP TABLE orders"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 0

    change = result.changes[0]
    assert change.kind is ChangeKind.DROP_TABLE
    assert change.table == "orders"
    assert change.source_file == DUMMY_FILE_NAME

    query = "DROP TABLE orders, customers, items"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 3
    assert len(result.not_analyzed) == 0

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


@pytest.mark.parametrize("query", ["", "-- only a comment", "       "])
def test_empty_input(query: str):
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 0
    assert len(result.not_analyzed) == 0


def test_long_sql_is_shortened():
    query = """
    CREATE TABLE audit_log (
            id INT,
            user_id INT,
            age INT,
            name VARCHAR(255),
            surname VARCHAR(255),
            married BOOLEAN,
            birth_yeat INT,
            birth_month INT,
            birth_day INT,
            address VARCHAR(255),
            nationality VARCHAR(255)
    """
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 0
    assert len(result.not_analyzed) == 1

    entry = result.not_analyzed[0]
    assert "\n" not in entry.reason
    assert "Could not parse SQL:" in entry.reason
    assert "..." in entry.reason


def test_mixed_script():
    query = "ALTER TABLE t DROP COLUMN a; DROP VIEW v"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 1

    change = result.changes[0]
    assert change.kind == ChangeKind.DROP_COLUMN
    assert change.table == "t"
    assert change.column == "a"
    assert change.source_file == DUMMY_FILE_NAME

    entry = result.not_analyzed[0]
    assert entry.source_file == DUMMY_FILE_NAME
    assert "DROP VIEW" in entry.reason


def test_mixed_actions():
    query = "ALTER TABLE t DROP COLUMN a, DROP CONSTRAINT fk"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 1
    assert len(result.not_analyzed) == 1

    change = result.changes[0]
    assert change.kind == ChangeKind.DROP_COLUMN
    assert change.table == "t"
    assert change.column == "a"
    assert change.source_file == DUMMY_FILE_NAME

    entry = result.not_analyzed[0]
    assert entry.source_file == DUMMY_FILE_NAME
    assert "DROP CONSTRAINT" in entry.reason


def test_parse_error_loses_valid_sql():
    query = "ALTER TABLE a DROP COLUMN x; ALTER TABLE"
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 0
    assert len(result.not_analyzed) == 1

    entry = result.not_analyzed[0]
    assert "Could not parse" in entry.reason
    assert entry.source_file == DUMMY_FILE_NAME


@pytest.mark.parametrize(
    "query, keyword",
    [
        (
            "ALTER TABLE t RENAME COLUMN a TO b, RENAME COLUMN c TO d",
            "Could not break down",
        ),
        ("CREATE INDEX ix ON t (a)", "CREATE INDEX"),
        ("UPDATE t SET a = 1", "UPDATE"),
        ("ALTER TABLE t ALTER COLUMN a SET DEFAULT 0", "SET DEFAULT"),
        ("ALTER TABLE t ADD CONSTRAINT pk PRIMARY KEY (id)", "ADD CONSTRAINT"),
        ("ALTER TABLE", "Could not parse"),
    ],
)
def test_unsupported_sql_is_reported(query: str, keyword: str):
    result = parse_sql(query, DUMMY_FILE_NAME)

    assert isinstance(result, ChangeSet)
    assert len(result.changes) == 0
    assert len(result.not_analyzed) == 1

    entry = result.not_analyzed[0]
    assert keyword in entry.reason
    assert entry.source_file == DUMMY_FILE_NAME
