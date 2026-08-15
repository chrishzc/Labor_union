"""
File: import_warning_tracking.py
Description: 定義匯入警示顯示、導向、Preview 與 Apply 的嚴格 HTTP 契約。
"""

from typing import Literal

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
    display_message: str = Field(min_length=1, max_length=200)
    navigation_action: Literal[
        "hcm_import_center",
        "historical_order_import_center",
        "client_beclass_import_center",
        "staff_beclass_import_center",
        "finance_import_recovery_center",
    ] | None = None


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


class WarningReferralView(_StrictModel):
    occurrence_identity: str
    expected_version: int = Field(ge=1)
    owning_lane: Literal["hcm"]
    logical_code: str
    field_path: str
    masked_subject: str
    display_message: str = Field(min_length=1, max_length=200)
    navigation_action: Literal["hcm_import_center"]
    action_kind: Literal["owner_preview_apply", "wait_for_counterpart"]
    target_command: Literal["preview_hcm_resubmission"] | None = None


__all__ = [
    "ImportWarningTaskView",
    "WarningReferralView",
    "WarningTransitionBody",
    "WarningTransitionPreviewView",
]
