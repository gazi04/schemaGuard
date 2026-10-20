from pydantic import BaseModel, ConfigDict


class Source(BaseModel):
    model_config = ConfigDict(frozen=True)
    unique_id: str
    source_name: str
    name: str
    identifier: str


class DependsOn(BaseModel):
    model_config = ConfigDict(frozen=True)
    nodes: list[str] = []


class Node(BaseModel):
    model_config = ConfigDict(frozen=True)
    unique_id: str
    resource_type: str
    name: str
    depends_on: DependsOn
    compiled_code: str | None = None
    column_name: str | None = None
    attached_node: str | None = None


class Exposure(BaseModel):
    model_config = ConfigDict(frozen=True)
    unique_id: str
    name: str


class Manifest(BaseModel):
    model_config = ConfigDict(frozen=True)
    sources: dict[str, Source]
    nodes: dict[str, Node]
    child_map: dict[str, list[str]]
    exposures: dict[str, Exposure]
