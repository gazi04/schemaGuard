import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from schemaguard.config import ConfigError, FailOn, load_config
from schemaguard.dbt.columns import ColumnUsage, column_usage
from schemaguard.dbt.lineage import (
    Downstream,
    downstream,
    find_source,
    first_hop,
    split,
)
from schemaguard.dbt.manifest import Manifest
from schemaguard.github import GitHubError, make_client, post_comment
from schemaguard.impact import AnalyzerError, ImpactReport, analyze, should_fail
from schemaguard.migrations import (
    ChangeSet,
    parse_alembic,
    parse_sql,
)
from schemaguard.report import (
    format_change,
    format_json,
    format_markdown,
    format_not_analyzed,
    format_report,
)


class OutputFormat(StrEnum):
    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


app = typer.Typer(no_args_is_help=True)


@app.callback()
def callback() -> None:
    """Find dbt models broken by database migrations"""


@app.command()
def parse(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Print the schema changes found in one migration file"""
    result = parse_file(file)

    entries = [(c.line, format_change(c)) for c in result.changes]
    entries += [(n.line, format_not_analyzed(n)) for n in result.not_analyzed]

    if not entries:
        typer.echo("No changes found.")
        return

    for _, line in sorted(entries, key=lambda e: e[0]):
        typer.echo(line)


@app.command()
def lineage(
    source: Annotated[
        str,
        typer.Argument(help="dbt source as <source>.<table>, e.g. ecom.raw_customers"),
    ],
    manifest: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ] = Path("target/manifest.json"),
) -> None:
    """Print the dbt models downstream of a source"""

    source_name, _, table_name = source.partition(".")

    if not source_name or not table_name:
        typer.echo(
            "Error: expected <source>.<table>, e.g. ecom.raw_customers", err=True
        )
        raise typer.Exit(code=2)

    m = load_manifest(manifest)
    source_id = find_source(m, source_name, table_name)

    if source_id is None:
        typer.echo(f"Error: unknown source {source}", err=True)
        raise typer.Exit(code=2)

    source_node = m.sources[source_id]

    items = downstream(m, source_id)
    lin = split(m, items)

    usages: dict[str, ColumnUsage] = {}
    uncompiled = False
    for d in first_hop(lin):
        node = m.nodes[d.unique_id]
        if not node.compiled_code:
            uncompiled = True
        usages[d.unique_id] = column_usage(node.compiled_code, source_node.identifier)

    typer.echo(f"source {source}")

    if not lin.models:
        typer.echo("  no downstream models")

    for item in lin.models:
        name = m.nodes[item.unique_id].name
        typer.echo(format_model(item, name, usages.get(item.unique_id)))

    typer.echo(f"  tests: {len(lin.tests)}")

    if lin.exposures:
        names = ", ".join(m.exposures[e.unique_id].name for e in lin.exposures)
        typer.echo(f"  exposures: {names}")

    if uncompiled:
        typer.echo(
            "hint: some models have no compiled SQL; run dbt compile or dbt build",
            err=True,
        )


@app.command()
def check(
    files: Annotated[
        list[Path] | None,
        typer.Argument(
            exists=True,
            dir_okay=False,
            readable=True,
            help="Migration files to check (default: the config's migrations folder)",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", "-c", exists=True, dir_okay=False, readable=True),
    ] = Path("schemaguard.yml"),
    output_format: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="...")
    ] = OutputFormat.TEXT,
    fail_on: Annotated[
        FailOn | None,
        typer.Option(
            "--fail-on",
            help="Exit 1 at this severity or above (default: the config's fail_on)",
        ),
    ] = None,
    pr: Annotated[
        int | None,
        typer.Option(
            "--pr",
            min=1,
            help="Also post the report as a comment on this PR "
            "(needs GITHUB_TOKEN and GITHUB_REPOSITORY in the environment)",
        ),
    ] = None,
) -> None:
    """Check migrations against the dbt project

    Exit codes: 0 below the fail_on threshold, 1 at or above it, 2 on errors.
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if pr is not None and not (token and repo):
        typer.echo(
            "Error: --pr needs GITHUB_TOKEN and GITHUB_REPOSITORY to be set", err=True
        )
        raise typer.Exit(code=2)

    try:
        cfg = load_config(config.read_text(encoding="utf-8"))
    except (ConfigError, UnicodeDecodeError) as e:
        typer.echo(f"Error: {config}: {e}", err=True)
        raise typer.Exit(code=2) from e

    base = config.parent

    if not files:
        folder = base / cfg.migrations
        if not folder.is_dir():
            typer.echo(f"Error: migrations folder {folder} not found", err=True)
            raise typer.Exit(code=2)
        files = migration_files(folder)

    change_set = merge_change_sets([parse_file(f) for f in files])
    manifest = load_manifest(base / cfg.manifest)

    try:
        report = analyze(change_set, manifest, cfg)
    except AnalyzerError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=2) from e

    if output_format is OutputFormat.JSON:
        typer.echo(format_json(report))
    elif output_format is OutputFormat.MARKDOWN:
        typer.echo(format_markdown(report))
    else:
        for line in format_report(report):
            typer.echo(line)

    if pr is not None:
        comment_on_pr(report, token, repo, pr)

    if should_fail(report.worst, fail_on or cfg.fail_on):
        raise typer.Exit(code=1)


def comment_on_pr(report: ImpactReport, token: str, repo: str, pr: int) -> None:
    """Post the markdown report. A failure warns but never changes the exit code."""
    empty = not (report.impacts or report.unmapped or report.not_analyzed)
    try:
        with make_client(token) as client:
            post_comment(client, repo, pr, format_markdown(report), create=not empty)
    except GitHubError as e:
        typer.echo(f"Warning: could not post the PR comment: {e}", err=True)


def parse_file(file: Path) -> ChangeSet:
    suffix = file.suffix.lower()

    if suffix not in (".py", ".sql"):
        typer.echo(f"Error: {file} is not a .py or .sql migration", err=True)
        raise typer.Exit(code=2)

    text = file.read_text(encoding="utf-8")
    if suffix == ".py":
        return parse_alembic(text, str(file))
    return parse_sql(text, str(file))


def load_manifest(path: Path) -> Manifest:
    if not path.is_file():
        typer.echo(f"Error: manifest {path} not found", err=True)
        raise typer.Exit(code=2)

    try:
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, UnicodeDecodeError) as e:
        typer.echo(f"Error: {path} is not a valid dbt manifest", err=True)
        raise typer.Exit(code=2) from e


def migration_files(folder: Path) -> list[Path]:
    return sorted(
        p
        for p in folder.iterdir()
        if p.is_file()
        and p.suffix.lower() in (".py", ".sql")
        and not p.name.startswith("__")
    )


def merge_change_sets(change_sets: list[ChangeSet]) -> ChangeSet:
    return ChangeSet(
        changes=tuple(c for cs in change_sets for c in cs.changes),
        not_analyzed=tuple(n for cs in change_sets for n in cs.not_analyzed),
    )


def format_columns(usage: ColumnUsage) -> str:
    names = ", ".join(sorted(usage.columns))

    if not usage.uncertain:
        return f"columns: {names or 'none'}"
    if names:
        return f"columns: {names} (uncertain)"
    return "columns: uncertain"


def format_model(item: Downstream, name: str, usage: ColumnUsage | None) -> str:
    line = f"  hop {item.depth}  {name:<20}"

    if usage is not None:
        line = f"{line} {format_columns(usage)}"

    return line.rstrip()
