"""Retired direct schedule-generation writers retained as Gone routes."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field


router = APIRouter(
    prefix="/api/v1/assignment-schedules",
    tags=["Multi-caregiver schedules"],
)


class AssignmentScheduleDayAdjustment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_work_day: bool = Field(...)
    is_double_pay: bool = Field(...)
    notes: str | None = Field(default=None, max_length=255)


@router.post("/{assignment_id}/generate")
def generate_assignment_schedule(
    assignment_id: int = Path(..., ge=1),
) -> Any:
    del assignment_id
    _raise_retired()


@router.put("/{assignment_id}/days/{work_date}")
def adjust_assignment_schedule(
    adjustment: AssignmentScheduleDayAdjustment,
    assignment_id: int = Path(..., ge=1),
    work_date: date = Path(...),
) -> Any:
    del adjustment, assignment_id, work_date
    _raise_retired()


def _raise_retired() -> None:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_assignment_schedule_writer_retired",
            "message": "Use an authoritative Scheduling Preview and Apply API.",
            "replacement": "/api/v1/orders/{case_no}/assignment-plan/preview",
        },
    )
