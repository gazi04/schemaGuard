from collections import deque

from pydantic import BaseModel, ConfigDict

from schemaguard.dbt.manifest import Manifest


class Downstream(BaseModel):
    model_config = ConfigDict(frozen=True)
    unique_id: str
    depth: int


class Lineage(BaseModel):
    model_config = ConfigDict(frozen=True)
    models: tuple[Downstream, ...]
    tests: tuple[Downstream, ...]
    exposures: tuple[Downstream, ...]


def find_source(manifest: Manifest, source_name: str, table_name: str) -> str | None:
    for source in manifest.sources.values():
        if source.source_name == source_name and source.name == table_name:
            return source.unique_id

    return None


def downstream(manifest: Manifest, start_id: str) -> tuple[Downstream, ...]:
    result: list[Downstream] = []
    seen: set[str] = {start_id}
    queue: deque[tuple[str, int]] = deque([(start_id, 0)])

    while queue:
        current, depth = queue.popleft()

        for child in manifest.child_map.get(current, []):
            if child in seen:
                continue

            seen.add(child)
            result.append(Downstream(unique_id=child, depth=depth + 1))
            queue.append((child, depth + 1))

    return tuple(result)


def split(manifest: Manifest, items: tuple[Downstream, ...]) -> Lineage:
    models: list[Downstream] = []
    tests: list[Downstream] = []
    exposures: list[Downstream] = []

    for item in items:
        node = manifest.nodes.get(item.unique_id)
        if node:
            if node.resource_type == "model":
                models.append(item)
            elif node.resource_type == "test":
                tests.append(item)
        elif item.unique_id in manifest.exposures:
            exposures.append(item)

    return Lineage(models=tuple(models), tests=tuple(tests), exposures=tuple(exposures))
