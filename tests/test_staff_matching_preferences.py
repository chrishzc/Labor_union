"""
File: test_staff_matching_preferences.py
Description: 驗證 Staff 偏好 domain 規則與冪等 fingerprint 邊界。
"""

from __future__ import annotations

from contextlib import AbstractContextManager

import pytest
from pydantic import ValidationError

from api.schemas.staff_matching_preferences import StaffPreferenceProfileInput
from domains.scheduling.staff_matching_preferences import (
    IntegerRangePreference,
    IntegerSetPreference,
    PreferenceComparisonOperator,
    PreferenceValueKind,
    StaffPreferenceDefinition,
    preference_matches,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.scheduling.staff_matching_preference_workflow import (
    PreferenceApplyRequest,
    StaffMatchingPreferenceWorkflow,
)


def test_service_day_range_honours_query_tolerance():
    definition = _service_day_definition()
    value = IntegerRangePreference(20, 30)

    assert preference_matches(definition, value, 32, tolerance=2)
    assert not preference_matches(definition, value, 33, tolerance=2)


def test_daily_hours_are_a_canonical_integer_set():
    definition = _daily_hours_definition()
    value = IntegerSetPreference((4, 8, 24))

    assert preference_matches(definition, value, 8)
    assert not preference_matches(definition, value, 9)
    with pytest.raises(ValueError, match="not_canonical"):
        IntegerSetPreference((8, 4, 8))


def test_filter_semantics_cannot_be_inferred_from_a_label():
    with pytest.raises(ValueError, match="comparison_operator_invalid"):
        StaffPreferenceDefinition(
            "custom_days",
            "我想接的天數",
            PreferenceValueKind.INTEGER_RANGE,
            True,
            "service_days",
            PreferenceComparisonOperator.CONTAINS_INTEGER,
        )


def test_profile_input_rejects_unknown_value_shapes():
    with pytest.raises(ValidationError):
        StaffPreferenceProfileInput.model_validate(
            {
                "values": [
                    {
                        "preference_key": "preferred_service_days",
                        "value": {"kind": "integer_range", "minimum": 10},
                    }
                ]
            }
        )


def test_profile_preview_apply_and_exact_replay():
    repository = _FakeRepository()
    workflow = StaffMatchingPreferenceWorkflow(repository, _FakeUnitOfWork)
    proposed = {
        "preferred_service_days": {"minimum": 20, "maximum": 30},
        "daily_service_hours": {"values": [4, 8]},
    }
    preview = workflow.preview_profile(7, proposed)
    request = _request(preview.version, preview.fingerprint, "profile-key")

    first = workflow.apply_profile(7, proposed, request)
    replay = workflow.apply_profile(7, proposed, request)

    assert first == replay
    assert first["version"] == 1
    assert first["values"]["daily_service_hours"] == {"values": [4, 8]}
    assert len(repository.events) == 1


def test_profile_apply_rejects_stale_preview_without_writes():
    repository = _FakeRepository()
    workflow = StaffMatchingPreferenceWorkflow(repository, _FakeUnitOfWork)
    proposed = {"preferred_service_days": {"minimum": 20, "maximum": 30}}
    preview = workflow.preview_profile(7, proposed)
    repository.profile_version = 1

    with pytest.raises(ValueError, match="stale_version"):
        workflow.apply_profile(7, proposed, _request(0, preview.fingerprint, "stale-key"))

    assert repository.events == []


def test_same_idempotency_key_rejects_different_profile_payload():
    repository = _FakeRepository()
    workflow = StaffMatchingPreferenceWorkflow(repository, _FakeUnitOfWork)
    initial = {"preferred_service_days": {"minimum": 20, "maximum": 30}}
    preview = workflow.preview_profile(7, initial)
    workflow.apply_profile(7, initial, _request(0, preview.fingerprint, "same-key"))
    changed = {"preferred_service_days": {"minimum": 25, "maximum": 35}}

    with pytest.raises(ValueError, match="idempotency_conflict"):
        workflow.apply_profile(7, changed, _request(1, preview.fingerprint, "same-key"))


@pytest.mark.parametrize(
    "changed_request",
    [
        lambda request: PreferenceApplyRequest(
            ExpectedVersion(request.expected_version.value + 1),
            request.preview_fingerprint,
            request.idempotency_key,
            request.actor,
            request.reason,
            request.correlation_id,
        ),
        lambda request: PreferenceApplyRequest(
            request.expected_version,
            PreviewFingerprint("f" * 64),
            request.idempotency_key,
            request.actor,
            request.reason,
            request.correlation_id,
        ),
    ],
)
def test_same_idempotency_key_fingerprint_includes_version_and_preview(
    changed_request,
):
    repository = _FakeRepository()
    workflow = StaffMatchingPreferenceWorkflow(repository, _FakeUnitOfWork)
    proposed = {"preferred_service_days": {"minimum": 20, "maximum": 30}}
    preview = workflow.preview_profile(7, proposed)
    request = _request(preview.version, preview.fingerprint, "fingerprint-key")
    workflow.apply_profile(7, proposed, request)

    with pytest.raises(ValueError, match="idempotency_conflict"):
        workflow.apply_profile(7, proposed, changed_request(request))


def test_definition_display_name_can_change_but_semantics_cannot():
    repository = _FakeRepository()
    workflow = StaffMatchingPreferenceWorkflow(repository, _FakeUnitOfWork)
    renamed = StaffPreferenceDefinition(
        "preferred_service_days",
        "偏好承接天數",
        PreferenceValueKind.INTEGER_RANGE,
        True,
        "service_days",
        PreferenceComparisonOperator.RANGE_WITH_TOLERANCE,
    )
    preview = workflow.preview_definition(renamed)
    request = _request(preview.version, preview.fingerprint, "definition-key")
    result = workflow.apply_definition(
        renamed,
        request,
    )
    assert result == {
        "preference_key": "preferred_service_days",
        "version": 2,
        "preview_fingerprint": preview.fingerprint.value,
        "idempotency_key": "definition-key",
    }

    changed_kind = StaffPreferenceDefinition(
        "preferred_service_days",
        "偏好承接天數",
        PreferenceValueKind.INTEGER_SET,
        True,
        "service_hours_per_day",
        PreferenceComparisonOperator.CONTAINS_INTEGER,
    )
    changed_preview = workflow.preview_definition(changed_kind)
    with pytest.raises(ValueError, match="semantics_immutable"):
        workflow.apply_definition(
            changed_kind,
            _request(changed_preview.version, changed_preview.fingerprint, "semantic-key"),
        )


def _service_day_definition():
    return StaffPreferenceDefinition(
        "preferred_service_days",
        "希望服務天數",
        PreferenceValueKind.INTEGER_RANGE,
        True,
        "service_days",
        PreferenceComparisonOperator.RANGE_WITH_TOLERANCE,
    )


def _daily_hours_definition():
    return StaffPreferenceDefinition(
        "daily_service_hours",
        "每日服務時數",
        PreferenceValueKind.INTEGER_SET,
        True,
        "service_hours_per_day",
        PreferenceComparisonOperator.CONTAINS_INTEGER,
    )


def _request(version, fingerprint, key):
    return PreferenceApplyRequest(
        ExpectedVersion(version),
        PreviewFingerprint(fingerprint.value),
        IdempotencyKey(key),
        ActorContext("operator"),
        "人工維護月嫂偏好",
        CorrelationId(f"correlation-{key}"),
    )


class _FakeUnitOfWork(AbstractContextManager):
    def __enter__(self):
        self.committed = False
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self):
        self.committed = True


class _FakeRepository:
    def __init__(self):
        self.definitions = {
            "preferred_service_days": (_service_day_definition(), 1),
            "daily_service_hours": (_daily_hours_definition(), 1),
        }
        self.profile_version = 0
        self.profile_values = {}
        self.receipts = {}
        self.events = []
        self.profile_locks = []

    def list_definitions(self, *, active_only):
        del active_only
        return tuple(self.definitions.values())

    def load_definition(self, preference_key, *, for_update):
        del for_update
        return self.definitions.get(preference_key)

    def staff_exists(self, staff_id):
        return staff_id == 7

    def lock_profile_aggregate(self, staff_id):
        assert staff_id == 7
        self.profile_locks.append(staff_id)

    def load_profile(self, staff_id, *, for_update):
        del staff_id, for_update
        return self.profile_version, dict(self.profile_values)

    def find_receipt(self, key, *, for_update):
        del for_update
        return self.receipts.get(key.value)

    def save_definition(self, definition, version, actor):
        del actor
        self.definitions[definition.preference_key] = (definition, version)

    def save_profile(self, staff_id, values, version, actor):
        del staff_id, actor
        self.profile_version = version
        self.profile_values = {
            key: value.canonical_payload() for key, value in values.items()
        }

    def append_event(self, event):
        self.events.append(event)
        return len(self.events)

    def save_receipt(self, receipt):
        self.receipts[receipt.key.value] = {
            "command_fingerprint": receipt.command_fingerprint.value,
            "result": dict(receipt.result),
        }
