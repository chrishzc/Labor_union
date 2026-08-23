"""
File: test_line_registration_atomicity.py
Description: 驗證 LIFF 登記、LINE binding、owner projection 與 intent 共用單一 outer UoW。
"""

from __future__ import annotations

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
    receipt, binding = _application(uow).apply_registration(
        _intent(),
        LineUserId("U-registration"),
        None,
        CorrelationId("line-registration:test"),
    )

    assert receipt.client_id == 17
    assert binding.status.value == "bound"
    assert uow.commits == 1
    assert uow.rollbacks == 0
    assert uow.registration.candidates
    assert uow.customer.bind_calls == [("17", LineUserId("U-registration"), None)]
    assert len(uow.outbox.items) == 1
    assert len(uow.delivery.items) == 1


def test_registration_does_not_require_preexisting_customer_lookup() -> None:
    uow = _RegistrationUow()
    uow.customer.resolve_result = None

    receipt, binding = _application(uow).apply_registration(
        _intent(),
        LineUserId("U-registration"),
        None,
        CorrelationId("line-registration:test-no-preexisting-customer"),
    )

    assert receipt.client_id == 17
    assert binding.status.value == "bound"
    assert uow.commits == 1
    assert uow.customer.bind_calls == [("17", LineUserId("U-registration"), None)]
    assert uow.customer.resolve_calls == 0


def test_registration_rolls_back_when_binding_projection_fails() -> None:
    uow = _RegistrationUow()
    uow.customer.error = RuntimeError("owner_projection_conflict")

    with pytest.raises(RuntimeError, match="owner_projection_conflict"):
        _application(uow).apply_registration(
            _intent(),
            LineUserId("U-registration"),
            None,
            CorrelationId("line-registration:test-failure"),
        )

    assert uow.commits == 0
    assert uow.rollbacks == 1


def _application(uow):
    return LineIdentityApplication(lambda: uow, lambda: NOW)


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
        if exception_type is not None or self.commits == 0:
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
    def get(self, _line_user_id):
        return None

    def bind(self, claim, *_):
        return LineIdentityBindingSnapshot(
            claim.line_user_id,
            LineIdentityBindingStatus.BOUND,
            ExpectedVersion(1),
            claim.subject_type,
            claim.subject_reference,
        )


class _ListRepository:
    def __init__(self) -> None:
        self.items = []

    def append(self, item):
        self.items.append(item)

    def enqueue(self, item):
        self.items.append(item)
        return SimpleNamespace()
