from enum import StrEnum

from pydantic import BaseModel, ConfigDict, computed_field

from schemaguard.config import Config, SourceRef
from schemaguard.dbt.columns import ColumnUsage
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
