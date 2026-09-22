from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Acknowledgement(BaseModel):
    ok: bool = True
    message: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None
