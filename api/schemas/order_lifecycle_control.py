"""Strict HTTP read models for the Orders lifecycle control projection."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ActualStartReconfirmationControlStateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["not_required", "active", "cleared"]
    required_date: str | None
    current_actual_start_date: str | None
    blockers: list[str]
    can_reconfirm: bool


class OrderLifecycleControlStateView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_no: str = Field(min_length=1, max_length=50)
    lifecycle_version: int = Field(ge=0)
    canonical_status: str = Field(min_length=1)
    actual_start_reconfirmation: ActualStartReconfirmationControlStateView


__all__ = [
    "ActualStartReconfirmationControlStateView",
    "OrderLifecycleControlStateView",
]
