from sqlglot import exp, parse

from schemaguard.migrations.changes import ChangeKind, ChangeSet, SchemaChange


def parse_sql(sql: str, source_file: str, line: int = 1) -> ChangeSet:
    changes: list[SchemaChange] = []

    for statement in parse(sql, read="postgres"):
        if isinstance(statement, exp.Alter):
            changes.extend(_parse_alter(statement, source_file, line))

    return ChangeSet(changes=tuple(changes), not_analyzed=())


def _parse_alter(stm: exp.Alter, source_file: str, line: int) -> list[SchemaChange]:
    changes: list[SchemaChange] = []
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
        elif isinstance(action, exp.Drop):
            column = action.args["tables"][0].this.this
            change = SchemaChange(
                kind=ChangeKind.DROP_COLUMN,
                table=table,
                source_file=source_file,
                line=line,
                column=column,
            )
            changes.append(change)

    return changes
