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
from schemaguard.github import GitHubError
from schemaguard.migrations import ChangeKind, ChangeSet, NotAnalyzed, SchemaChange
from schemaguard.report import MARKER

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
    extra: str = "",
) -> Path:
    config = tmp_path / "schemaguard.yml"
    config.write_text(
        f"manifest: dbt/manifest.json\nmigrations: versions\nsources:\n  {sources}\n"
        + extra,
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

    assert result.exit_code == 1
    assert "customers.signup_date" in result.stdout
    assert "source app.customers" in result.stdout
    assert "raw_dump" in result.stdout
    assert "(uncertain)" in result.stdout
    assert "exposures: dashboard" in result.stdout


def test_check_explicit_files(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_table.py")})
    mixed = str(FIXTURES / "sql" / "mixed.sql")

    result = runner.invoke(app, ["check", mixed, "--config", str(config)])

    assert result.exit_code == 1
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

    assert result.exit_code == 1
    assert "severity: breaking (uncertain)" in result.stdout


def test_check_json_output(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    result = runner.invoke(app, ["check", "--config", str(config), "--format", "json"])

    assert result.exit_code == 1
    doc = json.loads(result.stdout)
    assert doc["version"] == 1
    assert doc["worst"] == "breaking"
    [impact] = doc["impacts"]
    assert impact["change"]["column"] == "signup_date"
    assert impact["source"] == {"source_name": "app", "table_name": "customers"}


def test_check_json_short_flag(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    result = runner.invoke(app, ["check", "--config", str(config), "-f", "json"])

    assert result.exit_code == 1
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

    assert text.exit_code == 1
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


def test_check_markdown_output(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    result = runner.invoke(
        app, ["check", "--config", str(config), "--format", "markdown"]
    )

    assert result.exit_code == 1
    assert result.stdout.splitlines()[0] == MARKER
    assert "drop_column customers.signup_date" in result.stdout
    assert "raw_dump (hop 1)?" in result.stdout


def test_check_markdown_no_changes(tmp_path: Path):
    config = make_project(tmp_path, {})

    result = runner.invoke(app, ["check", "--config", str(config), "-f", "markdown"])

    assert result.exit_code == 0
    assert "No changes found." in result.stdout


def test_check_markdown_errors_go_to_stderr(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})
    (tmp_path / "dbt" / "manifest.json").unlink()

    result = runner.invoke(
        app, ["check", "--config", str(config), "--format", "markdown"]
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "not found" in result.stderr


NULLABLE = """
def upgrade():
    op.alter_column("customers", "signup_date", nullable=True)
"""


@pytest.mark.parametrize(
    ("fail_on", "code"), [("breaking", 0), ("risky", 1), ("never", 0)]
)
def test_check_fail_on_from_config(tmp_path: Path, fail_on: str, code: int):
    config = make_project(
        tmp_path, {"0001.py": NULLABLE}, extra=f"fail_on: {fail_on}\n"
    )

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert "severity: risky" in result.stdout
    assert result.exit_code == code, result.output


@pytest.mark.parametrize(
    ("fail_on", "code"), [("breaking", 1), ("risky", 1), ("never", 0)]
)
def test_check_fail_on_flag_overrides_config(tmp_path: Path, fail_on: str, code: int):
    config = make_project(
        tmp_path,
        {"0001.py": alembic_fixture("drop_column.py")},
        extra="fail_on: never\n",
    )

    result = runner.invoke(
        app, ["check", "--config", str(config), "--fail-on", fail_on]
    )

    assert result.exit_code == code, result.output


def test_check_no_changes_never_fails(tmp_path: Path):
    config = make_project(tmp_path, {}, extra="fail_on: risky\n")

    result = runner.invoke(app, ["check", "--config", str(config)])

    assert result.exit_code == 0


def test_check_unknown_fail_on(tmp_path: Path):
    config = make_project(tmp_path, {})

    result = runner.invoke(app, ["check", "--config", str(config), "--fail-on", "x"])

    assert result.exit_code == 2


def test_check_failing_json_keeps_stdout_clean(tmp_path: Path):
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    result = runner.invoke(app, ["check", "--config", str(config), "-f", "json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["worst"] == "breaking"
    assert result.stderr == ""


class FakePost:
    """Stands in for post_comment; records calls, optionally raises."""

    def __init__(self, error: GitHubError | None = None):
        self.calls: list[tuple[str, int, str, bool]] = []
        self.error = error

    def __call__(
        self, client: object, repo: str, pr: int, body: str, *, create: bool = True
    ) -> str:
        self.calls.append((repo, pr, body, create))
        if self.error:
            raise self.error
        return "created"


@pytest.fixture
def github_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/shop")


def test_check_pr_posts_markdown_comment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, github_env: None
):
    fake = FakePost()
    monkeypatch.setattr("schemaguard.cli.post_comment", fake)
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    result = runner.invoke(app, ["check", "--config", str(config), "--pr", "7"])

    assert result.exit_code == 1
    assert "source app.customers" in result.stdout
    [(repo, pr, body, create)] = fake.calls
    assert (repo, pr, create) == ("acme/shop", 7, True)
    assert body.splitlines()[0] == MARKER


def test_check_pr_empty_report_does_not_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, github_env: None
):
    fake = FakePost()
    monkeypatch.setattr("schemaguard.cli.post_comment", fake)
    config = make_project(tmp_path, {})

    result = runner.invoke(app, ["check", "--config", str(config), "--pr", "7"])

    assert result.exit_code == 0
    assert [c[3] for c in fake.calls] == [False]


def test_check_without_pr_does_not_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, github_env: None
):
    fake = FakePost()
    monkeypatch.setattr("schemaguard.cli.post_comment", fake)
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    runner.invoke(app, ["check", "--config", str(config)])

    assert fake.calls == []


def test_check_pr_needs_token_and_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    config = make_project(tmp_path, {})

    result = runner.invoke(app, ["check", "--config", str(config), "--pr", "7"])

    assert result.exit_code == 2
    assert "GITHUB_TOKEN" in result.stderr


def test_check_pr_must_be_positive(tmp_path: Path, github_env: None):
    config = make_project(tmp_path, {})

    result = runner.invoke(app, ["check", "--config", str(config), "--pr", "0"])

    assert result.exit_code == 2


def test_check_pr_post_failure_warns_and_keeps_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, github_env: None
):
    monkeypatch.setattr("schemaguard.cli.post_comment", FakePost(GitHubError("403")))
    config = make_project(tmp_path, {"0001.py": alembic_fixture("drop_column.py")})

    result = runner.invoke(app, ["check", "--config", str(config), "--pr", "7"])

    assert result.exit_code == 1
    assert "Warning: could not post the PR comment: 403" in result.stderr
    assert "secret-token" not in result.stdout + result.stderr
