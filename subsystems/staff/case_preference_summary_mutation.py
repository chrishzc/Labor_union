"""Preview/apply workflow for the six Staff-owned case-preference relation facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_positive_integer
from subsystems.staff.case_preference_summary_query import (
    StaffCasePreferenceFacts,
    StaffCasePreferenceSummary,
    StaffCasePreferenceSummaryQueryApplication,
)


@dataclass(frozen=True, slots=True)
class PreferenceTopicInput:
    values: tuple[str, ...] = ()
    other_detail: str | None = None


@dataclass(frozen=True, slots=True)
class StaffCasePreferenceSnapshot:
    service_regions: PreferenceTopicInput
    service_periods: PreferenceTopicInput
    rest_schedule: PreferenceTopicInput
    baby_counts: PreferenceTopicInput
    holiday_availability: PreferenceTopicInput
    transportation: PreferenceTopicInput

    def canonical_payload(self) -> dict[str, object]:
        return {
            name: {
                "values": list(getattr(self, name).values),
                "other_detail": getattr(self, name).other_detail,
            }
            for name in _TOPICS
        }


@dataclass(frozen=True, slots=True)
class StaffCasePreferencePreview:
    staff_id: int
    before: StaffCasePreferenceSnapshot
    after: StaffCasePreferenceSnapshot
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class StaffCasePreferenceApplyReceipt:
    staff_id: int
    preview_fingerprint: PreviewFingerprint
    snapshot: StaffCasePreferenceSnapshot


class StaffCasePreferenceMutationRepository(Protocol):
    def fetch(self, staff_id: int) -> StaffCasePreferenceFacts | None: ...
    def lock_staff(self, staff_id: int) -> None: ...
    def replace(self, staff_id: int, snapshot: StaffCasePreferenceSnapshot) -> None: ...


_TOPICS = (
    "service_regions",
    "service_periods",
    "rest_schedule",
    "baby_counts",
    "holiday_availability",
    "transportation",
)


class StaffCasePreferenceMutationWorkflow:
    def __init__(
        self,
        repository: StaffCasePreferenceMutationRepository,
        unit_of_work_factory: Callable[[], Any],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._query = StaffCasePreferenceSummaryQueryApplication(repository)

    def preview(
        self,
        staff_id: int,
        proposed: StaffCasePreferenceSnapshot,
    ) -> StaffCasePreferencePreview:
        require_positive_integer(staff_id, "staff case preference staff_id")
        current = self._query.get(staff_id)
        if current is None:
            raise ValueError("staff_not_found")
        before = _snapshot_from_summary(current)
        after = _normalize_snapshot(proposed)
        return _preview(staff_id, before, after)

    def apply(
        self,
        staff_id: int,
        proposed: StaffCasePreferenceSnapshot,
        preview_fingerprint: PreviewFingerprint,
    ) -> StaffCasePreferenceApplyReceipt:
        require_positive_integer(staff_id, "staff case preference staff_id")
        after = _normalize_snapshot(proposed)
        with self._unit_of_work_factory() as unit_of_work:
            self._repository.lock_staff(staff_id)
            current = self._query.get(staff_id)
            if current is None:
                raise ValueError("staff_not_found")
            preview = _preview(staff_id, _snapshot_from_summary(current), after)
            if preview.fingerprint != preview_fingerprint:
                raise ValueError("stale_preview")
            self._repository.replace(staff_id, after)
            unit_of_work.commit()
        return StaffCasePreferenceApplyReceipt(staff_id, preview_fingerprint, after)


def _preview(
    staff_id: int,
    before: StaffCasePreferenceSnapshot,
    after: StaffCasePreferenceSnapshot,
) -> StaffCasePreferencePreview:
    fingerprint = fingerprint_payload(
        {
            "staff_id": staff_id,
            "before": before.canonical_payload(),
            "after": after.canonical_payload(),
        }
    )
    return StaffCasePreferencePreview(staff_id, before, after, fingerprint)


def _snapshot_from_summary(summary: StaffCasePreferenceSummary) -> StaffCasePreferenceSnapshot:
    return StaffCasePreferenceSnapshot(
        service_regions=_from_summary_topic(summary.service_regions),
        service_periods=_from_summary_topic(summary.service_periods),
        rest_schedule=_from_summary_topic(summary.rest_schedule),
        baby_counts=_from_summary_topic(summary.baby_counts),
        holiday_availability=_from_summary_topic(summary.holiday_availability),
        transportation=PreferenceTopicInput(tuple(summary.transportation.values), None),
    )


def _from_summary_topic(topic) -> PreferenceTopicInput:
    return PreferenceTopicInput(tuple(topic.values), topic.other_detail)


def _normalize_snapshot(snapshot: StaffCasePreferenceSnapshot) -> StaffCasePreferenceSnapshot:
    normalized = {
        name: _normalize_topic(getattr(snapshot, name), allow_other=name != "transportation")
        for name in _TOPICS
    }
    return StaffCasePreferenceSnapshot(**normalized)


def _normalize_topic(topic: PreferenceTopicInput, *, allow_other: bool) -> PreferenceTopicInput:
    values: set[str] = set()
    for raw in topic.values:
        if not isinstance(raw, str):
            raise ValueError("staff_case_preference_value_invalid")
        value = raw.strip()
        if not value or len(value) > 50 or value == "其他":
            raise ValueError("staff_case_preference_value_invalid")
        values.add(value)
    detail = None if topic.other_detail is None else topic.other_detail.strip()
    if detail == "":
        detail = None
    if detail is not None and (not allow_other or len(detail) > 100):
        raise ValueError("staff_case_preference_other_detail_invalid")
    return PreferenceTopicInput(tuple(sorted(values)), detail)


__all__ = [
    "PreferenceTopicInput",
    "StaffCasePreferenceApplyReceipt",
    "StaffCasePreferenceMutationRepository",
    "StaffCasePreferenceMutationWorkflow",
    "StaffCasePreferencePreview",
    "StaffCasePreferenceSnapshot",
]
