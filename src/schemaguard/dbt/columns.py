from pydantic import BaseModel, ConfigDict
from sqlglot import exp, parse_one
from sqlglot.errors import ParseError


class ColumnUsage(BaseModel):
    model_config = ConfigDict(frozen=True)
    columns: frozenset[str] = frozenset()
    uncertain: bool


def column_usage(sql: str | None, table: str) -> ColumnUsage:
    if not sql:
        return ColumnUsage(uncertain=True)

    try:
        tree = parse_one(sql, read="postgres")
    except ParseError:
        return ColumnUsage(uncertain=True)

    columns: list[str] = []

    for column in tree.find_all(exp.Column):
        if not isinstance(column.this, exp.Star):
            columns.append(column.name)

    return ColumnUsage(columns=frozenset(columns), uncertain=False)
