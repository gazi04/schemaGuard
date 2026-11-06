from schemaguard.config import SourceRef
from schemaguard.impact import AffectedModel, ChangeImpact, ImpactReport
from schemaguard.migrations import ChangeKind, NotAnalyzed, SchemaChange
from schemaguard.report import MARKER, format_markdown
from schemaguard.report.markdown import md

EMPTY = ImpactReport(impacts=(), unmapped=(), not_analyzed=())

HEADER = (
    "| Severity | Change | Location | Source | Affected models | Tests | Exposures |"
)

DROP = SchemaChange(
    kind=ChangeKind.DROP_COLUMN,
    table="customers",
    column="email",
    source_file="m.py",
    line=3,
)


def impact(
    change: SchemaChange = DROP,
    models: tuple[AffectedModel, ...] = (),
    tests: tuple[str, ...] = (),
    exposures: tuple[str, ...] = (),
    possible_rename: bool = False,
) -> ChangeImpact:
    return ChangeImpact(
        change=change,
        source=SourceRef(source_name="app", table_name="customers"),
        models=models,
        tests=tests,
        exposures=exposures,
        possible_rename=possible_rename,
    )


def mixed_report() -> ImpactReport:
    """One breaking uncertain impact, one unmapped change, one not_analyzed."""
    models = (
        AffectedModel(
            unique_id="model.demo.raw_dump", name="raw_dump", depth=1, uncertain=True
        ),
        AffectedModel(
            unique_id="model.demo.report", name="report", depth=2, uncertain=False
        ),
    )
    unmapped = SchemaChange(
        kind=ChangeKind.DROP_TABLE, table="audit_log", source_file="m.py", line=5
    )
    skipped = NotAnalyzed(reason="op.execute sa.text(...)", source_file="m.py", line=7)
    return ImpactReport(
        impacts=(
            impact(
                models=models,
                tests=("test.demo.not_null_email",),
                exposures=("dashboard", "kpis"),
            ),
        ),
        unmapped=(unmapped,),
        not_analyzed=(skipped,),
    )


def rows(text: str) -> list[str]:
    """Table rows after the header and separator."""
    lines = text.splitlines()
    start = lines.index(HEADER) + 2
    return [line for line in lines[start:] if line.startswith("|")]


def test_marker_is_first_line():
    assert format_markdown(EMPTY).splitlines()[0] == MARKER
    assert format_markdown(mixed_report()).splitlines()[0] == MARKER


def test_empty_report():
    text = format_markdown(EMPTY)

    assert "## SchemaGuard" in text
    assert (
        "**worst: safe · 0 breaking, 0 risky, 0 safe · 0 unmapped · 0 not analyzed**"
        in text
    )
    assert "No changes found." in text
    assert HEADER not in text
    assert "<details>" not in text


def test_summary_line():
    text = format_markdown(mixed_report())

    assert (
        "**worst: breaking · 1 breaking, 0 risky, 0 safe · 1 unmapped · 1 not analyzed**"
        in text
    )
    assert "No changes found." not in text


def test_impact_row():
    [row] = rows(format_markdown(mixed_report()))

    assert row == (
        "| 🔴 breaking (uncertain) | drop_column customers.email | m.py:3 | app.customers"
        " | raw_dump (hop 1)?, report (hop 2) | 1 | dashboard, kpis |"
    )


def test_impact_without_models():
    report = ImpactReport(impacts=(impact(),), unmapped=(), not_analyzed=())

    [row] = rows(format_markdown(report))

    assert (
        row
        == "| 🟢 safe | drop_column customers.email | m.py:3 | app.customers | - | 0 | - |"
    )


def test_possible_rename_and_detail():
    rename = SchemaChange(
        kind=ChangeKind.RENAME_COLUMN,
        table="customers",
        column="name",
        new_name="full_name",
        source_file="m.py",
        line=4,
    )
    report = ImpactReport(
        impacts=(impact(change=rename, tests=("t",), possible_rename=True),),
        unmapped=(),
        not_analyzed=(),
    )

    [row] = rows(format_markdown(report))

    assert row.startswith(
        "| 🔴 breaking (possible rename) | rename_column customers.name -> full_name |"
    )


def test_unmapped_and_not_analyzed_sections():
    text = format_markdown(mixed_report())

    assert "<summary>1 unmapped (table not in <code>sources</code>)</summary>" in text
    assert "- drop_table audit_log (m.py:5)" in text
    assert "<summary>1 not analyzed</summary>" in text
    assert "- op.execute sa.text(...) (m.py:7)" in text
    assert text.count("<details>") == text.count("</details>") == 2


def test_reason_is_escaped():
    skipped = NotAnalyzed(
        reason="Statement not checked: SELECT a | b FROM t WHERE x < 1\nAND y",
        source_file="m.sql",
        line=1,
    )
    report = ImpactReport(impacts=(), unmapped=(), not_analyzed=(skipped,))

    text = format_markdown(report)

    assert (
        "- Statement not checked: SELECT a \\| b FROM t WHERE x &lt; 1 AND y (m.sql:1)"
        in text
    )


def test_md_filter():
    assert md("a|b") == "a\\|b"
    assert md("<b>") == "&lt;b>"
    assert md("x -> y") == "x -> y"
    assert md("one\r\ntwo") == "one  two"
