from collections.abc import Iterable
from enum import StrEnum

from schemaguard.config import FailOn
from schemaguard.migrations import ChangeKind, SchemaChange

TABLE_LEVEL = frozenset({ChangeKind.DROP_TABLE, ChangeKind.RENAME_TABLE})


class Severity(StrEnum):
    SAFE = "safe"
    RISKY = "risky"
    BREAKING = "breaking"

    @property
    def rank(self) -> int:
        """Order for comparisons; a StrEnum itself sorts alphabetically."""
        return _RANK[self]


# Module level: a dict inside the enum body would become an enum member.
_RANK: dict[Severity, int] = {
    Severity.SAFE: 0,
    Severity.RISKY: 1,
    Severity.BREAKING: 2,
}


# The lowest severity that fails the run; `never` has none.
_THRESHOLD: dict[FailOn, Severity | None] = {
    FailOn.BREAKING: Severity.BREAKING,
    FailOn.RISKY: Severity.RISKY,
    FailOn.NEVER: None,
}


def should_fail(worst: Severity, fail_on: FailOn) -> bool:
    """True when `worst` reaches the `fail_on` threshold."""
    threshold = _THRESHOLD[fail_on]
    return threshold is not None and worst.rank >= threshold.rank


def classify(change: SchemaChange, affected: bool) -> Severity:
    """`affected`: a model or a source test reads the changed column or table."""
    # A dropped or renamed table breaks the dbt source itself,
    # even when no model reads it.
    if change.kind in TABLE_LEVEL:
        return Severity.BREAKING

    if not affected:
        return Severity.SAFE

    match change.kind:
        case ChangeKind.DROP_COLUMN | ChangeKind.RENAME_COLUMN:
            return Severity.BREAKING
        case ChangeKind.ALTER_TYPE:
            return Severity.RISKY
        case ChangeKind.ALTER_NULLABILITY:
            # Becoming NOT NULL is safe; becoming nullable is risky.
            # A missing value is treated as risky rather than guessed safe.
            return Severity.SAFE if change.nullable is False else Severity.RISKY
        case _:
            return Severity.SAFE


def _rename_key(change: SchemaChange) -> tuple[str, str]:
    return change.source_file, change.table.lower()


def rename_candidates(changes: Iterable[SchemaChange]) -> frozenset[tuple[str, str]]:
    """(file, table) pairs with both a drop_column and an add_column.

    Alembic autogenerate writes a column rename as drop + add.
    """
    dropped: set[tuple[str, str]] = set()
    added: set[tuple[str, str]] = set()

    for change in changes:
        if change.kind is ChangeKind.DROP_COLUMN:
            dropped.add(_rename_key(change))
        elif change.kind is ChangeKind.ADD_COLUMN:
            added.add(_rename_key(change))

    return frozenset(dropped & added)


def is_possible_rename(
    change: SchemaChange, candidates: frozenset[tuple[str, str]]
) -> bool:
    return change.kind is ChangeKind.DROP_COLUMN and _rename_key(change) in candidates
