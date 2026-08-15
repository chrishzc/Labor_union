"""
File: hcm_resubmission_workbook.py
Description: 從完整 HCM 修正版工作簿建立單一既有警示的受驗證 owner command。
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Callable, Mapping, Protocol

import pandas as pd

from domains.case_import.client_import_validation import validate_hcm_row
from subsystems.case_import.hcm_resubmission_source import hcm_resubmission_target_values
from subsystems.case_import.hcm_resubmission_workflow import (
    ApplyHcmResubmission,
    HcmResubmissionPreview,
    HcmResubmissionReceipt,
    HcmResubmissionSource,
    HcmResubmissionWorkflow,
    hcm_resubmission_source_event_identity,
)


class HcmWorkbookFrameLoader(Protocol):
    def load_frame(self, source_path: str) -> pd.DataFrame | None: ...


@dataclass(frozen=True, slots=True)
class HcmResubmissionApplyRequest:
    occurrence_identity: str
    expected_occurrence_version: int
    expected_root_fingerprint: str
    preview_fingerprint: str
    idempotency_key: str
    actor: str
    reason: str
    correlation_id: str


class HcmResubmissionWorkbookService:
    """Keeps raw workbook input inside the HCM owner boundary.

    The warning center supplies only an occurrence identity and navigation.  A
    complete re-submitted workbook is revalidated here, and exactly one row
    matching the already-bound canonical case can become a source command.
    """

    def __init__(
        self,
        workflow: HcmResubmissionWorkflow,
        frame_loader: HcmWorkbookFrameLoader,
        holiday_dates: Callable[[], set],
        row_normalizer: Callable[[object], Mapping[str, object]],
    ) -> None:
        self._workflow = workflow
        self._frame_loader = frame_loader
        self._holiday_dates = holiday_dates
        self._row_normalizer = row_normalizer

    def preview(self, source_path: str, occurrence_identity: str) -> HcmResubmissionPreview:
        return self._workflow.preview(
            occurrence_identity,
            self._source(source_path, occurrence_identity),
        )

    def apply(self, source_path: str, request: HcmResubmissionApplyRequest) -> HcmResubmissionReceipt:
        return self._workflow.apply(
            ApplyHcmResubmission(
                request.occurrence_identity,
                self._source(source_path, request.occurrence_identity),
                request.expected_occurrence_version,
                request.expected_root_fingerprint,
                request.preview_fingerprint,
                request.idempotency_key,
                request.actor,
                request.reason,
                request.correlation_id,
            )
        )

    def _source(self, source_path: str, occurrence_identity: str) -> HcmResubmissionSource:
        facts = self._workflow.facts(occurrence_identity)
        frame = self._frame_loader.load_frame(source_path)
        if frame is None:
            raise ValueError("hcm_resubmission_workbook_sheet_contract_not_unique")
        matches = [row.to_dict() for _, row in frame.iterrows() if self._row_normalizer(row).get("case_no") == facts.case_no]
        if len(matches) != 1:
            raise ValueError("hcm_resubmission_case_row_not_unique")
        raw_row = matches[0]
        validation_errors = validate_hcm_row(raw_row)
        if validation_errors:
            raise ValueError("hcm_resubmission_workbook_still_invalid")
        normalized = self._row_normalizer(raw_row)
        field_path = facts.field_path
        return HcmResubmissionSource(
            raw_row,
            validation_errors,
            hcm_resubmission_target_values(
                field_path,
                normalized,
                holiday_dates=self._holiday_dates(),
            ),
            hcm_resubmission_source_event_identity(occurrence_identity, _digest(source_path)),
            _digest(source_path),
        )


def _digest(source_path: str) -> str:
    return sha256(Path(source_path).read_bytes()).hexdigest()


__all__ = ["HcmResubmissionApplyRequest", "HcmResubmissionWorkbookService"]
