"""
File: test_line_registration_atomicity.py
Description: 驗證 LIFF 登記、LINE binding、owner projection 與 intent 共用單一 outer UoW。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from domains.case_import.provisional_registration import ProvisionalRegistrationIntent
from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from shared_kernel.identities import CorrelationId, ExpectedVersion
from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationReceipt
from subsystems.line.identity_application import LineIdentityApplication
from subsystems.line.identity_contracts import LineIdentityCandidate


NOW = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


def test_registration_commits_roots_projection_and_intents_once() -> None:
    uow = _RegistrationUow()
    receipt, binding = _preview_then_apply(
        _application(uow),
        CorrelationId("line-registration:test"),
    )

    assert receipt.client_id == 17
    assert binding.status.value == "bound"
    assert uow.commits == 1
    assert uow.rollbacks == 0
    assert uow.registration.candidates
    assert uow.customer.bind_calls == [
        ("17", LineUserId("U-registration"), LineUserId("U-registration"))
    ]
    assert len(uow.outbox.items) == 1
    assert len(uow.delivery.items) == 1


def test_registration_does_not_require_preexisting_customer_lookup() -> None:
    uow = _RegistrationUow()
    uow.customer.resolve_result = None

    receipt, binding = _preview_then_apply(
        _application(uow),
        CorrelationId("line-registration:test-no-preexisting-customer"),
    )

    assert receipt.client_id == 17
    assert binding.status.value == "bound"
    assert uow.commits == 1
    assert uow.customer.bind_calls == [
        ("17", LineUserId("U-registration"), LineUserId("U-registration"))
    ]
    assert uow.customer.resolve_calls == 0


def test_registration_rolls_back_when_binding_projection_fails() -> None:
    uow = _RegistrationUow()
    uow.customer.error = RuntimeError("owner_projection_conflict")

    with pytest.raises(RuntimeError, match="owner_projection_conflict"):
        _preview_then_apply(
            _application(uow),
            CorrelationId("line-registration:test-failure"),
        )

    assert uow.commits == 0
    assert uow.rollbacks == 1


def test_registration_apply_rejects_payload_changed_after_preview_before_any_write() -> None:
    uow = _RegistrationUow()
    application = _application(uow)
    line_user_id = LineUserId("U-registration")
    preview = application.preview_registration(_intent(), line_user_id, None)
    changed = replace(_intent(), service_days=30)

    with pytest.raises(RuntimeError, match="registration_preview_stale"):
        application.apply_registration(
            changed,
            line_user_id,
            None,
            preview.expected_binding_version,
            preview.preview_fingerprint,
            CorrelationId("line-registration:stale"),
        )

    assert uow.registration.candidates == []
    assert uow.commits == 0


def _application(uow):
    return LineIdentityApplication(lambda: uow, lambda: NOW)


def _preview_then_apply(application, correlation_id):
    intent = _intent()
    line_user_id = LineUserId("U-registration")
    preview = application.preview_registration(intent, line_user_id, None)
    return application.apply_registration(
        intent,
        line_user_id,
        None,
        preview.expected_binding_version,
        preview.preview_fingerprint,
        correlation_id,
    )


def _intent() -> ProvisionalRegistrationIntent:
    return ProvisionalRegistrationIntent(
        line_user_id="U-registration",
        name="王小美",
        phone="0912-345-678",
        expected_date="2026-10-01",
        service_days=26,
        address="台北市中山區",
        gender=None,
        email=None,
        birth_date=None,
        tel=None,
        ext=None,
        city=None,
        zip_code=None,
        id_number=None,
        liff_config_revision="sandbox",
        survey_details={},
    )


class _RegistrationUow:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.registration = _RegistrationRepository()
        self.customer = _CustomerRepository()
        self.identities = _IdentityRepository()
        self.outbox = _ListRepository()
        self.audit = _ListRepository()
        self.delivery = _ListRepository()
        self.customers = self.customer
        self.delivery_tasks = self.delivery
        self.provisional_registrations = self.registration

    def __enter__(self):
        return self

    def __exit__(self, exception_type, *_):
        if exception_type is not None:
            self.rollbacks += 1
        return False

    def commit(self) -> None:
        self.commits += 1


class _RegistrationRepository:
    def __init__(self) -> None:
        self.candidates = []

    def apply(self, candidate):
        self.candidates.append(candidate)
        return ProvisionalRegistrationReceipt(5, 17, 23, "王小美", False, True)


class _CustomerRepository:
    def __init__(self) -> None:
        self.bind_calls = []
        self.error = None
        self.resolve_result = LineIdentityCandidate(LineBindingSubjectType.CUSTOMER, "17")
        self.resolve_calls = 0

    def resolve_customer(self, _proof):
        self.resolve_calls += 1
        return self.resolve_result

    def bind_customer(self, subject_reference, line_user_id, expected_current_line_user_id):
        if self.error:
            raise self.error
        self.bind_calls.append((subject_reference, line_user_id, expected_current_line_user_id))


class _IdentityRepository:
    def __init__(self) -> None:
        self.current = None

    def get(self, _line_user_id, subject_type=None):
        assert subject_type in {None, LineBindingSubjectType.CUSTOMER}
        return self.current

    def list_by_user(self, _line_user_id):
        return () if self.current is None else (self.current,)

    def bind(self, claim, *_):
        self.current = LineIdentityBindingSnapshot(
            claim.line_user_id,
            LineIdentityBindingStatus.BOUND,
            ExpectedVersion(1),
            claim.subject_type,
            claim.subject_reference,
        )
        return self.current


class _ListRepository:
    def __init__(self) -> None:
        self.items = []

    def append(self, item):
        self.items.append(item)

    def enqueue(self, item):
        self.items.append(item)
        return SimpleNamespace()
