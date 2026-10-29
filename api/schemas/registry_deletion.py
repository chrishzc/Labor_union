"""Closed request/view shapes for the case registry deletion operation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RegistryDeletionApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    expected_client_version: int | None = Field(default=None, ge=0)


class RegistryDeletionPreviewView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    kind: Literal["case"]
    identity: str
    version: int
    client_version: int | None
    blockers: list[str]


class RegistryDeletionReceiptView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    kind: Literal["case"]
    identity: str
    deleted: Literal[True]
    replayed: bool
