from enum import StrEnum

from pydantic import BaseModel, ConfigDict, computed_field

from schemaguard.config import Config, SourceRef
from schemaguard.dbt.columns import ColumnUsage, column_usage
from schemaguard.dbt.lineage import (
    Downstream,
    Lineage,
    downstream,
    find_source,
    first_hop,
    split,
)
from schemaguard.dbt.manifest import Manifest
from schemaguard.migrations import ChangeKind, ChangeSet, NotAnalyzed, SchemaChange

TABLE_LEVEL = frozenset({ChangeKind.DROP_TABLE, ChangeKind.RENAME_TABLE})


class Match(StrEnum):
    NONE = "none"
    CERTAIN = "certain"
    UNCERTAIN = "uncertain"


class AffectedModel(BaseModel):
    model_config = ConfigDict(frozen=True)
    unique_id: str
    name: str
    depth: int
    uncertain: bool


class ChangeImpact(BaseModel):
    model_config = ConfigDict(frozen=True)
    change: SchemaChange
    source: SourceRef
    models: tuple[AffectedModel, ...]
    tests: tuple[str, ...]
    exposures: tuple[str, ...]

    @computed_field
    @property
    def uncertain(self) -> bool:
        return any(m.uncertain for m in self.models)


class ImpactReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    impacts: tuple[ChangeImpact, ...]
    unmapped: tuple[SchemaChange, ...]
    not_analyzed: tuple[NotAnalyzed, ...]


class AnalyzerError(Exception):
    pass


def is_ignored(config: Config, table: str) -> bool:
    return any(name.lower() == table.lower() for name in config.ignore)


def find_ref(config: Config, table: str) -> SourceRef | None:
    for key, ref in config.sources.items():
        if key.lower() == table.lower():
            return ref

    return None


def match_first_hop(change: SchemaChange, usage: ColumnUsage) -> Match:
    if change.kind is ChangeKind.ADD_COLUMN:
        return Match.NONE

    if change.kind in TABLE_LEVEL:
        return Match.CERTAIN

    if change.column is None:
        raise AnalyzerError(
            f"{change.kind} on {change.table} has no column "
            f"({change.source_file}:{change.line})"
        )

    used = {col.lower() for col in usage.columns}
    if change.column.lower() in used:
        return Match.CERTAIN

    if usage.uncertain:
        return Match.UNCERTAIN

    return Match.NONE


def walk_affected(
    manifest: Manifest, first_hop: dict[str, bool]
) -> tuple[AffectedModel, ...]:
    found: dict[str, tuple[int, bool]] = {}

    def merge(uid: str, depth: int, uncertain: bool) -> None:
        if uid not in found:
            found[uid] = (depth, uncertain)
        else:
            old_depth, old_uncertain = found[uid]
            depth = min(old_depth, depth)
            uncertain = old_uncertain and uncertain
            found[uid] = (depth, uncertain)

    for uid, uncertain in first_hop.items():
        merge(uid, 1, uncertain)
        children = split(manifest, downstream(manifest, uid))

        for child in children.models:
            merge(child.unique_id, 1 + child.depth, uncertain)

    result: list[AffectedModel] = []

    for uid, (depth, uncertain) in found.items():
        result.append(
            AffectedModel(
                unique_id=uid,
                name=manifest.nodes[uid].name,
                depth=depth,
                uncertain=uncertain,
            )
        )

    return tuple(sorted(result, key=lambda model: (model.depth, model.unique_id)))


def first_hop_matches(
    manifest: Manifest, lineage: Lineage, identifier: str, change: SchemaChange
) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for model in first_hop(lineage):
        node = manifest.nodes[model.unique_id]
        usage = column_usage(node.compiled_code, identifier)
        match = match_first_hop(change, usage)

        if match is Match.NONE:
            continue

        result[model.unique_id] = match is Match.UNCERTAIN

    return result


def collect_tests_exposures(
    manifest: Manifest,
    lineage: Lineage,
    change: SchemaChange,
    models: tuple[AffectedModel, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    tests: set[str] = set()
    exposures: set[str] = set()

    for item in lineage.tests:
        if item.depth != 1:
            continue

        column = manifest.nodes[item.unique_id].column_name
        if change.kind in TABLE_LEVEL or (
            column is not None
            and change.column is not None
            and column.lower() == change.column.lower()
        ):
            tests.add(item.unique_id)

    for model in models:
        children = tuple(
            Downstream(unique_id=uid, depth=model.depth + 1)
            for uid in manifest.child_map.get(model.unique_id, [])
        )
        attached = split(manifest, children)
        tests.update(test.unique_id for test in attached.tests)
        exposures.update(
            manifest.exposures[exposure.unique_id].name
            for exposure in attached.exposures
        )

    return tuple(sorted(tests)), tuple(sorted(exposures))


def analyze(change_set: ChangeSet, manifest: Manifest, config: Config) -> ImpactReport:
    impacts: list[ChangeImpact] = []
    unmapped: list[SchemaChange] = []

    for change in change_set.changes:
        if is_ignored(config, change.table):
            continue

        ref = find_ref(config, change.table)
        if ref is None:
            unmapped.append(change)
            continue

        source_id = find_source(manifest, ref.source_name, ref.table_name)
        if source_id is None:
            raise AnalyzerError(
                f"source {ref} (mapped from table {change.table}) "
                "is not in the manifest"
            )

        identifier = manifest.sources[source_id].identifier
        lineage = split(manifest, downstream(manifest, source_id))
        models = walk_affected(
            manifest, first_hop_matches(manifest, lineage, identifier, change)
        )
        tests, exposures = collect_tests_exposures(manifest, lineage, change, models)
        impacts.append(
            ChangeImpact(
                change=change,
                source=ref,
                models=models,
                tests=tests,
                exposures=exposures,
            )
        )

    return ImpactReport(
        impacts=tuple(impacts),
        unmapped=tuple(unmapped),
        not_analyzed=change_set.not_analyzed,
    )
