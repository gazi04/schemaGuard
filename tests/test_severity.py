import pytest

from schemaguard.config import SourceRef
from schemaguard.impact import AffectedModel, ChangeImpact, ImpactReport, Severity
from schemaguard.impact.severity import (
    classify,
    is_possible_rename,
    rename_candidates,
)
from schemaguard.migrations import ChangeKind, SchemaChange

K = ChangeKind
S = Severity


def change(
    kind: ChangeKind = K.DROP_COLUMN,
    *,
    table: str = "customers",
    column: str | None = "email",
    nullable: bool | None = None,
    source_file: str = "m.py",
) -> SchemaChange:
    return SchemaChange(
        kind=kind,
        table=table,
        source_file=source_file,
        line=1,
        column=column,
        nullable=nullable,
    )


def impact(
    schema_change: SchemaChange | None = None,
    *,
    uncertain: bool | None = None,
    tests: tuple[str, ...] = (),
) -> ChangeImpact:
    models = (
        ()
        if uncertain is None
        else (
            AffectedModel(
                unique_id="model.demo.stg", name="stg", depth=1, uncertain=uncertain
            ),
        )
    )
    return ChangeImpact(
        change=schema_change or change(),
        source=SourceRef(source_name="ecom", table_name="raw_customers"),
        models=models,
        tests=tests,
        exposures=(),
    )


def report(*impacts: ChangeImpact) -> ImpactReport:
    return ImpactReport(impacts=impacts, unmapped=(), not_analyzed=())


def test_rank_order() -> None:
    assert S.SAFE.rank < S.RISKY.rank < S.BREAKING.rank


def test_max_by_rank() -> None:
    # Plain max() would pick SAFE: StrEnum compares alphabetically.
    assert max(S, key=lambda s: s.rank) is S.BREAKING


def test_possible_rename_default() -> None:
    assert impact().possible_rename is False


def test_worst_empty() -> None:
    assert report().worst is S.SAFE


def test_dump_has_severity_and_worst() -> None:
    dumped = report(impact()).model_dump()
    assert "worst" in dumped
    assert "severity" in dumped["impacts"][0]
    assert "possible_rename" in dumped["impacts"][0]


@pytest.mark.parametrize(
    ("schema_change", "affected", "expected"),
    [
        (change(K.DROP_TABLE, column=None), True, S.BREAKING),
        (change(K.DROP_TABLE, column=None), False, S.BREAKING),
        (change(K.RENAME_TABLE, column=None), True, S.BREAKING),
        (change(K.RENAME_TABLE, column=None), False, S.BREAKING),
        (change(K.DROP_COLUMN), True, S.BREAKING),
        (change(K.DROP_COLUMN), False, S.SAFE),
        (change(K.RENAME_COLUMN), True, S.BREAKING),
        (change(K.RENAME_COLUMN), False, S.SAFE),
        (change(K.ALTER_TYPE), True, S.RISKY),
        (change(K.ALTER_TYPE), False, S.SAFE),
        (change(K.ALTER_NULLABILITY, nullable=True), True, S.RISKY),
        (change(K.ALTER_NULLABILITY, nullable=True), False, S.SAFE),
        (change(K.ALTER_NULLABILITY, nullable=False), True, S.SAFE),
        (change(K.ALTER_NULLABILITY, nullable=None), True, S.RISKY),
        (change(K.ADD_COLUMN), True, S.SAFE),
        (change(K.ADD_COLUMN), False, S.SAFE),
    ],
)
def test_classify(schema_change: SchemaChange, affected: bool, expected: Severity):
    assert classify(schema_change, affected) is expected


def test_severity_uses_models() -> None:
    assert impact(change(K.DROP_COLUMN), uncertain=False).severity is S.BREAKING
    assert impact(change(K.DROP_COLUMN)).severity is S.SAFE


@pytest.mark.parametrize(
    ("schema_change", "expected"),
    [
        (change(K.DROP_COLUMN), S.BREAKING),
        (change(K.RENAME_COLUMN), S.BREAKING),
        (change(K.ALTER_TYPE), S.RISKY),
        (change(K.ALTER_NULLABILITY, nullable=True), S.RISKY),
        (change(K.ALTER_NULLABILITY, nullable=False), S.SAFE),
        (change(K.ADD_COLUMN), S.SAFE),
    ],
)
def test_severity_counts_tests_without_models(
    schema_change: SchemaChange, expected: Severity
) -> None:
    only_tests = impact(schema_change, tests=("test.src_email",))

    assert only_tests.models == ()
    assert only_tests.severity is expected


def test_uncertain_keeps_full_severity() -> None:
    uncertain = impact(change(K.DROP_COLUMN), uncertain=True)

    assert uncertain.uncertain is True
    assert uncertain.severity is S.BREAKING


def test_worst_picks_highest() -> None:
    risky = impact(change(K.ALTER_TYPE), uncertain=False)
    breaking = impact(change(K.DROP_COLUMN), uncertain=False)
    safe = impact(change(K.ADD_COLUMN), uncertain=False)

    assert report(safe, risky).worst is S.RISKY
    assert report(safe, breaking, risky).worst is S.BREAKING


def test_rename_candidates_drop_and_add() -> None:
    drop = change(K.DROP_COLUMN, column="email")
    add = change(K.ADD_COLUMN, column="mail")
    candidates = rename_candidates([drop, add])

    assert is_possible_rename(drop, candidates)
    assert not is_possible_rename(add, candidates)


def test_rename_candidates_table_case_insensitive() -> None:
    drop = change(K.DROP_COLUMN, table="Customers")
    candidates = rename_candidates([drop, change(K.ADD_COLUMN, table="customers")])

    assert is_possible_rename(drop, candidates)


@pytest.mark.parametrize(
    "add",
    [
        change(K.ADD_COLUMN, table="orders"),
        change(K.ADD_COLUMN, source_file="other.py"),
        change(K.ALTER_TYPE),
    ],
    ids=["other table", "other file", "not an add"],
)
def test_rename_candidates_no_match(add: SchemaChange) -> None:
    drop = change(K.DROP_COLUMN)

    assert not is_possible_rename(drop, rename_candidates([drop, add]))


def test_rename_candidates_flags_every_drop() -> None:
    first = change(K.DROP_COLUMN, column="a")
    second = change(K.DROP_COLUMN, column="b")
    candidates = rename_candidates([first, second, change(K.ADD_COLUMN, column="c")])

    assert is_possible_rename(first, candidates)
    assert is_possible_rename(second, candidates)
