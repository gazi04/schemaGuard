from enum import StrEnum
from typing import Annotated, Any, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class FailOn(StrEnum):
    BREAKING = "breaking"
    RISKY = "risky"
    NEVER = "never"


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_name: str
    table_name: str

    @model_validator(mode="before")
    @classmethod
    def parse_string(cls, data: Any) -> Any:
        if not isinstance(data, str):
            return data

        source_name, _, table_name = data.partition(".")

        if not source_name or not table_name:
            raise ValueError("Expected <source>.<table>, e.g. ecom.raw_customers")

        return {"source_name": source_name, "table_name": table_name}

    def __str__(self) -> str:
        return f"{self.source_name}.{self.table_name}"


class Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sources: Annotated[dict[str, SourceRef], Field(min_length=1)]
    manifest: str = "target/manifest.json"
    migrations: str = "alembic/versions"
    ignore: tuple[str, ...] = ()
    fail_on: FailOn = FailOn.BREAKING

    @model_validator(mode="after")
    def check_ignore(self) -> Self:
        both = set(self.ignore) & self.sources.keys()

        if both:
            raise ValueError(
                f"Listed in both ignore and source: {', '.join(sorted(both))}"
            )

        return self


class ConfigError(Exception):
    pass


def load_config(text: str) -> Config:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML: {e}") from e

    if data is None:
        raise ConfigError("Config file is empty")
    if not isinstance(data, dict):
        raise ConfigError("Config must be a mapping of keys to values")

    try:
        return Config.model_validate(data)
    except ValidationError as e:
        raise ConfigError(str(e)) from e
