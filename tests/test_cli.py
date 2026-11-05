import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from schemaguard.cli import (
    app,
    format_columns,
    format_model,
    merge_change_sets,
    migration_files,
)
from schemaguard.dbt.columns import ColumnUsage
from schemaguard.dbt.lineage import Downstream
from schemaguard.migrations import ChangeKind, ChangeSet, NotAnalyzed, SchemaChange

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


def make_project(
    tmp_path: Path,
    migrations: dict[str, str],
    sources: str = "customers: app.customers",
) -> Path:
    config = tmp_path / "schemaguard.yml"
    config.write_text(
        f"manifest: dbt/manifest.json\nmigrations: versions\nsources:\n  {sources}\n",
        encoding="utf-8",
    )
    (tmp_path / "dbt").mkdir()
    (tmp_path / "dbt" / "manifest.json").write_text(
        MANIFEST.read_text(encoding="utf-8"), encoding="utf-8"
    )
    versions = tmp_path / "versions"
    versions.mkdir()
    for name, text in migrations.items():
        (versions / name).write_text(text, encoding="utf-8")

    return config


def alembic_fixture(name: str) -> str:
    return (FIXTURES / "alembic" / name).read_text(encoding="utf-8")


def test_check_reports_impact(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert result.exit_code == 0
    assert "customers.signup_date" in result.stdout
    assert "source app.customers" in result.stdout
    assert "raw_dump" in result.stdout
    assert "(uncertain)" in result.stdout
    assert "exposures: dashboard" in result.stdout


def test_check_explicit_files(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_table.py")})
    mixed = str(FIXTURES / "sql" / "mixed.sql")

    result = runner.invoke(app, ["check", mixed, "--config", str(config)])

    assert result.exit_code == 0
    assert "orders.amount -> total  (unmapped)" in result.stdout
    assert result.stdout.count("not_analyzed") == 2
    assert "drop_table" not in result.stdout


def test_check_no_changes(tmp_path: Path):
    config = make_project(tmp_path, {})

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[0].startswith("worst: safe")
    assert lines[-1] == "No changes found."


def test_check_missing_config(tmp_path: Path):
    result = runner.invoke(app, ["check", "--config", str(tmp_path / "nope.yml")])

    assert result.exit_code == 2


def test_check_invalid_config(tmp_path: Path):
    config = make_project(tmp_path, {})
    config.write_text("sources: {}\n", encoding="utf-8")

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert result.exit_code == 2
    assert f"Error: {config}" in result.stderr


def test_check_missing_manifest(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})
    (tmp_path / "dbt" / "manifest.json").unlink()

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert result.exit_code == 2
    assert "manifest" in result.stderr
    assert "not found" in result.stderr


def test_check_missing_migrations_folder(tmp_path: Path):
    config = make_project(tmp_path, {})
    (tmp_path / "versions").rmdir()

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert result.exit_code == 2
    assert "migrations folder" in result.stderr


def test_check_source_not_in_manifest(tmp_path: Path):
    config = make_project(
        tmp_path,
        {"0001.py": alembic_fixture("drop_column.py")},
        sources="customers: ecom.nope",
    )

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert result.exit_code == 2
    assert "ecom.nope" in result.stderr


def test_check_wrong_file_type(tmp_path: Path):
    config = make_project(tmp_path, {})
    notes = tmp_path / "notes.txt"
    notes.write_text("hello", encoding="utf-8")

    result = runner.invoke(app, ["check", str(notes), "--config", str(config)])

    assert result.exit_code == 2
    assert "is not a .py or .sql migration" in result.stderr


def test_merge_change_sets_keeps_order():
    first = SchemaChange(
        kind=ChangeKind.DROP_TABLE, table="a", source_file="1.sql", line=1
    )
    second = SchemaChange(
        kind=ChangeKind.DROP_TABLE, table="b", source_file="2.sql", line=1
    )
    skipped = NotAnalyzed(reason="BEGIN not checked", source_file="2.sql", line=1)

    result = merge_change_sets(
        [
            ChangeSet(changes=(first,), not_analyzed=()),
            ChangeSet(changes=(second,), not_analyzed=(skipped,)),
        ]
    )

    assert result == ChangeSet(changes=(first, second), not_analyzed=(skipped,))


def test_migration_files(tmp_path: Path):
    for name in ("b.sql", "a.py", "__init__.py", "x.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")
    (tmp_path / "sub.py").mkdir()

    assert migration_files(tmp_path) == [tmp_path / "a.py", tmp_path / "b.sql"]


def test_check_shows_severity(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert result.exit_code == 0
    assert "severity: breaking (uncertain)" in result.stdout


def test_check_json_output(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    result = runner.invoke(app, ["check", "--config", str(config), "--format", "json"])

    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["version"] == 1
    assert doc["worst"] == "breaking"
    [impact] = doc["impacts"]
    assert impact["change"]["column"] == "signup_date"
    assert impact["source"] == {"source_name": "app", "table_name": "customers"}


def test_check_json_short_flag(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    result = runner.invoke(app, ["check", "--config", str(config), "-f", "json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["version"] == 1


def test_check_json_no_changes(tmp_path: Path):
    config = make_project(tmp_path, {})

    result = runner.invoke(app, ["check", "--config", str(config), "--format", "json"])

    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["impacts"] == []
    assert doc["worst"] == "safe"


def test_check_format_text_is_default(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    default = runner.invoke(app, ["check", "--config", str(config)])
    text = runner.invoke(app, ["check", "--config", str(config), "--format", "text"])

    assert text.exit_code == 0
    assert text.stdout == default.stdout


def test_check_unknown_format(tmp_path: Path):
    config = make_project(tmp_path, {})

    result = runner.invoke(app, ["check", "--config", str(config), "--format", "xml"])

    assert result.exit_code == 2
    assert "xml" in result.stderr


def test_check_json_errors_go_to_stderr(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})
    (tmp_path / "dbt" / "manifest.json").unlink()

    result = runner.invoke(app, ["check", "--config", str(config), "--format", "json"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "not found" in result.stderr
