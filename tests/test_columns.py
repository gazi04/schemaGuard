from schemaguard.dbt.columns import column_usage


def test_column_usage():
    sql = "select id, name from raw_customers"
    result = column_usage(sql, "table")

    assert result.columns == {"id", "name"}
    assert result.uncertain is False


def test_column_usage_with_aliases():
    sql = "select id as customer_id from raw_customers"
    result = column_usage(sql, "table")

    assert result.columns == {"id"}
    assert result.uncertain is False


def test_column_usage_with_star():
    sql = "select count(*) from raw_customers"
    result = column_usage(sql, "table")

    assert result.columns == frozenset()
    assert result.uncertain is False
