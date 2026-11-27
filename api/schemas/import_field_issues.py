"""Bounded, sanitized current import field issue HTTP contracts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ImportFieldIssueView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["hcm", "client_beclass"]
    owner: Literal["client_profile", "client_beclass", "order_terms"]
    field: str = Field(min_length=1)
    source_field: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    optional_skip_review_identity: str | None = Field(default=None, min_length=1)


class CaseImportFieldIssuesView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_no: str = Field(min_length=1, max_length=50)
    issues: tuple[ImportFieldIssueView, ...]


class ImportFieldIssuePageView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: tuple[CaseImportFieldIssuesView, ...]
    next_page: int | None = Field(default=None, ge=1)
    total: int | None = Field(default=None, ge=0)
