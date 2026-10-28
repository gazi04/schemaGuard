import pytest

from schemaguard.config import SourceRef, load_config
from schemaguard.impact.analyzer import find_ref, is_ignored

CONFIG = load_config(
    "sources:\n  customers: ecom.raw_customers\nignore: [alembic_version]\n"
)


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
    config = load_config("sources:\n Customers: ecom.raw_customers\n")

    assert find_ref(config, "customers") == SourceRef(
        source_name="ecom", table_name="raw_customers"
    )
