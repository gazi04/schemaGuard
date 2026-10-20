from pathlib import Path

from typer.testing import CliRunner

from schemaguard.cli import app, format_change
from schemaguard.migrations import ChangeKind, SchemaChange

FIXTURES = Path(__file__).parent / "fixtures"
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
