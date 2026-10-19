from ast import (
    Attribute,
    Call,
    Constant,
    Expr,
    FunctionDef,
    Name,
    Pass,
    parse,
    unparse,
)

from schemaguard.migrations.changes import (
    ChangeKind,
    ChangeSet,
    NotAnalyzed,
    SchemaChange,
)
from schemaguard.migrations.sql import parse_sql
from schemaguard.migrations.text import short


def parse_alembic(source: str, source_file: str, line: int = 1) -> ChangeSet:
    results: list[SchemaChange | NotAnalyzed] = []
    tree = parse(source)

    upgrade_node: FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, FunctionDef) and node.name == "upgrade":
            upgrade_node = node
            break

    if not upgrade_node:
        not_analyzed = [
            NotAnalyzed(
                reason="No upgrade() function found",
                source_file=source_file,
                line=line,
            )
        ]
        return ChangeSet(changes=(), not_analyzed=tuple(not_analyzed))

    for node in upgrade_node.body:
        # docstrings, bare strings and pass do nothing
        if isinstance(node, Pass) or (
            isinstance(node, Expr)
            and isinstance(node.value, Constant)
            and isinstance(node.value.value, str)
        ):
            continue

        if not (isinstance(node, Expr) and isinstance(node.value, Call)):
            results.append(
                NotAnalyzed(
                    reason=f"Statement not checked: {short(unparse(node))}",
                    source_file=source_file,
                    line=node.lineno,
                )
            )
            continue

        call = node.value
        if not (
            isinstance(call.func, Attribute)
            and isinstance(call.func.value, Name)
            and call.func.value.id == "op"
        ):
            results.append(
                NotAnalyzed(
                    reason=f"Non-op call not checked: {short(unparse(node))}",
                    source_file=source_file,
                    line=node.lineno,
                )
            )
            continue

        if call.func.attr == "drop_table":
            results.append(_parse_drop_table(call, source_file))
        elif call.func.attr == "rename_table":
            results.append(_parse_rename_table(call, source_file))
        elif call.func.attr == "drop_column":
            results.append(_parse_drop_column(call, source_file))
        elif call.func.attr == "alter_column":
            results.extend(_parse_alter_column(call, source_file))
        elif call.func.attr == "add_column":
            results.append(_parse_add_column(call, source_file))
        elif call.func.attr == "execute":
            results.extend(_parse_execute(call, source_file))
        else:
            results.append(
                NotAnalyzed(
                    reason=f"op.{call.func.attr} not checked: {short(unparse(node))}",
                    source_file=source_file,
                    line=node.lineno,
                )
            )

    changes = tuple(change for change in results if isinstance(change, SchemaChange))
    not_analyzed = tuple(
        not_analyzed
        for not_analyzed in results
        if isinstance(not_analyzed, NotAnalyzed)
    )

    return ChangeSet(changes=changes, not_analyzed=not_analyzed)


def _parse_drop_table(node: Call, source_file: str) -> SchemaChange | NotAnalyzed:
    if not node.args:
        return NotAnalyzed(
            reason=f"op.drop_table not checked: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    arg = node.args[0]
    if not (isinstance(arg, Constant) and isinstance(arg.value, str)):
        return NotAnalyzed(
            reason=f"op.drop_table not checked: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    table = arg.value
    return SchemaChange(
        kind=ChangeKind.DROP_TABLE,
        table=table,
        source_file=source_file,
        line=node.lineno,
    )


def _parse_rename_table(node: Call, source_file: str) -> SchemaChange | NotAnalyzed:
    if len(node.args) < 2:
        return NotAnalyzed(
            reason=f"op.rename_table not checked: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    first_arg = node.args[0]
    sec_arg = node.args[1]
    if not (isinstance(first_arg, Constant) and isinstance(sec_arg, Constant)):
        return NotAnalyzed(
            reason=f"op.rename_table not checked: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    if not (isinstance(first_arg.value, str) and isinstance(sec_arg.value, str)):
        return NotAnalyzed(
            reason=f"op.rename_table arguments aren't strings: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    table = first_arg.value
    new_name = sec_arg.value
    return SchemaChange(
        kind=ChangeKind.RENAME_TABLE,
        table=table,
        new_name=new_name,
        source_file=source_file,
        line=node.lineno,
    )


def _parse_drop_column(node: Call, source_file: str) -> SchemaChange | NotAnalyzed:
    if len(node.args) < 2:
        return NotAnalyzed(
            reason=f"op.drop_column not checked: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    first_arg = node.args[0]
    sec_arg = node.args[1]
    if not (isinstance(first_arg, Constant) and isinstance(sec_arg, Constant)):
        return NotAnalyzed(
            reason=f"op.drop_column not checked: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    if not (isinstance(first_arg.value, str) and isinstance(sec_arg.value, str)):
        return NotAnalyzed(
            reason=f"op.drop_column arguments aren't strings: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    table = first_arg.value
    column = sec_arg.value
    return SchemaChange(
        kind=ChangeKind.DROP_COLUMN,
        table=table,
        column=column,
        source_file=source_file,
        line=node.lineno,
    )


def _parse_alter_column(
    node: Call, source_file: str
) -> list[SchemaChange | NotAnalyzed]:
    if len(node.args) < 2:
        return [
            NotAnalyzed(
                reason=f"op.alter_column not checked: {short(unparse(node))}",
                source_file=source_file,
                line=node.lineno,
            )
        ]

    result: list[SchemaChange | NotAnalyzed] = []

    existing_type: str | None = None
    first_arg = node.args[0]
    sec_arg = node.args[1]
    if not (isinstance(first_arg, Constant) and isinstance(sec_arg, Constant)):
        return [
            NotAnalyzed(
                reason=f"op.alter_column not checked: {short(unparse(node))}",
                source_file=source_file,
                line=node.lineno,
            )
        ]

    if not (isinstance(first_arg.value, str) and isinstance(sec_arg.value, str)):
        return [
            NotAnalyzed(
                reason=f"op.alter_column arguments aren't strings: {short(unparse(node))}",
                source_file=source_file,
                line=node.lineno,
            )
        ]

    table = first_arg.value
    column = sec_arg.value

    for keyword in node.keywords:
        if keyword.arg == "existing_type":
            existing_type = unparse(keyword.value)

    for keyword in node.keywords:
        if keyword.arg == "new_column_name":
            if not (
                isinstance(keyword.value, Constant)
                and isinstance(keyword.value.value, str)
            ):
                result.append(
                    NotAnalyzed(
                        reason=f"op.alter_column new_column_name isn't a string literal: {short(unparse(node))}",
                        source_file=source_file,
                        line=node.lineno,
                    )
                )
                continue

            result.append(
                SchemaChange(
                    kind=ChangeKind.RENAME_COLUMN,
                    table=table,
                    column=column,
                    new_name=keyword.value.value,
                    source_file=source_file,
                    line=node.lineno,
                )
            )
        elif keyword.arg == "type_":
            result.append(
                SchemaChange(
                    kind=ChangeKind.ALTER_TYPE,
                    table=table,
                    source_file=source_file,
                    column=column,
                    new_type=unparse(keyword.value),
                    old_type=existing_type,
                    line=node.lineno,
                )
            )
        elif keyword.arg == "nullable":
            if not (
                isinstance(keyword.value, Constant)
                and isinstance(keyword.value.value, bool)
            ):
                result.append(
                    NotAnalyzed(
                        reason=f"op.alter_column nullable isn't True/False: {short(unparse(node))}",
                        source_file=source_file,
                        line=node.lineno,
                    )
                )
                continue

            result.append(
                SchemaChange(
                    kind=ChangeKind.ALTER_NULLABILITY,
                    table=table,
                    column=column,
                    nullable=keyword.value.value,
                    source_file=source_file,
                    line=node.lineno,
                )
            )
        elif keyword.arg is None:
            result.append(
                NotAnalyzed(
                    reason=f"op.alter_column **kwargs not checked: {short(unparse(node))}",
                    source_file=source_file,
                    line=node.lineno,
                )
            )
        elif keyword.arg.startswith("existing_"):
            pass  # describes the old state, not a change
        else:
            result.append(
                NotAnalyzed(
                    reason=f"op.alter_column {keyword.arg} not checked: {short(unparse(node))}",
                    source_file=source_file,
                    line=node.lineno,
                )
            )
    if result:
        return result

    return [
        NotAnalyzed(
            reason=f"op.alter_column has no supported keyword: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )
    ]


def _parse_add_column(node: Call, source_file: str) -> SchemaChange | NotAnalyzed:
    if len(node.args) < 2:
        return NotAnalyzed(
            reason=f"op.add_column not checked: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    first_arg = node.args[0]
    column_node = node.args[1]
    if not (isinstance(first_arg, Constant) and isinstance(first_arg.value, str)):
        return NotAnalyzed(
            reason=f"op.add_column not checked: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    if not isinstance(column_node, Call):
        return NotAnalyzed(
            reason=f"op.add_column column isn't a Column() call: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    func = column_node.func

    if not (
        (isinstance(func, Attribute) and func.attr == "Column")
        or (isinstance(func, Name) and func.id == "Column")
    ):
        return NotAnalyzed(
            reason=f"op.add_column column isn't a Column() call: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    if len(column_node.args) < 1:
        return NotAnalyzed(
            reason=f"op.add_column Column(...) has no name: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    column_arg = column_node.args[0]
    if not (isinstance(column_arg, Constant) and isinstance(column_arg.value, str)):
        return NotAnalyzed(
            reason=f"op.add_column column name isn't a string literal: {short(unparse(node))}",
            source_file=source_file,
            line=node.lineno,
        )

    new_type = None if len(column_node.args) < 2 else unparse(column_node.args[1])
    return SchemaChange(
        kind=ChangeKind.ADD_COLUMN,
        table=first_arg.value,
        column=column_arg.value,
        new_type=new_type,
        source_file=source_file,
        line=node.lineno,
    )


def _parse_execute(node: Call, source_file: str) -> list[SchemaChange | NotAnalyzed]:
    if not node.args:
        return [
            NotAnalyzed(
                reason=f"op.execute not checked: {short(unparse(node))}",
                source_file=source_file,
                line=node.lineno,
            )
        ]

    arg = node.args[0]
    if not (isinstance(arg, Constant) and isinstance(arg.value, str)):
        return [
            NotAnalyzed(
                reason=f"op.execute argument isn't a string literal: {short(unparse(node))}",
                source_file=source_file,
                line=node.lineno,
            )
        ]

    sql = arg.value
    change_set = parse_sql(sql, source_file, line=node.lineno)
    return list(change_set.changes) + list(change_set.not_analyzed)
