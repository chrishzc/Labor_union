"""
File: historical_operational_baseline.py
Description: 定義歷史案件作業基準 Query、Preview、Apply 與 readback 的嚴格公開模型。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


_Fingerprint = str
_EvidenceMode = Literal[
    "retained",
    "historical_evidence_unavailable_accepted",
]
_StepState = Literal["historical_baseline_completed", "in_progress"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class HistoricalOperationalBaselineStepView(_StrictModel):
    step: StrictInt = Field(ge=1, le=11)
    state: _StepState


class HistoricalOperationalBaselineProvenanceView(_StrictModel):
    source_event_identity: str = Field(min_length=1, max_length=191)
    source_version: StrictInt = Field(ge=0)


class HistoricalOperationalBaselineLineageView(_StrictModel):
    baseline_event_identity: str = Field(min_length=1, max_length=191)
    selected_step: StrictInt = Field(ge=1, le=11)
    resulting_orders_version: StrictInt = Field(ge=0)
    resulting_owner_binding_fingerprint: _Fingerprint = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    step_projection: list[HistoricalOperationalBaselineStepView] = Field(
        min_length=1,
        max_length=11,
    )


class HistoricalOperationalBaselineQueryView(_StrictModel):
    order_identity: str = Field(min_length=1, max_length=191)
    case_no: str = Field(min_length=1, max_length=50)
    historical_provenance: HistoricalOperationalBaselineProvenanceView
    current_orders_version: StrictInt = Field(ge=0)
    baseline_binding_fingerprint: _Fingerprint = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    current_baseline: HistoricalOperationalBaselineLineageView | None
    allowed_steps: list[StrictInt] = Field(min_length=11, max_length=11)
    evidence_modes: list[_EvidenceMode] = Field(min_length=2, max_length=2)


class HistoricalOperationalBaselineIntentBody(_StrictModel):
    order_identity: str = Field(min_length=1, max_length=191)
    selected_step: StrictInt = Field(ge=1, le=11)
    expected_orders_version: StrictInt = Field(ge=0)
    expected_baseline_binding_fingerprint: _Fingerprint = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    evidence_mode: _EvidenceMode
    reason: str = Field(min_length=1, max_length=500)
    evidence_reference: str = Field(min_length=1, max_length=191)
    document_kind: str | None = Field(default=None, min_length=1, max_length=191)
    affected_steps: list[StrictInt] | None = Field(
        default=None,
        min_length=1,
        max_length=11,
    )

    @model_validator(mode="after")
    def validate_evidence_shape(self):
        unavailable = (
            self.evidence_mode == "historical_evidence_unavailable_accepted"
        )
        if unavailable != (self.document_kind is not None):
            raise ValueError("historical_baseline_document_kind_shape_invalid")
        if unavailable != (self.affected_steps is not None):
            raise ValueError("historical_baseline_affected_steps_shape_invalid")
        if self.affected_steps is not None:
            values = list(self.affected_steps)
            if values != sorted(set(values)) or any(
                step < 1 or step > 11 for step in values
            ):
                raise ValueError("historical_baseline_affected_steps_invalid")
        return self


class HistoricalOperationalBaselineApplyBody(
    HistoricalOperationalBaselineIntentBody
):
    preview_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")


class HistoricalOperationalBaselinePreviewView(_StrictModel):
    order_identity: str
    case_no: str
    selected_step: StrictInt = Field(ge=1, le=11)
    expected_orders_version: StrictInt = Field(ge=0)
    expected_baseline_binding_fingerprint: _Fingerprint = Field(
        pattern=r"^[0-9a-f]{64}$"
    )
    candidate_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    preview_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_mode: _EvidenceMode
    prior_baseline_event_identity: str | None
    step_projection: list[HistoricalOperationalBaselineStepView] = Field(
        min_length=1,
        max_length=11,
    )


class HistoricalOperationalBaselineReceiptSnapshotView(_StrictModel):
    baseline_event_identity: str
    receipt_identity: str
    selected_step: StrictInt = Field(ge=1, le=11)
    resulting_orders_version: StrictInt = Field(ge=0)
    preview_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    command_fingerprint: _Fingerprint = Field(pattern=r"^[0-9a-f]{64}$")
    replayed: bool


class HistoricalOperationalBaselineApplyView(_StrictModel):
    order_identity: str
    case_no: str
    receipt: HistoricalOperationalBaselineReceiptSnapshotView
    readback: HistoricalOperationalBaselineQueryView


__all__ = [
    "HistoricalOperationalBaselineApplyBody",
    "HistoricalOperationalBaselineApplyView",
    "HistoricalOperationalBaselineIntentBody",
    "HistoricalOperationalBaselinePreviewView",
    "HistoricalOperationalBaselineQueryView",
]
