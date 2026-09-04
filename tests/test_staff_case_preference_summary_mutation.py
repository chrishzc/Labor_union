from __future__ import annotations

# CI refresh marker for #209; no production or test semantics change.

import pytest

from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.staff.case_preference_summary_mutation import (
    PreferenceTopicInput,
    StaffCasePreferenceMutationWorkflow,
    StaffCasePreferenceSnapshot,
)
from subsystems.staff.case_preference_summary_query import (
    PreferenceTopicFacts,
    StaffCasePreferenceFacts,
)


class _UnitOfWork:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def commit(self) -> None:
        self.committed = True


class _Repository:
    def __init__(self) -> None:
        self.facts = StaffCasePreferenceFacts(
            531,
            PreferenceTopicFacts(("北區", "其他"), ("偏遠地區",)),
            PreferenceTopicFacts(("8小時",)),
            PreferenceTopicFacts(("週休1日",)),
            PreferenceTopicFacts(("雙胞胎",)),
            PreferenceTopicFacts(("中秋節",)),
            PreferenceTopicFacts(("機車",)),
        )
        self.locked: list[int] = []
        self.saved: StaffCasePreferenceSnapshot | None = None

    def fetch(self, staff_id: int):
        return self.facts if staff_id == 531 else None

    def lock_staff(self, staff_id: int) -> None:
        self.locked.append(staff_id)

    def replace(self, staff_id: int, snapshot: StaffCasePreferenceSnapshot) -> None:
        assert staff_id == 531
        self.saved = snapshot


def _snapshot() -> StaffCasePreferenceSnapshot:
    return StaffCasePreferenceSnapshot(
        service_regions=PreferenceTopicInput(("新竹縣", "北區"), "山區需先確認"),
        service_periods=PreferenceTopicInput(("24小時",)),
        rest_schedule=PreferenceTopicInput(("連續服務",)),
        baby_counts=PreferenceTopicInput(("單胞胎", "雙胞胎")),
        holiday_availability=PreferenceTopicInput(("端午節",)),
        transportation=PreferenceTopicInput(("轎車",), None),
    )


def test_preview_apply_writes_same_six_topics_after_fingerprint_check() -> None:
    repository = _Repository()
    uow = _UnitOfWork()
    workflow = StaffCasePreferenceMutationWorkflow(repository, lambda: uow)

    preview = workflow.preview(531, _snapshot())
    receipt = workflow.apply(531, _snapshot(), preview.fingerprint)

    assert repository.locked == [531]
    assert repository.saved == preview.after
    assert receipt.snapshot == preview.after
    assert receipt.preview_fingerprint == preview.fingerprint
    assert uow.committed is True


def test_apply_rejects_stale_preview_before_write() -> None:
    repository = _Repository()
    workflow = StaffCasePreferenceMutationWorkflow(repository, _UnitOfWork)
    stale = PreviewFingerprint("0" * 64)

    with pytest.raises(ValueError, match="stale_preview"):
        workflow.apply(531, _snapshot(), stale)

    assert repository.saved is None


def test_transportation_other_detail_is_not_writable() -> None:
    repository = _Repository()
    workflow = StaffCasePreferenceMutationWorkflow(repository, _UnitOfWork)
    snapshot = _snapshot()
    invalid = StaffCasePreferenceSnapshot(
        service_regions=snapshot.service_regions,
        service_periods=snapshot.service_periods,
        rest_schedule=snapshot.rest_schedule,
        baby_counts=snapshot.baby_counts,
        holiday_availability=snapshot.holiday_availability,
        transportation=PreferenceTopicInput(("機車",), "自行猜測來源"),
    )

    with pytest.raises(ValueError, match="other_detail_invalid"):
        workflow.preview(531, invalid)
