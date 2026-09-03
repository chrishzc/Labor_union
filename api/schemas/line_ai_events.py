"""Typed LINE AI event and curated QA readback contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LineRouterPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    source_event_id: str = Field(min_length=1, max_length=191)
    score: int | None = Field(default=None, ge=0, le=100)
    development_line_user_id: str = Field(default="", max_length=191)
    apply_manual_fallback: bool = False


class LineRouterPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    source_event_id: str
    source_identity: str
    source_revision: int = Field(ge=1)
    semantic_bucket: str
    confidence: int = Field(ge=0, le=100)
    score_band: str | None = None
    reason_code: str | None = None
    route_key: str | None = None
    options: tuple[str, ...] = ()
    answer_text: str | None = None
    ticket_id: int | None = None
    apply_ready: bool


class LineQaCatalogItemView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: str
    tag: str
    question: str
    aliases: tuple[str, ...] = ()
    answer: str
    enabled: bool
    source_ref: str
    notes: str | None = None


class LineQaCatalogView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_identity: str
    total_count: int = Field(ge=0)
    enabled_count: int = Field(ge=0)
    items: tuple[LineQaCatalogItemView, ...] = ()
