"""HTTP schemas for knowledge intake, review, publication, and answers."""

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeIngestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_identity: str = Field(min_length=1, max_length=191)
    source_trust_tier: str = Field(
        pattern="^(internal_policy|government_source|approved_partner)$"
    )
    title: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=100000)
    source_uri: str | None = Field(default=None, max_length=1000)


class KnowledgeTransitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


class KnowledgeQuestionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=2000)


__all__ = ["KnowledgeIngestBody", "KnowledgeQuestionBody", "KnowledgeTransitionBody"]
