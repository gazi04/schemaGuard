from pathlib import Path
from typing import Annotated

import typer

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
