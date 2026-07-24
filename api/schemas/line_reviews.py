"""Schemas for LINE artificial review decisions."""

from pydantic import BaseModel, Field


class LineReviewDecisionRequest(BaseModel):
    reason: str = Field(default="", max_length=1000)
