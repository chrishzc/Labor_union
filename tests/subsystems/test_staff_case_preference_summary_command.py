from __future__ import annotations

from copy import deepcopy

import pytest

from subsystems.staff.case_preference_summary_command import (
    PreferenceTopicDraft,
    StaffCasePreferenceApplyRequest,
    StaffCasePreferenceCommandApplication,
    StaffCasePreferenceSnapshot,
    StaffCasePreferenceStaleError,
    StaffCasePreferenceValidationError,
)


def _snapshot(*, regions=("北區",), transport=("機車",), region_other=None):
    return StaffCasePreferenceSnapshot(
        service_regions=PreferenceTopicDraft(regions, region_other),
        service_periods=PreferenceTopicDraft(("8小時",), None),
        rest_schedule=PreferenceTopicDraft(("週休1日",), None),
        baby_counts=PreferenceTopicDraft(("單胞胎",), None),
        holiday_availability=PreferenceTopicDraft(("端午節",), None),
        transportation=PreferenceTopicDraft(transport, None),
    )


class FakeRepository:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.pending = None
        self.commits = 0
        self.rollbacks = 0

    def begin(self):
        self.pending = deepcopy(self.snapshot)

    def commit(self):
        if self.pending is not None:
            self.snapshot = self.pending
        self.pending = None
        self.commits += 1

    def rollback(self):
        self.pending = None
        self.rollbacks += 1

    def load(self, staff_id, *, lock):
        del lock
        if staff_id != 7:
            return None
        return deepcopy(self.pending if self.pending is not None else self.snapshot)

    def replace(self, staff_id, snapshot):
        assert staff_id == 7
        self.pending = deepcopy(snapshot)


def test_preview_apply_and_replay_observe_same_six_topic_snapshot():
    repository = FakeRepository(_snapshot())
    application = StaffCasePreferenceCommandApplication(repository)
    proposed = _snapshot(
        regions=("苗栗縣", "北區", "苗栗縣"),
        region_other="竹北外圍",
    )

    preview = application.preview(7, proposed)

    assert preview.changed_topics == ("service_regions",)
    assert preview.snapshot.service_regions.values == ("北區", "苗栗縣")
    assert preview.snapshot.service_regions.other_detail == "竹北外圍"

    request = StaffCasePreferenceApplyRequest(
        staff_id=7,
        snapshot=preview.snapshot,
        expected_fingerprint=preview.expected_fingerprint,
        preview_fingerprint=preview.preview_fingerprint,
    )
    receipt = application.apply(request)

    assert receipt.outcome == "applied"
    assert receipt.changed_topics == ("service_regions",)
    assert repository.snapshot == preview.snapshot

    replay = application.apply(request)
    assert replay.outcome == "already_observed"
    assert replay.changed_topics == ()


def test_apply_rejects_stale_snapshot_without_persisting_candidate():
    repository = FakeRepository(_snapshot())
    application = StaffCasePreferenceCommandApplication(repository)
    preview = application.preview(7, _snapshot(regions=("新竹縣",)))
    repository.snapshot = _snapshot(regions=("東區",))

    with pytest.raises(StaffCasePreferenceStaleError, match="stale_snapshot"):
        application.apply(
            StaffCasePreferenceApplyRequest(
                staff_id=7,
                snapshot=preview.snapshot,
                expected_fingerprint=preview.expected_fingerprint,
                preview_fingerprint=preview.preview_fingerprint,
            )
        )

    assert repository.snapshot.service_regions.values == ("東區",)
    assert repository.rollbacks == 1


def test_transportation_other_detail_remains_non_writable():
    repository = FakeRepository(_snapshot())
    application = StaffCasePreferenceCommandApplication(repository)
    invalid = StaffCasePreferenceSnapshot(
        service_regions=PreferenceTopicDraft(("北區",), None),
        service_periods=PreferenceTopicDraft(("8小時",), None),
        rest_schedule=PreferenceTopicDraft(("週休1日",), None),
        baby_counts=PreferenceTopicDraft(("單胞胎",), None),
        holiday_availability=PreferenceTopicDraft(("端午節",), None),
        transportation=PreferenceTopicDraft(("轎車",), "步行"),
    )

    with pytest.raises(
        StaffCasePreferenceValidationError,
        match="transportation_other_source_not_ready",
    ):
        application.preview(7, invalid)
