from sqlglot import exp, parse
from sqlglot.errors import ParseError

from schemaguard.migrations.changes import (
    ChangeKind,
    ChangeSet,
    NotAnalyzed,
    SchemaChange,
)

MAX_SQL_LENGTH: int = 80


def _short(sql: str) -> str:
    text = " ".join(sql.split())

    if len(text) <= MAX_SQL_LENGTH:
        return text

    return text[:MAX_SQL_LENGTH] + "..."


def parse_sql(sql: str, source_file: str, line: int = 1) -> ChangeSet:
    results: list[SchemaChange | NotAnalyzed] = []

    try:
        statements = parse(sql, read="postgres")
    except ParseError:
        not_analyzed = [
            NotAnalyzed(
                reason=f"Could not parse SQL: {_short(sql)}",
                source_file=source_file,
                line=line,
            )
        ]
        return ChangeSet(
            changes=(),
            not_analyzed=tuple(not_analyzed),
        )

    for statement in statements:
        if statement is None:
            continue

        if isinstance(statement, exp.Alter):
            results.extend(_parse_alter(statement, source_file, line))
        elif isinstance(statement, exp.Drop):
            results.extend(_parse_drop(statement, source_file, line))
        elif isinstance(statement, exp.Command):
            results.append(
                NotAnalyzed(
                    reason=f"Could not break down statement: {_short(statement.sql(dialect='postgres'))}",
                    source_file=source_file,
                    line=line,
                )
            )
        else:
            results.append(
                NotAnalyzed(
                    reason=f"Statement not checked: {_short(statement.sql(dialect='postgres'))}",
                    source_file=source_file,
                    line=line,
                )
            )

    changes = tuple(change for change in results if isinstance(change, SchemaChange))
    not_analyzed = tuple(
        not_analyzed
        for not_analyzed in results
        if isinstance(not_analyzed, NotAnalyzed)
    )

    return ChangeSet(changes=changes, not_analyzed=not_analyzed)


def _parse_alter(
    stm: exp.Alter, source_file: str, line: int
) -> list[SchemaChange | NotAnalyzed]:
    changes: list[SchemaChange | NotAnalyzed] = []
    table = stm.this.name

    for action in stm.actions:
        if isinstance(action, exp.RenameColumn):
            column = action.this.name
            new_name = action.args["to"].name
            change = SchemaChange(
                kind=ChangeKind.RENAME_COLUMN,
                table=table,
                source_file=source_file,
                line=line,
                column=column,
                new_name=new_name,
            )
            changes.append(change)
        elif isinstance(action, exp.ColumnDef):
            new_column = action.name
            column_type = str(action.args.get("kind"))
            changes.append(
                SchemaChange(
                    kind=ChangeKind.ADD_COLUMN,
                    table=table,
                    source_file=source_file,
                    line=line,
                    column=new_column,
                    new_type=column_type,
                )
            )
        elif isinstance(action, exp.AlterColumn):
            dtype = action.args.get("dtype")
            column = action.this.name
            allow_null = action.args.get("allow_null")

            if dtype is not None:
                changes.append(
                    SchemaChange(
                        kind=ChangeKind.ALTER_TYPE,
                        table=table,
                        source_file=source_file,
                        line=line,
                        column=column,
                        new_type=dtype.sql(dialect="postgres"),
                    )
                )

            elif allow_null is not None:
                changes.append(
                    SchemaChange(
                        kind=ChangeKind.ALTER_NULLABILITY,
                        table=table,
                        source_file=source_file,
                        line=line,
                        column=column,
                        nullable=allow_null,
                    )
                )

        elif isinstance(action, exp.AlterRename):
            name = action.this.name
            changes.append(
                SchemaChange(
                    kind=ChangeKind.RENAME_TABLE,
                    table=table,
                    source_file=source_file,
                    line=line,
                    new_name=name,
                )
            )
        elif isinstance(action, exp.Drop):
            if action.args.get("kind") != "COLUMN":
                # TODO step 5: NotAnalyzed
                continue

            column = action.args["tables"][0].name
            change = SchemaChange(
                kind=ChangeKind.DROP_COLUMN,
                table=table,
                source_file=source_file,
                line=line,
                column=column,
            )
            changes.append(change)

    return changes


def _parse_drop(
    stm: exp.Drop, source_file: str, line: int
) -> list[SchemaChange | NotAnalyzed]:
    changes: list[SchemaChange | NotAnalyzed] = []

    if stm.kind != "TABLE":
        return changes

    for table in stm.args.get("tables", []):
        change = SchemaChange(
            kind=ChangeKind.DROP_TABLE,
            table=table.name,
            source_file=source_file,
            line=line,
        )
        changes.append(change)

    return changes
