"""Preview/Apply workflow for current-plan national-holiday work agreements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from domains.scheduling.holiday_work_agreement import (
    HolidayWorkAgreementDraft,
    require_exact_plan_participants,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey


class HolidayWorkAgreementError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HolidayWorkAgreementPreview:
    draft: HolidayWorkAgreementDraft
    preview_fingerprint: PreviewFingerprint

    def as_dict(self) -> dict[str, object]:
        return {
            "case_no": self.draft.case_no,
            "plan_id": self.draft.plan_id,
            "expected_version": self.draft.plan_version,
            "holiday_date": self.draft.holiday_date,
            "agreement_status": self.draft.status.value,
            "participant_decisions": [
                {
                    "participant_role": item.participant_role,
                    "segment_id": item.segment_id,
                    "decision": item.decision.value,
                }
                for item in self.draft.participant_decisions
            ],
            "preview_fingerprint": self.preview_fingerprint.value,
            "apply_allowed": self.draft.status.value == "accepted",
        }


class HolidayWorkAgreementWorkflow:
    def __init__(self, unit_of_work_factory: Callable[[], Any], now: Callable[[], datetime]) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._now = now

    def preview(self, draft: HolidayWorkAgreementDraft) -> HolidayWorkAgreementPreview:
        with self._unit_of_work_factory() as unit_of_work:
            self._validate_current(unit_of_work.matching_holiday_work_agreements, draft, lock=False)
        return HolidayWorkAgreementPreview(draft, _fingerprint(draft))

    def apply(
        self,
        draft: HolidayWorkAgreementDraft,
        preview_fingerprint: PreviewFingerprint,
        idempotency_key: IdempotencyKey,
        correlation_id: CorrelationId,
    ) -> Mapping[str, object]:
        del correlation_id
        expected = _fingerprint(draft)
        if preview_fingerprint != expected:
            raise HolidayWorkAgreementError("holiday-work agreement preview is stale")
        with self._unit_of_work_factory() as unit_of_work:
            repository = unit_of_work.matching_holiday_work_agreements
            existing = repository.find_by_idempotency(idempotency_key, expected)
            if existing is not None:
                return _receipt(existing)
            self._validate_current(repository, draft, lock=True)
            stored = repository.append(
                draft,
                idempotency_key=idempotency_key,
                fingerprint=expected,
                occurred_at=self._now(),
            )
            unit_of_work.commit()
        return _receipt(stored)

    @staticmethod
    def _validate_current(repository: Any, draft: HolidayWorkAgreementDraft, *, lock: bool) -> None:
        current = repository.load_current_plan(draft.case_no, draft.plan_id, lock=lock)
        if current is None:
            raise HolidayWorkAgreementError("holiday-work matching plan was not found")
        plan = current["plan"]
        if int(plan["is_active"]) != 1 or str(plan["status"]) != "proposed":
            raise HolidayWorkAgreementError("holiday-work agreement requires an active proposed plan")
        if int(plan["version"]) != draft.plan_version:
            raise HolidayWorkAgreementError("holiday-work agreement plan version is stale")
        if not (
            plan["start_date"] <= draft.holiday_date <= plan["end_date"]
        ):
            raise HolidayWorkAgreementError(
                "holiday-work date is outside the current matching plan"
            )
        if not repository.is_holiday(draft.holiday_date):
            raise HolidayWorkAgreementError("holiday-work date is not a national holiday")
        try:
            require_exact_plan_participants(
                draft,
                tuple(int(item["id"]) for item in current["segments"]),
            )
        except ValueError as error:
            raise HolidayWorkAgreementError(str(error)) from error


def _fingerprint(draft: HolidayWorkAgreementDraft) -> PreviewFingerprint:
    return fingerprint_payload({
        "case_no": draft.case_no,
        "plan_id": draft.plan_id,
        "plan_version": draft.plan_version,
        "holiday_date": draft.holiday_date.isoformat(),
        "actor_id": draft.actor_id,
        "reason": draft.reason,
        "participant_decisions": [
            (item.participant_role, item.segment_id, item.decision.value)
            for item in draft.participant_decisions
        ],
    })


def _receipt(stored: Mapping[str, object]) -> Mapping[str, object]:
    agreement = stored["agreement"]
    return {
        "agreement_id": agreement["id"],
        "plan_id": agreement["plan_id"],
        "holiday_date": agreement["holiday_date"],
        "plan_version": agreement["plan_version"],
        "agreement_status": agreement["agreement_status"],
        "participant_decisions": stored["participants"],
        "replayed": stored["replayed"],
    }


__all__ = [
    "HolidayWorkAgreementError",
    "HolidayWorkAgreementPreview",
    "HolidayWorkAgreementWorkflow",
]
