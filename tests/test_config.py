from pathlib import Path

import pytest

from schemaguard.config import ConfigError, FailOn, SourceRef, load_config

FIXTURES = Path(__file__).parent / "fixtures" / "config"
SOURCES = "sources:\n  customers: ecom.raw_customers\n"


def load(file_name: str) -> str:
    return (FIXTURES / file_name).read_text(encoding="utf-8")


def test_demo_config():
    config = load_config(load("demo.yml"))

    sources = config.sources
    assert len(sources) == 3
    assert sources["orders"] == SourceRef(source_name="ecom", table_name="raw_orders")
    assert config.manifest == "dbt/manifest.json"
    assert config.ignore == ("alembic_version",)
    assert config.fail_on is FailOn.RISKY


def test_minimal_config_defaults():
    config = load_config(load("minimal.yml"))

    assert len(config.sources) == 1
    assert str(config.sources["customers"]) == "ecom.raw_customers"
    assert config.manifest == "target/manifest.json"
    assert config.migrations == "alembic/versions"
    assert config.ignore == ()
    assert config.fail_on is FailOn.BREAKING


@pytest.mark.parametrize("value", ["raw", "ecom.", ".x", ""])
def test_bad_source_value(value: str):
    text = f"sources: \n customers: {value!r}\n"

    with pytest.raises(ConfigError) as exc_info:
        load_config(text)

    assert "sources.customers" in str(exc_info.value)


def test_source_with_two_dots():
    config = load_config("sources: \n customers: a.b.c")
    assert config.sources["customers"].source_name == "a"
    assert config.sources["customers"].table_name == "b.c"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("", "empty"),
        ("# only a comment\n", "empty"),
        ("- a\n- b\n", "mapping"),
        ("hello\n", "mapping"),
        ("a: [1", "Invalid YAML"),
        ("!!python/object/apply:os.system ['echo hi']\n", "Invalid YAML"),
        ("sources: {}\n", "at least 1 item"),
        ("fail_on: never\n", "Field required"),
        (SOURCES + "fail_ob: never\n", "fail_ob"),
        (SOURCES + "fail_on: sometimes\n", "fail_on"),
        (SOURCES + "ignore: customers\n", "ignore"),
    ],
)
def test_load_error(text: str, expected: str):
    with pytest.raises(ConfigError) as exc_info:
        load_config(text)
    assert expected in str(exc_info.value)
