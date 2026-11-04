import pytest

from schemaguard.config import SourceRef
from schemaguard.impact import AffectedModel, ChangeImpact, ImpactReport
from schemaguard.migrations import ChangeKind, NotAnalyzed, SchemaChange
from schemaguard.report import (
    format_change,
    format_impact,
    format_report,
    format_severity,
    format_summary,
)


def test_format_alter_type_without_old_type():
    change = SchemaChange(
        kind=ChangeKind.ALTER_TYPE,
        table="orders",
        column="amount",
        new_type="BIGINT",
        source_file="m.sql",
        line=3,
    )

    assert format_change(change).endswith("orders.amount ? -> BIGINT")


def test_format_impact_without_models():
    change = SchemaChange(
        kind=ChangeKind.ADD_COLUMN,
        table="customers",
        source_file="m.py",
        line=3,
        column="email",
    )
    impact = ChangeImpact(
        change=change,
        source=SourceRef(source_name="app", table_name="customers"),
        models=(),
        tests=(),
        exposures=(),
    )

    assert format_impact(impact) == [
        format_change(change),
        "  source app.customers",
        "  severity: safe",
        "  no affected models",
        "  tests: 0",
    ]


def test_format_severity_marks():
    change = SchemaChange(
        kind=ChangeKind.DROP_COLUMN,
        table="customers",
        source_file="m.py",
        line=3,
        column="email",
    )
    model = AffectedModel(
        unique_id="model.demo.raw_dump", name="raw_dump", depth=1, uncertain=True
    )
    impact = ChangeImpact(
        change=change,
        source=SourceRef(source_name="app", table_name="customers"),
        models=(model,),
        tests=(),
        exposures=(),
        possible_rename=True,
    )

    assert format_severity(impact) == (
        "  severity: breaking (uncertain, possible rename)"
    )


def impact(kind: ChangeKind, column: str | None = None) -> ChangeImpact:
    """An impact with no affected models: DROP_TABLE is breaking, ADD_COLUMN safe."""
    return ChangeImpact(
        change=SchemaChange(
            kind=kind, table="customers", column=column, source_file="m.py", line=1
        ),
        source=SourceRef(source_name="app", table_name="customers"),
        models=(),
        tests=(),
        exposures=(),
    )


EMPTY = ImpactReport(impacts=(), unmapped=(), not_analyzed=())
MIXED = ImpactReport(
    impacts=(
        impact(ChangeKind.DROP_TABLE),
        impact(ChangeKind.ADD_COLUMN, "email"),
        impact(ChangeKind.ADD_COLUMN, "phone"),
    ),
    unmapped=(
        SchemaChange(
            kind=ChangeKind.DROP_TABLE, table="audit", source_file="m.py", line=2
        ),
    ),
    not_analyzed=(
        NotAnalyzed(reason="BEGIN not checked", source_file="m.sql", line=1),
    ),
)


def test_summary_empty():
    assert format_summary(EMPTY) == (
        "worst: safe · 0 breaking, 0 risky, 0 safe · 0 unmapped · 0 not analyzed"
    )


def test_summary_counts():
    assert format_summary(MIXED) == (
        "worst: breaking · 1 breaking, 0 risky, 2 safe · 1 unmapped · 1 not analyzed"
    )


@pytest.mark.parametrize("report", [EMPTY, MIXED], ids=["empty", "mixed"])
def test_report_starts_with_summary(report: ImpactReport):
    assert format_report(report)[0] == format_summary(report)


def test_empty_report_still_says_no_changes():
    assert format_report(EMPTY) == [format_summary(EMPTY), "", "No changes found."]
