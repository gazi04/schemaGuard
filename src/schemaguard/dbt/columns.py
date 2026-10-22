from pydantic import BaseModel, ConfigDict
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError
from sqlglot.optimizer.scope import Scope, build_scope


class ColumnUsage(BaseModel):
    model_config = ConfigDict(frozen=True)
    columns: frozenset[str] = frozenset()
    uncertain: bool


def _is_star(projection: exp.Expr) -> bool:
    return isinstance(projection, exp.Star) or (
        isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star)
    )


def _star_reaches(scope: Scope, table: str) -> bool:
    if scope.set_operation_scopes:
        return any(
            _star_reaches(branch, table) for branch in scope.set_operation_scopes
        )

    select = scope.expression

    if not isinstance(select, exp.Select):
        return False

    if not any(_is_star(projection) for projection in select.selects):
        return False

    for _node, source in scope.selected_sources.values():
        if isinstance(source, exp.Table) and source.name == table:
            return True
        if isinstance(source, Scope) and _star_reaches(source, table):
            return True

    return False


def column_usage(sql: str | None, table: str) -> ColumnUsage:
    if not sql:
        return ColumnUsage(uncertain=True)

    try:
        tree = parse_one(sql, read="postgres")
    except ParseError:
        return ColumnUsage(uncertain=True)

    columns: list[str] = []

    for column in tree.find_all(exp.Column):
        if not _is_star(column):
            columns.append(column.name)

    scope = build_scope(tree)
    uncertain = scope is None or _star_reaches(scope, table)

    return ColumnUsage(columns=frozenset(columns), uncertain=uncertain)
