from enum import StrEnum

from pydantic import BaseModel, ConfigDict, computed_field

from schemaguard.config import Config, SourceRef
from schemaguard.dbt.columns import ColumnUsage
from schemaguard.dbt.lineage import downstream, split
from schemaguard.dbt.manifest import Manifest
from schemaguard.migrations import ChangeKind, NotAnalyzed, SchemaChange


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

    if change.kind in (ChangeKind.DROP_TABLE, ChangeKind.RENAME_TABLE):
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
