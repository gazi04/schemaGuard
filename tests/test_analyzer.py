from typing import Any

import pytest

from schemaguard.config import SourceRef, load_config
from schemaguard.dbt.columns import ColumnUsage
from schemaguard.impact import AffectedModel
from schemaguard.impact.analyzer import (
    AnalyzerError,
    Match,
    find_ref,
    is_ignored,
    match_first_hop,
    walk_affected,
)
from schemaguard.migrations import ChangeKind, SchemaChange
from tests.helper import make_manifest, node

CONFIG = load_config(
    "sources:\n  customers: ecom.raw_customers\nignore: [alembic_version]\n"
)


def change(kind: ChangeKind, column: str | None = "email") -> SchemaChange:
    return SchemaChange(
        kind=kind, table="customers", source_file="m.py", line=1, column=column
    )


def usage(*columns: str, uncertain: bool = False) -> ColumnUsage:
    return ColumnUsage(columns=frozenset(columns), uncertain=uncertain)


def summary(models: tuple[AffectedModel, ...]) -> list[tuple[str, int, bool]]:
    return [(model.unique_id, model.depth, model.uncertain) for model in models]


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
