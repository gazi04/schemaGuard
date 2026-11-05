import json
from typing import Any

from schemaguard.config import SourceRef
from schemaguard.impact import AffectedModel, ChangeImpact, ImpactReport
from schemaguard.migrations import ChangeKind, NotAnalyzed, SchemaChange
from schemaguard.report import format_json
from schemaguard.report.json_report import FORMAT_VERSION

EMPTY = ImpactReport(impacts=(), unmapped=(), not_analyzed=())


def mixed_report() -> ImpactReport:
    """One breaking uncertain impact, one unmapped change, one not_analyzed."""
    drop = SchemaChange(
        kind=ChangeKind.DROP_COLUMN,
        table="customers",
        column="email",
        source_file="m.py",
        line=3,
    )
    model = AffectedModel(
        unique_id="model.demo.raw_dump", name="raw_dump", depth=1, uncertain=True
    )
    impact = ChangeImpact(
        change=drop,
        source=SourceRef(source_name="app", table_name="customers"),
        models=(model,),
        tests=("test.demo.not_null_email",),
        exposures=(),
    )
    unmapped = SchemaChange(
        kind=ChangeKind.DROP_TABLE, table="audit_log", source_file="m.py", line=5
    )
    skipped = NotAnalyzed(reason="op.execute sa.text(...)", source_file="m.py", line=7)
    return ImpactReport(
        impacts=(impact,), unmapped=(unmapped,), not_analyzed=(skipped,)
    )


def parse(report: ImpactReport) -> dict[str, Any]:
    return json.loads(format_json(report))


def test_empty_report():
    assert parse(EMPTY) == {
        "version": FORMAT_VERSION,
        "impacts": [],
        "unmapped": [],
        "not_analyzed": [],
        "worst": "safe",
    }


def test_version_is_first_key():
    assert next(iter(parse(EMPTY))) == "version"


def test_computed_fields_included():
    doc = parse(mixed_report())
    impact = doc["impacts"][0]

    assert doc["worst"] == "breaking"
    assert impact["severity"] == "breaking"
    assert impact["uncertain"] is True


def test_impact_fields():
    impact = parse(mixed_report())["impacts"][0]

    assert impact["change"]["kind"] == "drop_column"
    assert impact["change"]["column"] == "email"
    assert impact["source"] == {"source_name": "app", "table_name": "customers"}
    assert impact["models"] == [
        {
            "unique_id": "model.demo.raw_dump",
            "name": "raw_dump",
            "depth": 1,
            "uncertain": True,
        }
    ]
    assert impact["tests"] == ["test.demo.not_null_email"]
    assert impact["possible_rename"] is False


def test_unmapped_and_not_analyzed():
    doc = parse(mixed_report())

    assert [c["table"] for c in doc["unmapped"]] == ["audit_log"]
    assert doc["not_analyzed"][0]["line"] == 7


def test_round_trip():
    """The JSON validates back into the same report; computed fields are ignored."""
    report = mixed_report()
    doc = parse(report)
    del doc["version"]

    assert ImpactReport.model_validate(doc) == report
