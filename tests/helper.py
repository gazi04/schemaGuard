from typing import Any

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
