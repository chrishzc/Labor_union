"""Owner-local contract tests for Client profile applicant/reviewer workflows."""

from contextlib import AbstractContextManager

import pytest

from domains.clients.profile import ClientProfileValidationError, validate_changes
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_profile.application import ClientProfileApplication
from subsystems.client_profile.contracts import (
    ClientBindingEvidence,
    ClientProfileRequestConflictError,
    ClientProfileStaleError,
)


class _Uow(AbstractContextManager):
    def __init__(self, repository):
        self.client_profiles = repository
        self.binding = _Binding()
        self.commit_count = 0
        self.rollback_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None:
            self.rollback_count += 1
        return False

    def commit(self):
        self.commit_count += 1


class _Repository:
    def __init__(self):
        self.profile = {
            "client_id": 7, "client_profile_version": 0, "name": "王小明", "gender": "女",
            "phone": "0912345678", "city": "新竹市", "address": "新竹市東區一號",
            "residence_type": "電梯大樓", "delivery_type": "自然產", "baby_info": "初生兒", "notes": "無",
        }
        self.requests = {}
        self.receipts = {}
        self.next_id = 1

    def load_profile(self, client_id, *, for_update=False):
        return dict(self.profile) if client_id == 7 else None

    def load_request(self, request_id, *, for_update=False):
        return dict(self.requests[request_id]) if request_id in self.requests else None

    def list_requests(self, *, status, page, page_size):
        rows = [row for row in self.requests.values() if status is None or row["status"] == status]
        return tuple(rows), len(rows)

    def find_receipt(self, key, *, for_update=False):
        return self.receipts.get(key)

    def create_request(self, **kwargs):
        request_id = self.next_id
        self.next_id += 1
        row = {
            "request_id": request_id, "client_id": kwargs["client_id"], "line_user_id": kwargs["line_user_id"],
            "status": "pending", "request_version": 0, "profile_version": kwargs["expected_version"],
            "before": dict(kwargs["before"]), "requested": dict(kwargs["requested"]), "reason": kwargs["reason"],
        }
        self.requests[request_id] = row
        return row

    def approve_request(self, **kwargs):
        self.profile.update(kwargs["requested"])
        self.profile["client_profile_version"] = kwargs["expected_profile_version"] + 1
        row = self.requests[kwargs["request_id"]]
        row = {**row, "status": "approved_applied", "request_version": row["request_version"] + 1, "profile_version": self.profile["client_profile_version"]}
        self.requests[kwargs["request_id"]] = row
        return row

    def reject_request(self, **kwargs):
        row = self.requests[kwargs["request_id"]]
        row = {**row, "status": "rejected", "request_version": row["request_version"] + 1}
        self.requests[kwargs["request_id"]] = row
        return row

    def save_receipt(self, **kwargs):
        self.receipts[kwargs["idempotency_key"]] = {
            "command_fingerprint": kwargs["command_fingerprint"],
            "preview_fingerprint": kwargs["preview_fingerprint"],
            "result": dict(kwargs["result"]),
        }


def _application(repository):
    return ClientProfileApplication(
        lambda: _Uow(repository),
        city_allowlist={"新竹市"},
    )


class _Binding:
    def read_current(self, identity, *, client_id, lock=False):
        if identity != "line-user-7" or client_id != 7:
            raise RuntimeError("binding")
        return ClientBindingEvidence(identity, client_id, 1, ("customer", "staff"), True, True)


def test_profile_validation_is_closed_and_reuses_injected_city_allowlist():
    assert validate_changes({"name": " 王小美 ", "city": "新竹市"}, city_allowlist={"新竹市"}) == {"city": "新竹市", "name": "王小美"}
    with pytest.raises(ClientProfileValidationError):
        validate_changes({"line_user_id": "other"}, city_allowlist={"新竹市"})
    with pytest.raises(ClientProfileValidationError):
        validate_changes({"phone": "123"}, city_allowlist={"新竹市"})


def test_applicant_preview_is_zero_write_and_apply_creates_pending_request():
    repository = _Repository()
    application = _application(repository)
    preview = application.preview_applicant("line-user-7", 7, {"name": "王小美"}, ExpectedVersion(0))
    assert preview.before == {"name": "王小明"}
    assert repository.requests == {}
    receipt = application.apply_applicant(
        "line-user-7", 7, {"name": "王小美"}, ExpectedVersion(0), "本人資料異動",
        preview.preview_fingerprint, IdempotencyKey("client-profile-key-1"), CorrelationId("corr-1"),
    )
    assert receipt.request.status == "pending"
    assert repository.profile["name"] == "王小明"


def test_approval_applies_owner_root_and_same_key_replays_without_second_write():
    repository = _Repository()
    application = _application(repository)
    preview = application.preview_applicant("line-user-7", 7, {"name": "王小美"}, ExpectedVersion(0))
    application.apply_applicant("line-user-7", 7, {"name": "王小美"}, ExpectedVersion(0), "本人資料異動", preview.preview_fingerprint, IdempotencyKey("client-profile-key-2"), CorrelationId("corr-2"))
    approval = application.preview_approval(1, ExpectedVersion(0))
    actor = ActorContext("admin:9", ("line.customer_service.handle",))
    # The fake records the same receipt shape as the production adapter.
    receipt = application.apply_approval(1, actor, "核准", ExpectedVersion(0), ExpectedVersion(0), approval.preview_fingerprint, IdempotencyKey("approval-key-1"), CorrelationId("corr-3"))
    assert receipt.request.status == "approved_applied"
    assert receipt.readback.values["name"] == "王小美"
    replay = application.apply_approval(1, actor, "核准", ExpectedVersion(0), ExpectedVersion(0), approval.preview_fingerprint, IdempotencyKey("approval-key-1"), CorrelationId("corr-3"))
    assert replay.replayed is True
    with pytest.raises(ClientProfileRequestConflictError):
        application.preview_approval(1, ExpectedVersion(0))


def test_approval_preview_requires_current_request_version():
    repository = _Repository()
    application = _application(repository)
    preview = application.preview_applicant("line-user-7", 7, {"name": "王小美"}, ExpectedVersion(0))
    application.apply_applicant("line-user-7", 7, {"name": "王小美"}, ExpectedVersion(0), "本人資料異動", preview.preview_fingerprint, IdempotencyKey("client-profile-key-3"), CorrelationId("corr-4"))
    with pytest.raises(ClientProfileStaleError):
        application.preview_approval(1, ExpectedVersion(1))


def test_rejection_requires_supplied_preview_and_exact_replay():
    repository = _Repository()
    application = _application(repository)
    preview = application.preview_applicant("line-user-7", 7, {"name": "王小美"}, ExpectedVersion(0))
    application.apply_applicant("line-user-7", 7, {"name": "王小美"}, ExpectedVersion(0), "本人資料異動", preview.preview_fingerprint, IdempotencyKey("client-profile-key-4"), CorrelationId("corr-5"))
    rejection = application.preview_rejection(1, ExpectedVersion(0), "資料不完整")
    actor = ActorContext("admin:9", ("line.customer_service.handle",))
    with pytest.raises(ClientProfileRequestConflictError):
        application.reject_request(1, actor, "資料不完整", ExpectedVersion(0), PreviewFingerprint("0" * 64), IdempotencyKey("reject-key-1"), CorrelationId("corr-6"))
    result = application.reject_request(1, actor, "資料不完整", ExpectedVersion(0), rejection.preview_fingerprint, IdempotencyKey("reject-key-1"), CorrelationId("corr-6"))
    assert result.status == "rejected"
    replay = application.reject_request(1, actor, "資料不完整", ExpectedVersion(0), rejection.preview_fingerprint, IdempotencyKey("reject-key-1"), CorrelationId("corr-6"))
    assert replay.status == "rejected"
