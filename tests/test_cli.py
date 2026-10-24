import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from schemaguard.cli import app, format_change, format_columns, format_model
from schemaguard.dbt.columns import ColumnUsage
from schemaguard.dbt.lineage import Downstream
from schemaguard.migrations import ChangeKind, SchemaChange

FIXTURES = Path(__file__).parent / "fixtures"
MANIFEST = FIXTURES / "dbt" / "manifest.json"
runner = CliRunner()


def test_parse_sql_fixture():
    result = runner.invoke(app, ["parse", str(FIXTURES / "sql" / "drop_column.sql")])

    assert result.exit_code == 0
    assert "drop_column" in result.stdout
    assert "customers.signup_date" in result.stdout


def test_parse_alembic_fixture():
    result = runner.invoke(
        app, ["parse", str(FIXTURES / "alembic" / "rename_table.py")]
    )

    assert result.exit_code == 0
    assert "rename_table" in result.stdout
    assert "customers -> accounts" in result.stdout


def test_parse_mixed_shows_not_analyzed():
    result = runner.invoke(app, ["parse", str(FIXTURES / "sql" / "mixed.sql")])

    assert result.exit_code == 0
    assert result.stdout.count("not_analyzed") == 2
    assert "orders.amount -> total" in result.stdout


def test_parse_empty_file(tmp_path: Path):
    empty = tmp_path / "empty.sql"
    empty.write_text("")
    result = runner.invoke(app, ["parse", str(empty)])

    assert result.exit_code == 0
    assert "No changes found." in result.stdout


def test_parse_unknown_extension(tmp_path: Path):
    notes = tmp_path / "notes.txt"
    notes.write_text("hello")
    result = runner.invoke(app, ["parse", str(notes)])

    assert result.exit_code == 2
    assert "not a .py or .sql migration" in result.stderr


def test_parse_missing_file():
    result = runner.invoke(app, ["parse", "doesnt_exist.sql"])

    assert result.exit_code == 2


def test_format_alter_type_without_old_type():
    change = SchemaChange(
        kind=ChangeKind.ALTER_TYPE,
        table="orders",
        column="amount",
        new_type="BIGINT",
        source_file="m.sql",
        line=3,
    )

    assert format_change(change).endswith("orders.amount ? -> BIGINT")


def test_parse_directory():
    result = runner.invoke(app, ["parse", str(FIXTURES)])
    assert result.exit_code == 2


@pytest.mark.parametrize(
    ("columns", "uncertain", "expected"),
    [
        ({"name", "id"}, False, "columns: id, name"),
        (set[str](), True, "columns: uncertain"),
        ({"id"}, True, "columns: id (uncertain)"),
        (set[str](), False, "columns: none"),
    ],
)
def test_format_columns(columns: set[str], uncertain: bool, expected: str):
    usage = ColumnUsage(columns=frozenset(columns), uncertain=uncertain)

    assert format_columns(usage) == expected


def test_format_model_without_usage():
    line = format_model(
        Downstream(unique_id="model.demo.report", depth=2), "report", None
    )

    assert line == "  hop 2  report"


def lineage(*args: str):
    return runner.invoke(app, ["lineage", *args])


def test_lineage_fixture():
    result = lineage("app.customers", "--manifest", str(MANIFEST))

    assert result.exit_code == 0
    assert "source app.customers" in result.stdout
    assert "stg_customers" in result.stdout
    assert "columns: id, name" in result.stdout
    assert "tests: 1" in result.stdout
    assert "exposures: dashboard" in result.stdout


def test_lineage_bfs_order_and_depth():
    lines = lineage("app.customers", "--manifest", str(MANIFEST)).stdout.splitlines()
    models = [line.split()[2] for line in lines if line.startswith("  hop")]
    depths = [line.split()[1] for line in lines if line.startswith("  hop")]

    assert models == [
        "stg_customers",
        "raw_dump",
        "stg_uncompiled",
        "customer_stats",
        "report",
    ]
    assert depths == ["1", "1", "1", "2", "2"]


def test_lineage_only_first_hop_has_columns():
    lines = lineage("app.customers", "--manifest", str(MANIFEST)).stdout.splitlines()
    report = next(line for line in lines if "report" in line)

    assert "columns" not in report


def test_lineage_hint_for_uncompiled():
    result = lineage("app.customers", "--manifest", str(MANIFEST))

    assert result.exit_code == 0
    assert "dbt compile" in result.stderr
    assert "dbt compile" not in result.stdout


def test_lineage_no_hint_when_compiled(tmp_path: Path):
    data = json.loads(MANIFEST.read_text())
    uncompiled = "model.demo.stg_uncompiled"
    del data["nodes"][uncompiled]
    del data["child_map"][uncompiled]
    for children in data["child_map"].values():
        if uncompiled in children:
            children.remove(uncompiled)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(data))

    result = lineage("app.customers", "--manifest", str(path))

    assert result.exit_code == 0
    assert "stg_uncompiled" not in result.stdout
    assert "dbt compile" not in result.stderr


def test_lineage_unknown_source():
    result = lineage("app.nope", "--manifest", str(MANIFEST))

    assert result.exit_code == 2
    assert "unknown source app.nope" in result.stderr


@pytest.mark.parametrize("source", ["app", "app.", ".customers"])
def test_lineage_bad_source_format(source: str):
    result = lineage(source, "--manifest", str(MANIFEST))

    assert result.exit_code == 2
    assert "expected <source>.<table>" in result.stderr


@pytest.mark.parametrize("text", ["{not json", "{}", "[]"])
def test_lineage_invalid_manifest(tmp_path: Path, text: str):
    path = tmp_path / "manifest.json"
    path.write_text(text)

    result = lineage("app.customers", "--manifest", str(path))

    assert result.exit_code == 2
    assert "not a valid dbt manifest" in result.stderr


def test_lineage_missing_manifest(tmp_path: Path):
    result = lineage("app.customers", "--manifest", str(tmp_path / "nope.json"))

    assert result.exit_code == 2
