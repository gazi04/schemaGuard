from sqlglot import exp, parse

from schemaguard.migrations.changes import ChangeKind, ChangeSet, SchemaChange


def parse_sql(sql: str, source_file: str, line: int = 1) -> ChangeSet:
    changes: list[SchemaChange] = []

    for statement in parse(sql, read="postgres"):
        if not isinstance(statement, exp.Alter):
            continue

        table = statement.this.name

        for action in statement.actions:
            column = action.this.name

            if isinstance(action, exp.RenameColumn):
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

    return ChangeSet(changes=tuple(changes), not_analyzed=())
