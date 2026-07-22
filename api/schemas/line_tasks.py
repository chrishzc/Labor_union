"""Schemas for LINE task administration actions."""

from pydantic import BaseModel, Field


class LineTaskActionRequest(BaseModel):
    reason: str = Field(default="", max_length=500)
