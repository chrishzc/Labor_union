"""
File: client_beclass_import.py
Description: 定義 Client BeClass temporary workbook 的 strict Preview 與 Apply HTTP views。
"""

from pydantic import BaseModel, ConfigDict, Field


class ClientBeClassWorkbookRowIssueView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_row: int = Field(ge=1)
    query_no: str | None = Field(default=None, max_length=100)
    fields: list[str]
    issue_codes: list[str]


class ClientBeClassPairingSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_row: int = Field(ge=2)
    case_no: str = Field(min_length=1, max_length=50)


class ClientBeClassManualBindingView(ClientBeClassPairingSelection):
    query_no: str = Field(min_length=1, max_length=100)


class ClientBeClassManualRowView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_row: int
    query_no: str
    name: str
    masked_phone: str
    city: str | None
    submitted_at: str | None
    case_nos: list[str]


class ClientBeClassCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_no: str
    client_id: int
    name: str
    masked_phone: str
    city: str | None
    created_at: str | None
    start_date: str | None


class ClientBeClassWorkbookPreviewView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    sheet_identity: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    create_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    existing_conflict_count: int = Field(ge=0)
    existing_source_count: int = Field(ge=0)
    preview_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_issues: list[ClientBeClassWorkbookRowIssueView] = Field(default_factory=list)
    manual_rows: list[ClientBeClassManualRowView] = Field(default_factory=list)
    candidates: list[ClientBeClassCandidateView] = Field(default_factory=list)


class ClientBeClassWorkbookReceiptView(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_row_count: int = Field(ge=0)
    created_count: int = Field(ge=0)
    exact_replay_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    existing_conflict_count: int = Field(ge=0)
    existing_source_count: int = Field(ge=0)
    replayed_workbook: bool
    row_issues: list[ClientBeClassWorkbookRowIssueView] | None = None
    manual_bindings: list[ClientBeClassManualBindingView] = Field(default_factory=list)
