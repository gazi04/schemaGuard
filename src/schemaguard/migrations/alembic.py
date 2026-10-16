from ast import Attribute, Call, Expr, FunctionDef, Name, dump, parse

from schemaguard.migrations.changes import ChangeSet, NotAnalyzed


def parse_alembic(source: str, source_file: str, line: int = 1) -> ChangeSet:
    tree = parse(source)

    upgrade_node: FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, FunctionDef) and node.name == "upgrade":
            upgrade_node = node
            break

    if not upgrade_node:
        not_analyzed = [
            NotAnalyzed(
                reason="Couldn't find the upgrade() function in the alembic migration.",
                source_file=source_file,
                line=line,
            )
        ]
        return ChangeSet(changes=(), not_analyzed=tuple(not_analyzed))

    for node in upgrade_node.body:
        if not (isinstance(node, Expr) and isinstance(node.value, Call)):
            continue

        call = node.value
        if not (
            isinstance(call.func, Attribute)
            and isinstance(call.func.value, Name)
            and call.func.value.id == "op"
        ):
            continue

        print(dump(node, indent=2))

    return ChangeSet(changes=(), not_analyzed=())

