import pytest

from schemaguard.config import SourceRef, load_config
from schemaguard.dbt.columns import ColumnUsage
from schemaguard.impact.analyzer import (
    AnalyzerError,
    Match,
    find_ref,
    is_ignored,
    match_first_hop,
)
from schemaguard.migrations import ChangeKind, SchemaChange

CONFIG = load_config(
    "sources:\n  customers: ecom.raw_customers\nignore: [alembic_version]\n"
)


def change(kind: ChangeKind, column: str | None = "email") -> SchemaChange:
    return SchemaChange(
        kind=kind, table="customers", source_file="m.py", line=1, column=column
    )


def usage(*columns: str, uncertain: bool = False) -> ColumnUsage:
    return ColumnUsage(columns=frozenset(columns), uncertain=uncertain)


@pytest.mark.parametrize(
    "table, expected",
    [
        ("customers", SourceRef(source_name="ecom", table_name="raw_customers")),
        ("Customers", SourceRef(source_name="ecom", table_name="raw_customers")),
        ("orders", None),
    ],
)
def test_find_ref(table: str, expected: SourceRef | None):
    assert find_ref(CONFIG, table) == expected


@pytest.mark.parametrize(
    "table, expected",
    [
        ("alembic_version", True),
        ("Alembic_Version", True),
        ("customers", False),
    ],
)
def test_is_ignored(table: str, expected: bool):
    assert is_ignored(CONFIG, table) is expected


def test_find_ref_mixed_case_key():
    config = load_config("sources:\n  Customers: ecom.raw_customers\n")

    assert find_ref(config, "customers") == SourceRef(
        source_name="ecom", table_name="raw_customers"
    )


@pytest.mark.parametrize(
    "schema_change, column_usage, expected",
    [
        (change(ChangeKind.DROP_COLUMN), usage("email", "id"), Match.CERTAIN),
        (change(ChangeKind.DROP_COLUMN), usage("id"), Match.NONE),
        (change(ChangeKind.DROP_COLUMN), usage(uncertain=True), Match.UNCERTAIN),
        (change(ChangeKind.DROP_COLUMN), usage("email", uncertain=True), Match.CERTAIN),
        (
            change(ChangeKind.DROP_COLUMN, "Email"),
            usage("email", uncertain=True),
            Match.CERTAIN,
        ),
        (change(ChangeKind.DROP_TABLE, None), usage(), Match.CERTAIN),
        (change(ChangeKind.RENAME_TABLE, None), usage(), Match.CERTAIN),
        (change(ChangeKind.ADD_COLUMN), usage("email"), Match.NONE),
        (change(ChangeKind.RENAME_COLUMN), usage("email"), Match.CERTAIN),
        (change(ChangeKind.ALTER_TYPE), usage("email"), Match.CERTAIN),
        (change(ChangeKind.ALTER_NULLABILITY), usage("email"), Match.CERTAIN),
    ],
)
def test_match_first_hop(
    schema_change: SchemaChange, column_usage: ColumnUsage, expected: Match
):
    assert match_first_hop(schema_change, column_usage) is expected


def test_match_first_hop_without_column():
    with pytest.raises(
        AnalyzerError, match=r"drop_column on customers has no column \(m.py:1\)"
    ):
        match_first_hop(change(ChangeKind.DROP_COLUMN, None), usage())
