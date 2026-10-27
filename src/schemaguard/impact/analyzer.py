from pydantic import BaseModel

from schemaguard.config import SourceRef
from schemaguard.migrations import NotAnalyzed, SchemaChange


class AffectedModel(BaseModel):
    unique_id: str
    name: str
    depth: int
    uncertain: bool


class ChangeImpact(BaseModel):
    change: SchemaChange
    source: SourceRef
    model: tuple[AffectedModel, ...]
    tests: tuple[str, ...]
    exposures: tuple[str, ...]


class ImpactReport(BaseModel):
    impacts: tuple[ChangeImpact, ...]
    unmapped: tuple[SchemaChange, ...]
    not_analyzed: tuple[NotAnalyzed, ...]


class AnalyzerError(Exception):
    pass
