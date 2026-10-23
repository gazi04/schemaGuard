from pathlib import Path

import pytest

from schemaguard.dbt.lineage import downstream, find_source, split
from schemaguard.dbt.manifest import Manifest

FIXTURES = Path(__file__).parent / "fixtures" / "dbt" / "manifest.json"


def load() -> Manifest:
    return Manifest.model_validate_json(FIXTURES.read_text(encoding="utf-8"))


def test_load_counts():
    m = load()

    assert len(m.sources) == 1
    assert len(m.nodes) == 6
    assert len(m.exposures) == 1


def test_missing_compiled_code_is_none():
    m = load()
    node = m.nodes["model.demo.stg_uncompiled"]

    assert node.compiled_code is None


@pytest.mark.parametrize(
    "source_name, table_name, expected",
    [
        ("app", "customers", "source.demo.app.customers"),
        ("app", "app_customers", None),
        ("nope", "customers", None),
    ],
)
def test_find_source(source_name: str, table_name: str, expected: str | None):
    m = load()
    result = find_source(m, source_name, table_name)

    assert result == expected


def test_downstream_order():
    m = load()
    start = find_source(m, "app", "customers")
    assert start is not None

    items = downstream(m, start)
    pairs = [(d.unique_id, d.depth) for d in items]
    assert pairs == [
        ("model.demo.stg_customers", 1),
        ("model.demo.raw_dump", 1),
        ("model.demo.stg_uncompiled", 1),
        ("model.demo.customer_stats", 2),
        ("test.demo.not_null_stg_customers_id", 2),
        ("model.demo.report", 2),
        ("exposure.demo.dashboard", 3),
    ]


def test_split_fixture():
    m = load()
    start = find_source(m, "app", "customers")
    assert start is not None

    items = downstream(m, start)
    lineage = split(m, items)
    models = [d.unique_id for d in lineage.models]
    assert models == [
        "model.demo.stg_customers",
        "model.demo.raw_dump",
        "model.demo.stg_uncompiled",
        "model.demo.customer_stats",
        "model.demo.report",
    ]

    tests = [d.unique_id for d in lineage.tests]
    assert tests == ["test.demo.not_null_stg_customers_id"]

    exposures = [d.unique_id for d in lineage.exposures]
    assert exposures == ["exposure.demo.dashboard"]
