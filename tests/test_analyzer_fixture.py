import pytest

from schemaguard.config import SourceRef, load_config
from schemaguard.dbt.manifest import Manifest
from schemaguard.impact import AnalyzerError, ChangeImpact, Severity, analyze
from schemaguard.migrations import (
    ChangeKind,
    ChangeSet,
    SchemaChange,
    parse_alembic,
    parse_sql,
)
from tests.helper import read_fixture, summary

MANIFEST = Manifest.model_validate_json(read_fixture("dbt", "manifest.json"))
CONFIG = load_config(
    "sources:\n  customers: app.customers\nignore: [alembic_version]\n"
)

RAW_DUMP = "model.demo.raw_dump"
STG = "model.demo.stg_customers"
UNCOMPILED = "model.demo.stg_uncompiled"
STATS = "model.demo.customer_stats"
REPORT = "model.demo.report"
STG_TEST = "test.demo.not_null_stg_customers_id"

USED = [
    (RAW_DUMP, 1, True),
    (STG, 1, False),
    (UNCOMPILED, 1, True),
    (STATS, 2, False),
    (REPORT, 2, False),
]
UNUSED = [(RAW_DUMP, 1, True), (UNCOMPILED, 1, True), (REPORT, 2, True)]
TABLE = [
    (RAW_DUMP, 1, False),
    (STG, 1, False),
    (UNCOMPILED, 1, False),
    (STATS, 2, False),
    (REPORT, 2, False),
]


def change(
    kind: ChangeKind, column: str | None = None, table: str = "customers"
) -> SchemaChange:
    return SchemaChange(
        kind=kind, table=table, source_file="m.py", line=1, column=column
    )


def impact_of(schema_change: SchemaChange) -> ChangeImpact:
    change_set = ChangeSet(changes=(schema_change,), not_analyzed=())
    report = analyze(change_set, MANIFEST, CONFIG)

    assert len(report.impacts) == 1
    return report.impacts[0]


@pytest.mark.parametrize(
    "schema_change, models, tests, exposures, uncertain",
    [
        pytest.param(
            change(ChangeKind.DROP_COLUMN, "name"),
            USED,
            (STG_TEST,),
            ("dashboard",),
            True,
            id="used_column",
        ),
        pytest.param(
            change(ChangeKind.DROP_COLUMN, "email"),
            UNUSED,
            (),
            ("dashboard",),
            True,
            id="unused_column",
        ),
        pytest.param(
            change(ChangeKind.DROP_TABLE),
            TABLE,
            (STG_TEST,),
            ("dashboard",),
            False,
            id="drop_table",
        ),
        pytest.param(
            change(ChangeKind.RENAME_TABLE),
            TABLE,
            (STG_TEST,),
            ("dashboard",),
            False,
            id="rename_table",
        ),
        pytest.param(
            change(ChangeKind.ADD_COLUMN, "email"),
            [],
            (),
            (),
            False,
            id="add_column",
        ),
        pytest.param(
            change(ChangeKind.DROP_COLUMN, "NAME", table="Customers"),
            USED,
            (STG_TEST,),
            ("dashboard",),
            True,
            id="case_insensitive",
        ),
    ],
)
def test_fixture_impact(
    schema_change: SchemaChange,
    models: list[tuple[str, int, bool]],
    tests: tuple[str, ...],
    exposures: tuple[str, ...],
    uncertain: bool,
):
    impact = impact_of(schema_change)

    assert impact.source == SourceRef(source_name="app", table_name="customers")
    assert summary(impact.models) == models
    assert impact.tests == tests
    assert impact.exposures == exposures
    assert impact.uncertain is uncertain


def test_alembic_migration_end_to_end():
    change_set = parse_alembic(
        read_fixture("alembic", "drop_column.py"), "drop_column.py"
    )

    report = analyze(change_set, MANIFEST, CONFIG)

    assert len(report.impacts) == 1
    impact = report.impacts[0]
    assert impact.change.column == "signup_date"
    assert impact.change.source_file == "drop_column.py"
    assert summary(impact.models) == UNUSED
    assert report.unmapped == ()
    assert report.not_analyzed == ()


def test_sql_migration_end_to_end():
    change_set = parse_sql(read_fixture("sql", "mixed.sql"), "mixed.sql")

    report = analyze(change_set, MANIFEST, CONFIG)

    assert len(report.impacts) == 1
    impact = report.impacts[0]
    assert impact.change.column == "signup_date"
    assert summary(impact.models) == UNUSED
    assert [c.table for c in report.unmapped] == ["orders"]
    assert len(report.not_analyzed) == 2


def test_demo_config_does_not_match_fixture_manifest():
    config = load_config(read_fixture("config", "demo.yml"))
    change_set = parse_sql(read_fixture("sql", "mixed.sql"), "mixed.sql")

    with pytest.raises(AnalyzerError, match=r"ecom\.raw_customers"):
        analyze(change_set, MANIFEST, config)


def test_severity_and_possible_rename():
    drop = change(ChangeKind.DROP_COLUMN, "name")
    add = change(ChangeKind.ADD_COLUMN, "full_name")
    report = analyze(ChangeSet(changes=(drop, add), not_analyzed=()), MANIFEST, CONFIG)

    dropped, added = report.impacts
    assert dropped.severity is Severity.BREAKING
    assert dropped.possible_rename is True
    assert added.severity is Severity.SAFE
    assert added.possible_rename is False
    assert report.worst is Severity.BREAKING


def test_uncertain_drop_stays_breaking():
    impact = impact_of(change(ChangeKind.DROP_COLUMN, "not_used_anywhere"))

    assert impact.uncertain is True
    assert impact.severity is Severity.BREAKING
