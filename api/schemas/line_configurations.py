"""Public HTTP schemas for canonical versioned LINE configuration."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PreviewLineConfigurationRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    definition: dict[str, Any]


class ApplyLineConfigurationRequest(PreviewLineConfigurationRequest):
    reason: str = Field(min_length=1, max_length=1_000)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


__all__ = [
    "ApplyLineConfigurationRequest",
    "PreviewLineConfigurationRequest",
]
