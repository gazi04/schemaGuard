from typing import Any

import pytest

from schemaguard.config import SourceRef, load_config
from schemaguard.dbt.columns import ColumnUsage
from schemaguard.dbt.lineage import Lineage, downstream, split
from schemaguard.dbt.manifest import Manifest
from schemaguard.impact import ChangeImpact, Severity
from schemaguard.impact.analyzer import (
    AnalyzerError,
    Match,
    analyze,
    collect_tests_exposures,
    find_ref,
    first_hop_matches,
    is_ignored,
    match_first_hop,
    walk_affected,
)
from schemaguard.migrations import ChangeKind, ChangeSet, NotAnalyzed, SchemaChange
from tests.helper import make_manifest, node, summary

SOURCE = "source.demo.ecom.raw_customers"

CONFIG = load_config(
    "sources:\n  customers: ecom.raw_customers\nignore: [alembic_version]\n"
)


def change(
    kind: ChangeKind, column: str | None = "email", table: str = "customers"
) -> SchemaChange:
    return SchemaChange(
        kind=kind, table=table, source_file="m.py", line=1, column=column
    )


def usage(*columns: str, uncertain: bool = False) -> ColumnUsage:
    return ColumnUsage(columns=frozenset(columns), uncertain=uncertain)


@pytest.mark.parametrize(
    "table, expected",
    [
        ("customers", SourceRef(source_name="ecom", table_name="raw_customers")),
        ("Customers", SourceRef(source_name="ecom", table_name="raw_customers")),
        ("orders", None),
    ],
)
def test_find_ref(table: str, expected: SourceRef | None):
    assert find_ref(CONFIG, table) == expected


@pytest.mark.parametrize(
    "table, expected",
    [
        ("alembic_version", True),
        ("Alembic_Version", True),
        ("customers", False),
    ],
)
def test_is_ignored(table: str, expected: bool):
    assert is_ignored(CONFIG, table) is expected


def test_find_ref_mixed_case_key():
    config = load_config("sources:\n  Customers: ecom.raw_customers\n")

    assert find_ref(config, "customers") == SourceRef(
        source_name="ecom", table_name="raw_customers"
    )


@pytest.mark.parametrize(
    "schema_change, column_usage, expected",
    [
        (change(ChangeKind.DROP_COLUMN), usage("email", "id"), Match.CERTAIN),
        (change(ChangeKind.DROP_COLUMN), usage("id"), Match.NONE),
        (change(ChangeKind.DROP_COLUMN), usage(uncertain=True), Match.UNCERTAIN),
        (change(ChangeKind.DROP_COLUMN), usage("email", uncertain=True), Match.CERTAIN),
        (
            change(ChangeKind.DROP_COLUMN, "Email"),
            usage("email", uncertain=True),
            Match.CERTAIN,
        ),
        (change(ChangeKind.DROP_TABLE, None), usage(), Match.CERTAIN),
        (change(ChangeKind.RENAME_TABLE, None), usage(), Match.CERTAIN),
        (change(ChangeKind.ADD_COLUMN), usage("email"), Match.NONE),
        (change(ChangeKind.RENAME_COLUMN), usage("email"), Match.CERTAIN),
        (change(ChangeKind.ALTER_TYPE), usage("email"), Match.CERTAIN),
        (change(ChangeKind.ALTER_NULLABILITY), usage("email"), Match.CERTAIN),
    ],
)
def test_match_first_hop(
    schema_change: SchemaChange, column_usage: ColumnUsage, expected: Match
):
    assert match_first_hop(schema_change, column_usage) is expected


def test_match_first_hop_without_column():
    with pytest.raises(
        AnalyzerError, match=r"drop_column on customers has no column \(m.py:1\)"
    ):
        match_first_hop(change(ChangeKind.DROP_COLUMN, None), usage())


def models(*ids: str) -> dict[str, Any]:
    return {uid: node(uid, "model") for uid in ids}


def compiled(uid: str, sql: str) -> dict[str, Any]:
    return {**node(uid, "model"), "compiled_code": sql}


def source_test(uid: str, column: str | None = None) -> dict[str, Any]:
    if column is None:
        return node(uid, "test")

    return {**node(uid, "test"), "column_name": column}


def first_hop_manifest() -> Manifest:
    return make_manifest(
        child_map={
            SOURCE: ["model.uses", "model.unused", "model.star", "model.uncompiled"]
        },
        nodes={
            "model.uses": compiled("model.uses", "select email from raw_customers"),
            "model.unused": compiled("model.unused", "select id from raw_customers"),
            "model.star": compiled("model.star", "select * from raw_customers"),
            "model.uncompiled": node("model.uncompiled", "model"),
        },
    )


def attached_manifest() -> Manifest:
    return make_manifest(
        child_map={
            SOURCE: ["model.a", "test.src_email", "test.src_id", "test.src_table"],
            "model.a": ["test.a_id", "exposure.e"],
        },
        nodes={
            **models("model.a"),
            "test.src_email": source_test("test.src_email", "Email"),
            "test.src_id": source_test("test.src_id", "id"),
            "test.src_table": source_test("test.src_table"),
            "test.a_id": source_test("test.a_id", "id"),
        },
        exposures={"exposure.e": {"unique_id": "exposure.e", "name": "e"}},
    )


def source_test_manifest() -> Manifest:
    # No model reads email; only a source test does.
    return make_manifest(
        child_map={SOURCE: ["model.ids", "test.src_email"]},
        nodes={
            "model.ids": compiled("model.ids", "select id from raw_customers"),
            "test.src_email": source_test("test.src_email", "Email"),
        },
    )


def source_lineage(manifest: Manifest) -> Lineage:
    return split(manifest, downstream(manifest, SOURCE))


def test_walk_affected_chain():
    manifest = make_manifest(
        child_map={"model.a": ["model.b"], "model.b": ["model.c"]},
        nodes=models("model.a", "model.b", "model.c"),
    )

    result = walk_affected(manifest, {"model.a": False})

    assert summary(result) == [
        ("model.a", 1, False),
        ("model.b", 2, False),
        ("model.c", 3, False),
    ]
    assert [m.name for m in result] == ["a", "b", "c"]


def test_walk_affected_diamond_certain_wins():
    manifest = make_manifest(
        child_map={"model.a": ["model.c"], "model.b": ["model.c"]},
        nodes=models("model.a", "model.b", "model.c"),
    )

    result = walk_affected(manifest, {"model.a": False, "model.b": True})

    assert summary(result) == [
        ("model.a", 1, False),
        ("model.b", 1, True),
        ("model.c", 2, False),
    ]


def test_walk_affected_uncertainty_passes_down():
    manifest = make_manifest(
        child_map={"model.a": ["model.b"]},
        nodes=models("model.a", "model.b"),
    )

    result = walk_affected(manifest, {"model.a": True})

    assert summary(result) == [("model.a", 1, True), ("model.b", 2, True)]


def test_walk_affected_skips_unaffected_first_hop():
    manifest = make_manifest(
        child_map={"model.a": ["model.x"], "model.b": ["model.y"]},
        nodes=models("model.a", "model.b", "model.x", "model.y"),
    )

    result = walk_affected(manifest, {"model.a": False})

    assert summary(result) == [("model.a", 1, False), ("model.x", 2, False)]


def test_walk_affected_unaffected_first_hop_under_affected():
    # b reads the source too, but does not use the changed column
    manifest = make_manifest(
        child_map={
            "source.demo.ecom.raw_customers": ["model.a", "model.b"],
            "model.a": ["model.b"],
        },
        nodes=models("model.a", "model.b"),
    )

    result = walk_affected(manifest, {"model.a": False})

    assert summary(result) == [("model.a", 1, False), ("model.b", 2, False)]


def test_walk_affected_first_hop_under_first_hop_keeps_depth_1():
    manifest = make_manifest(
        child_map={"model.a": ["model.b"]},
        nodes=models("model.a", "model.b"),
    )

    result = walk_affected(manifest, {"model.a": False, "model.b": True})

    assert summary(result) == [("model.a", 1, False), ("model.b", 1, False)]


def test_walk_affected_depth_and_flag_merged_independently():
    # c: depth 2 via uncertain a, certain via b -> m -> c (depth 3)
    manifest = make_manifest(
        child_map={
            "model.a": ["model.c"],
            "model.b": ["model.m"],
            "model.m": ["model.c"],
        },
        nodes=models("model.a", "model.b", "model.m", "model.c"),
    )

    result = walk_affected(manifest, {"model.a": True, "model.b": False})

    assert summary(result) == [
        ("model.a", 1, True),
        ("model.b", 1, False),
        ("model.c", 2, False),
        ("model.m", 2, False),
    ]


def test_walk_affected_leaves_out_tests_and_exposures():
    manifest = make_manifest(
        child_map={"model.a": ["test.t", "exposures.e"]},
        nodes={**models("model.a"), "test.t": node("test.t", "test")},
        exposures={"exposures.e": {"unique_id": "exposures.e", "name": "e"}},
    )

    result = walk_affected(manifest, {"model.a": False})

    assert summary(result) == [("model.a", 1, False)]


def test_walk_affected_empty():
    manifest = make_manifest(
        child_map={"model.a": ["model.b"]},
        nodes=models("model.a", "model.b"),
    )

    assert walk_affected(manifest, {}) == ()


def test_first_hop_matches_column_change():
    manifest = first_hop_manifest()

    result = first_hop_matches(
        manifest,
        source_lineage(manifest),
        "raw_customers",
        change(ChangeKind.DROP_COLUMN),
    )

    assert result == {"model.uses": False, "model.star": True, "model.uncompiled": True}


def test_first_hop_matches_table_change():
    manifest = first_hop_manifest()

    result = first_hop_matches(
        manifest,
        source_lineage(manifest),
        "raw_customers",
        change(ChangeKind.DROP_TABLE, None),
    )

    assert result == {
        "model.uses": False,
        "model.unused": False,
        "model.star": False,
        "model.uncompiled": False,
    }


def test_collect_tests_exposures_column_change():
    manifest = attached_manifest()
    affected = walk_affected(manifest, {"model.a": False})

    result = collect_tests_exposures(
        manifest, source_lineage(manifest), change(ChangeKind.DROP_COLUMN), affected
    )

    assert result == (("test.a_id", "test.src_email"), ("e",))


def test_collect_tests_exposures_table_change():
    manifest = attached_manifest()
    affected = walk_affected(manifest, {"model.a": False})

    result = collect_tests_exposures(
        manifest,
        source_lineage(manifest),
        change(ChangeKind.DROP_TABLE, None),
        affected,
    )

    assert result == (
        ("test.a_id", "test.src_email", "test.src_id", "test.src_table"),
        ("e",),
    )


def test_collect_tests_exposures_no_affected_models():
    manifest = attached_manifest()

    result = collect_tests_exposures(
        manifest, source_lineage(manifest), change(ChangeKind.DROP_COLUMN), ()
    )

    assert result == (("test.src_email",), ())


def test_analyze_routes_changes():
    dropped = change(ChangeKind.DROP_COLUMN)
    ignored = change(ChangeKind.DROP_TABLE, None, table="alembic_version")
    other = change(ChangeKind.DROP_TABLE, None, table="orders")
    skipped = NotAnalyzed(reason="CREATE INDEX not checked", source_file="m.py", line=2)
    change_set = ChangeSet(changes=(dropped, ignored, other), not_analyzed=(skipped,))

    report = analyze(change_set, first_hop_manifest(), CONFIG)

    assert len(report.impacts) == 1
    impact = report.impacts[0]
    assert impact.change == dropped
    assert impact.source == SourceRef(source_name="ecom", table_name="raw_customers")
    assert summary(impact.models) == [
        ("model.star", 1, True),
        ("model.uncompiled", 1, True),
        ("model.uses", 1, False),
    ]
    assert impact.tests == ()
    assert impact.exposures == ()
    assert report.unmapped == (other,)
    assert report.not_analyzed == (skipped,)


def test_analyze_keeps_change_without_affected_models():
    change_set = ChangeSet(changes=(change(ChangeKind.ADD_COLUMN),), not_analyzed=())

    report = analyze(change_set, first_hop_manifest(), CONFIG)

    assert len(report.impacts) == 1
    impact = report.impacts[0]
    assert impact.models == ()
    assert impact.tests == ()
    assert impact.exposures == ()
    assert impact.uncertain is False


def test_analyze_source_missing_from_manifest():
    config = load_config("sources:\n  customers: ecom.nope\n")
    change_set = ChangeSet(changes=(change(ChangeKind.DROP_COLUMN),), not_analyzed=())

    with pytest.raises(
        AnalyzerError, match=r"source ecom\.nope .* not in the manifest"
    ):
        analyze(change_set, first_hop_manifest(), config)


def only_impact(schema_change: SchemaChange, manifest: Manifest) -> ChangeImpact:
    change_set = ChangeSet(changes=(schema_change,), not_analyzed=())
    report = analyze(change_set, manifest, CONFIG)

    assert len(report.impacts) == 1
    return report.impacts[0]


def test_analyze_source_test_only_drop():
    impact = only_impact(change(ChangeKind.DROP_COLUMN), source_test_manifest())

    assert impact.models == ()
    assert impact.tests == ("test.src_email",)
    assert impact.uncertain is False
    assert impact.severity is Severity.BREAKING


def test_analyze_source_test_only_nullable():
    nullable = change(ChangeKind.ALTER_NULLABILITY).model_copy(
        update={"nullable": True}
    )

    impact = only_impact(nullable, source_test_manifest())

    assert impact.tests == ("test.src_email",)
    assert impact.severity is Severity.RISKY


def test_analyze_unused_column_without_test():
    impact = only_impact(
        change(ChangeKind.DROP_COLUMN, "phone"), source_test_manifest()
    )

    assert impact.models == ()
    assert impact.tests == ()
    assert impact.severity is Severity.SAFE
