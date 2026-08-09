"""Typed knowledge source, publication, and cited-answer boundaries."""

from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeCommandBody(BaseModel):
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=191)
    correlation_id: str = Field(min_length=1, max_length=191)
    source_uri: str | None = Field(default=None, max_length=500)
    source_trust_tier: Literal["internal_policy", "government_source", "approved_partner"] | None = None
    title: str | None = Field(default=None, max_length=300)
    content: str | None = None


class KnowledgeReceiptView(BaseModel):
    knowledge_item_id: int
    state: Literal["draft", "reviewed", "published", "retired"]
    version: int
    source_uri: str
    content_digest: str


class KnowledgeCitationView(BaseModel):
    knowledge_item_id: int
    source_uri: str
    content_digest: str
    version: int


class KnowledgeAnswerView(BaseModel):
    answer: str
    citations: list[KnowledgeCitationView]
    authoritative: Literal[False]
