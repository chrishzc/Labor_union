"""Typed readback views for the bounded LINE M2 feedback/catalog surface."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LineNavigationEntryView(_Closed):
    alias: str
    route_key: str
    tier: str
    public_route: str | None
    postback_identity: str | None
    source_identity: str
    revision: int = Field(ge=1)


class LineNavigationCatalogView(_Closed):
    revision: int = Field(ge=1)
    entries: tuple[LineNavigationEntryView, ...]


class LineNavigationReplyView(_Closed):
    source_response_id: str
    source_event_id: str
    reply_kind: str
    reason_code: str
    source_identity: str
    source_revision: int = Field(ge=1)


class LineNavigationRecentRepliesView(_Closed):
    items: tuple[LineNavigationReplyView, ...]


class LineFeedbackAggregateView(_Closed):
    catalog_revision: int = Field(ge=1)
    window_start: str
    window_end: str
    resolved_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    resolved_rate: float | None = Field(default=None, ge=0, le=1)


class RecordLineFeedbackRequest(_Closed):
    line_id_token: str = Field(default="", max_length=4096)
    development_line_user_id: str = Field(default="", max_length=191)
    source_response_id: str = Field(min_length=1, max_length=191)
    outcome: str = Field(pattern="^(resolved|unresolved)$")
    response_revision: int = Field(ge=1)
    catalog_revision: int = Field(ge=1)
    rule_revision: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)


class LineFeedbackReceiptView(_Closed):
    source_response_id: str
    outcome: str
    command_fingerprint: str
    ticket_id: int | None
    replayed: bool


class LineFeedbackPreviewView(_Closed):
    source_response_id: str
    outcome: str
    command_fingerprint: str
    apply_ready: bool


class LineFeedbackQueryRequest(_Closed):
    line_id_token: str = Field(default="", max_length=4096)
    development_line_user_id: str = Field(default="", max_length=191)
    source_response_id: str = Field(min_length=1, max_length=191)


class LineFeedbackRootView(_Closed):
    actor_id_masked: str
    source_response_id: str
    outcome: str
    binding_version: int = Field(ge=0)
    response_revision: int = Field(ge=1)
    catalog_revision: int = Field(ge=1)
    rule_revision: int | None = Field(default=None, ge=1)
    command_fingerprint: str
    ticket_id: int | None
    idempotency_key: str
    correlation_id: str
    occurred_at: str


class LineFeedbackReadbackView(_Closed):
    root: LineFeedbackRootView
    receipt: LineFeedbackReceiptView
