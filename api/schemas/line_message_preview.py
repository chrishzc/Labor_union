"""Closed display-only LINE preview contracts; provider actions cannot cross this boundary."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class PreviewDescriptorView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    template_id: str | None
    name: str
    format: Literal["text", "flex"]
    requires_case: bool
    requires_staff: bool
    builtin: bool
    allows_draft: bool


class PreviewOptionView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str


class PreviewOptionPageView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[PreviewOptionView]
    next_cursor: str | None


class RenderPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=191)
    content: str | None = Field(default=None, max_length=5000)
    data_source: Literal["record", "sample"] = "record"
    case_no: str | None = Field(default=None, min_length=1, max_length=191)
    staff_id: int | None = Field(default=None, gt=0)


class PreviewNodeView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["text", "box", "button", "separator"]
    text: str
    bold: bool
    size: str
    layout: Literal["horizontal", "vertical"]
    primary: bool
    action_description: str
    children: list["PreviewNodeView"]


class RenderPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ready", "needs_subject", "unavailable"]
    note: str
    format: Literal["text", "flex"]
    text: str
    bubbles: list[PreviewNodeView]
    facts: list[PreviewOptionView]
