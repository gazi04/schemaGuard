from pathlib import Path

import pytest

from schemaguard.dbt.lineage import find_source
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
