from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ChangeKind(StrEnum):
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    RENAME_COLUMN = "rename_column"
    ALTER_TYPE = "alter_type"
    ALTER_NULLABILITY = "alter_nullability"
    DROP_TABLE = "drop_table"
    RENAME_TABLE = "rename_table"


class SchemaChange(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: ChangeKind
    table: str
    source_file: str
    line: int
    column: str | None = None
    new_name: str | None = None
    new_type: str | None = None
    old_type: str | None = None
    nullable: bool | None = None


class NotAnalyzed(BaseModel):
    model_config = ConfigDict(frozen=True)
    reason: str
    source_file: str
    line: int


class ChangeSet(BaseModel):
    model_config = ConfigDict(frozen=True)
    changes: tuple[SchemaChange, ...]
    not_analyzed: tuple[NotAnalyzed, ...]
