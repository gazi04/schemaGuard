import pytest

from schemaguard.dbt.columns import column_usage


def test_column_usage():
    sql = "select id, name from raw_customers"
    result = column_usage(sql, "raw_customers")

    assert result.columns == {"id", "name"}
    assert result.uncertain is False


def test_column_usage_with_aliases():
    sql = "select id as customer_id from raw_customers"
    result = column_usage(sql, "raw_customers")

    assert result.columns == {"id"}
    assert result.uncertain is False


def test_column_usage_count():
    sql = "select count(*) from raw_customers"
    result = column_usage(sql, "raw_customers")

    assert result.columns == frozenset()
    assert result.uncertain is False


@pytest.mark.parametrize(
    "sql, columns, uncertain",
    [
        ("select * from raw_customers", set[str](), True),
        ("select id, * from raw_customers", {"id"}, True),
        ("select * from other_table", set[str](), False),
        ("select c.* from raw_customers c", set[str](), True),
        ('select * from "dbt"."analytics_raw"."raw_customers"', set[str](), True),
        (
            "with s as (select * from raw_customers) select id, name from s",
            {"id", "name"},
            False,
        ),
        ("with s as (select * from raw_customers) select * from s", set[str](), True),
        ("select * from (select * from raw_customers) x", set[str](), True),
        (None, set[str](), True),
        ("", set[str](), True),
        ("select from where", set[str](), True),
    ],
)
def test_column_usage_star(sql: str | None, columns: set[str], uncertain: bool):
    result = column_usage(sql, "raw_customers")

    assert result.columns == columns
    assert result.uncertain is uncertain
