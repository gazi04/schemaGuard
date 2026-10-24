from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError

from schemaguard.dbt.columns import ColumnUsage, column_usage
from schemaguard.dbt.lineage import (
    Downstream,
    downstream,
    find_source,
    first_hop,
    split,
)
from schemaguard.dbt.manifest import Manifest
from schemaguard.migrations import (
    ChangeKind,
    NotAnalyzed,
    SchemaChange,
    parse_alembic,
    parse_sql,
)

app = typer.Typer(no_args_is_help=True)


@app.callback()
def callback() -> None:
    """Find dbt models broken by database migrations"""


@app.command()
def parse(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Print the schema changes found in one migration file"""
    suffix = file.suffix.lower()

    if suffix not in (".py", ".sql"):
        typer.echo(f"Error: {file} is not a .py or .sql migration", err=True)
        raise typer.Exit(code=2)

    text = file.read_text(encoding="utf-8")
    if suffix == ".py":
        result = parse_alembic(text, str(file))
    else:
        result = parse_sql(text, str(file))

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

    try:
        m = Manifest.model_validate_json(manifest.read_text(encoding="utf-8"))
    except (ValidationError, UnicodeDecodeError) as e:
        typer.echo(f"Error: {manifest} is not a valid dbt manifest", err=True)
        raise typer.Exit(code=2) from e

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


def format_change(change: SchemaChange) -> str:
    target = change.table

    if change.column is not None:
        target = f"{change.table}.{change.column}"

    match change.kind:
        case ChangeKind.RENAME_COLUMN | ChangeKind.RENAME_TABLE:
            detail = f"-> {change.new_name}"
        case ChangeKind.ALTER_TYPE:
            detail = f"{change.old_type or '?'} -> {change.new_type}"
        case ChangeKind.ALTER_NULLABILITY:
            detail = "-> nullable" if change.nullable else "-> not null"
        case ChangeKind.ADD_COLUMN:
            detail = change.new_type or ""
        case ChangeKind.DROP_COLUMN | ChangeKind.DROP_TABLE:
            detail = ""

    location = f"{change.source_file}:{change.line}"
    return f"{location} {change.kind:<17} {target} {detail}".rstrip()


def format_not_analyzed(entry: NotAnalyzed) -> str:
    location = f"{entry.source_file}:{entry.line}"
    return f"{location} {'not_analyzed':<17} {entry.reason}"


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
