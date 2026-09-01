"""Closed HTTP views for Full Contract Query/Preview."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FullContractPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str
    scope: str
    assignment_id: int | None = Field(default=None, ge=1)
    template_key: str
    template_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    owner_fingerprints: dict[str, str]
    field_values: dict[str, Any | None]
    blockers: list[str]
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    ready_to_print: bool


__all__ = ["FullContractPreviewView"]
