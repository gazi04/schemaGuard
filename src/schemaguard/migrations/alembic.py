from ast import Attribute, Call, Constant, Expr, FunctionDef, Name, dump, parse, unparse

from schemaguard.migrations.changes import (
    ChangeKind,
    ChangeSet,
    NotAnalyzed,
    SchemaChange,
)


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
        if not (isinstance(node, Expr) and isinstance(node.value, Call)):
            results.append(
                NotAnalyzed(
                    reason=f"Statement not checked: {unparse(node)}",
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
                    reason=f"Non-op call not checked: {unparse(node)}",
                    source_file=source_file,
                    line=node.lineno,
                )
            )
            continue

        if call.func.attr == "drop_table":
            results.append(_parse_drop_table(call, source_file))
        else:
            results.append(
                NotAnalyzed(
                    reason=f"op.{call.func.attr} not checked: {unparse(node)}",
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
            reason=f"op.drop_table not checked: {unparse(node)}",
            source_file=source_file,
            line=node.lineno,
        )

    arg = node.args[0]
    if not (isinstance(arg, Constant) and isinstance(arg.value, str)):
        return NotAnalyzed(
            reason=f"drop_table not checked: {unparse(node)}",
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




