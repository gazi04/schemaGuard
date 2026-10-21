from typing import Any

import pytest

from schemaguard.dbt.lineage import (
    Downstream,
    Lineage,
    downstream,
    find_source,
    first_hop,
    split,
)
from schemaguard.dbt.manifest import Manifest


def make_manifest(
    child_map: dict[str, list[str]] | None = None,
    nodes: dict[str, Any] | None = None,
    exposures: dict[str, Any] | None = None,
) -> Manifest:
    return Manifest.model_validate(
        {
            "sources": {
                "source.demo.ecom.raw_customers": {
                    "unique_id": "source.demo.ecom.raw_customers",
                    "source_name": "ecom",
                    "name": "raw_customers",
                    "identifier": "raw_customers",
                },
            },
            "nodes": nodes or {},
            "child_map": child_map or {},
            "exposures": exposures or {},
        }
    )


def node(unique_id: str, resource_type: str) -> dict[str, Any]:
    return {
        "unique_id": unique_id,
        "resource_type": resource_type,
        "name": unique_id.split(".")[-1],
        "depends_on": {},
    }


@pytest.mark.parametrize(
    "call, expected",
    [
        (("ecom", "raw_customers"), "source.demo.ecom.raw_customers"),
        (("ecom", "nope"), None),
        (("other", "raw_customers"), None),
        (("ECOM", "raw_customers"), None),
    ],
)
def test_find_source(call: tuple[str, str], expected: str | None):
    manifest = make_manifest()
    assert find_source(manifest, *call) == expected


def test_downstream_chain():
    manifest = make_manifest(
        child_map={
            "source.demo.ecom.raw_customers": ["model.a"],
            "model.a": ["model.b"],
            "model.b": [],
        }
    )

    result = downstream(manifest, "source.demo.ecom.raw_customers")

    assert result == (
        Downstream(unique_id="model.a", depth=1),
        Downstream(unique_id="model.b", depth=2),
    )


def test_downstream_diamond():
    manifest = make_manifest(
        child_map={
            "source.demo.ecom.raw_customers": ["model.a", "model.b"],
            "model.a": ["model.c"],
            "model.b": ["model.c"],
        }
    )
    result = downstream(manifest, "source.demo.ecom.raw_customers")

    assert result == (
        Downstream(unique_id="model.a", depth=1),
        Downstream(unique_id="model.b", depth=1),
        Downstream(unique_id="model.c", depth=2),
    )


def test_downstream_shortest_depth():
    manifest = make_manifest(
        child_map={
            "source.demo.ecom.raw_customers": ["model.a", "model.c"],
            "model.a": ["model.b"],
            "model.b": ["model.c"],
        }
    )
    result = downstream(manifest, "source.demo.ecom.raw_customers")

    assert result == (
        Downstream(unique_id="model.a", depth=1),
        Downstream(unique_id="model.c", depth=1),
        Downstream(unique_id="model.b", depth=2),
    )


def test_downstream_no_children():
    manifest = make_manifest(
        child_map={
            "source.demo.ecom.raw_customers": [],
        }
    )
    result = downstream(manifest, "source.demo.ecom.raw_customers")

    assert result == ()


def test_downstream_missing_key():
    manifest = make_manifest(child_map={"source.demo.ecom.raw_customers": ["model.a"]})
    result = downstream(manifest, "source.demo.ecom.raw_customers")

    assert result == (Downstream(unique_id="model.a", depth=1),)


def test_split_groups_by_type():
    manifest = make_manifest(
        nodes={
            "model.a": node("model.a", "model"),
            "test.t": node("test.t", "test"),
        },
        exposures={
            "exposures.e": {
                "unique_id": "exposures.e",
                "name": "e",
            }
        },
    )

    items = (
        Downstream(unique_id="model.a", depth=1),
        Downstream(unique_id="test.t", depth=2),
        Downstream(unique_id="exposures.e", depth=2),
    )

    result = split(manifest, items)

    assert result.models == (Downstream(unique_id="model.a", depth=1),)
    assert result.tests == (Downstream(unique_id="test.t", depth=2),)
    assert result.exposures == (Downstream(unique_id="exposures.e", depth=2),)


def test_split_skips_unit_tests():
    manifest = make_manifest()
    items = (Downstream(unique_id="unit_test.demo.a.check_totals", depth=2),)
    result = split(manifest, items)

    assert result.models == ()
    assert result.tests == ()
    assert result.exposures == ()


def test_split_skips_other_types():
    manifest = make_manifest(nodes={"seed.s": node("seed.s", "seed")})
    items = (Downstream(unique_id="seed.s", depth=1),)
    result = split(manifest, items)

    assert result.models == ()
    assert result.tests == ()
    assert result.exposures == ()


def test_split_keeps_order():
    manifest = make_manifest(
        nodes={
            "model.a": node("model.a", "model"),
            "model.b": node("model.b", "model"),
            "model.c": node("model.c", "model"),
        },
    )
    items = (
        Downstream(unique_id="model.a", depth=1),
        Downstream(unique_id="model.b", depth=2),
        Downstream(unique_id="model.c", depth=2),
    )
    result = split(manifest, items)

    assert result.models == items


def test_first_hop():
    lineage = Lineage(
        models=(
            Downstream(unique_id="model.a", depth=1),
            Downstream(unique_id="model.b", depth=2),
            Downstream(unique_id="model.c", depth=1),
        ),
        tests=(),
        exposures=(),
    )

    result = first_hop(lineage)

    assert result == (
        Downstream(unique_id="model.a", depth=1),
        Downstream(unique_id="model.c", depth=1),
    )
