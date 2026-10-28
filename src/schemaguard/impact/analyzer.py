from pydantic import BaseModel, ConfigDict, computed_field

from schemaguard.config import Config, SourceRef
from schemaguard.migrations import NotAnalyzed, SchemaChange


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
