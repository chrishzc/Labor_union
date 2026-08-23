"""
File: test_staff_matching_preferences_workflow.py
Description: 驗證 Staff 偏好 aggregate 鎖定、單一 outer UoW 與 strict receipt 契約。
"""

from __future__ import annotations

from contextlib import AbstractContextManager
import pytest
from pydantic import ValidationError

from api.schemas.staff_matching_preferences import StaffPreferenceProfileApplyReceiptView
from domains.scheduling.staff_matching_preferences import (
    PreferenceComparisonOperator,
    PreferenceValueKind,
    StaffPreferenceDefinition,
)
from infrastructure.mysql.staff_matching_preference_repository import (
    MySqlStaffMatchingPreferenceRepository,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.scheduling.staff_matching_preference_workflow import (
    PreferenceApplyRequest,
    StaffMatchingPreferenceWorkflow,
)


def test_profile_missing_row_locks_stable_staff_aggregate_before_profile_read():
    cursor = _Cursor(fetchone_values=[{"id": 7}, None], fetchall_values=[()])
    repository = MySqlStaffMatchingPreferenceRepository(_Connection(cursor))

    repository.lock_profile_aggregate(7)
    version, values = repository.load_profile(7, for_update=True)

    assert version == 0
    assert values == {}
    staff_lock_queries = [
        query
        for query, _params in cursor.executed
        if "FROM staff" in query and "FOR UPDATE" in query
    ]
    assert staff_lock_queries, "missing profile rows must still lock staff aggregate identity"


def test_profile_apply_uses_only_outer_uow_commit_owner():
    repository = _Repository()
    unit_of_work = _UnitOfWork()
    workflow = StaffMatchingPreferenceWorkflow(repository, lambda: unit_of_work)
    proposed = {
        "preferred_service_days": {"minimum": 20, "maximum": 30},
        "daily_service_hours": {"values": [4, 8]},
    }
    preview = workflow.preview_profile(7, proposed)
    request = _request(preview.version, preview.fingerprint, "outer-uow-profile")

    receipt = workflow.apply_profile(7, proposed, request)

    assert receipt["version"] == 1
    assert unit_of_work.commit_count == 1
    assert unit_of_work.rollback_count == 0
    assert repository.commit_calls == 0
    assert repository.rollback_calls == 0


def test_preference_receipt_requires_server_fingerprint_and_idempotency_key():
    valid = {
        "staff_id": 7,
        "version": 1,
        "values": [],
        "preview_fingerprint": "a" * 64,
        "idempotency_key": "profile-key-01",
    }

    receipt = StaffPreferenceProfileApplyReceiptView.model_validate(valid)
    assert receipt.preview_fingerprint == "a" * 64
    assert receipt.idempotency_key == "profile-key-01"

    for missing in ("preview_fingerprint", "idempotency_key"):
        payload = dict(valid)
        payload.pop(missing)
        with pytest.raises(ValidationError):
            StaffPreferenceProfileApplyReceiptView.model_validate(payload)


def test_preference_receipt_rejects_uppercase_or_non_hex_fingerprint():
    payload = {
        "staff_id": 7,
        "version": 1,
        "values": [],
        "preview_fingerprint": "A" * 64,
        "idempotency_key": "profile-key-02",
    }

    with pytest.raises(ValidationError):
        StaffPreferenceProfileApplyReceiptView.model_validate(payload)


class _Cursor:
    def __init__(self, *, fetchone_values=(), fetchall_values=()):
        self.executed = []
        self._fetchone_values = list(fetchone_values)
        self._fetchall_values = list(fetchall_values)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=()):
        self.executed.append((query, params))

    def fetchone(self):
        return self._fetchone_values.pop(0) if self._fetchone_values else None

    def fetchall(self):
        return self._fetchall_values.pop(0) if self._fetchall_values else ()


class _Connection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class _UnitOfWork(AbstractContextManager):
    def __init__(self):
        self.commit_count = 0
        self.rollback_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1


class _Repository:
    def __init__(self):
        self.definitions = {
            "preferred_service_days": (_service_day_definition(), 1),
            "daily_service_hours": (_daily_hours_definition(), 1),
        }
        self.profile_version = 0
        self.profile_values = {}
        self.receipts = {}
        self.commit_calls = 0
        self.rollback_calls = 0
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
        del definition, version, actor

    def save_profile(self, staff_id, values, version, actor):
        del staff_id, actor
        self.profile_version = version
        self.profile_values = {
            key: value.canonical_payload() for key, value in values.items()
        }

    def append_event(self, event):
        del event
        return 1

    def save_receipt(self, receipt):
        self.receipts[receipt.key.value] = {
            "command_fingerprint": receipt.command_fingerprint.value,
            "result": dict(receipt.result),
        }


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
