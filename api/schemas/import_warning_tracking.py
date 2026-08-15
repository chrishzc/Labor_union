"""
File: import_warning_tracking.py
Description: 定義匯入警示追蹤 Query、Preview 與 Apply 的嚴格 HTTP 契約。
"""

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ImportWarningTaskView(_StrictModel):
    occurrence_identity: str
    owning_lane: str
    logical_code: str
    field_path: str
    masked_subject: str
    issue_codes: list[str]
    tracking_status: str
    tracking_version: int = Field(ge=1)
    evidence_reference: str | None = None


class WarningTransitionBody(_StrictModel):
    expected_version: int = Field(ge=1)
    target_status: str = Field(pattern="^(awaiting_external_confirmation|response_recorded|reimport_requested|closed)$")
    reason_code: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=500)
    evidence_reference: str | None = Field(default=None, max_length=191)


class WarningTransitionPreviewView(_StrictModel):
    occurrence_identity: str
    expected_version: int = Field(ge=1)
    resulting_status: str
    resulting_version: int = Field(ge=2)


__all__ = ["ImportWarningTaskView", "WarningTransitionBody", "WarningTransitionPreviewView"]
