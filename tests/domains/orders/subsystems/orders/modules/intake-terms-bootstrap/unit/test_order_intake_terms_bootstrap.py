from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.order_intake_terms_bootstrap import (
    OrderIntakeTermsBootstrapApplication,
    OrderIntakeTermsBootstrapError,
    OrderIntakeTermsBootstrapFacts,
)


_CASE = "CASE-166"
_START = date(2026, 9, 10)
_DAYS = 30


def test_missing_start_and_service_days_preview_and_apply_only_fill_missing_terms():
    repository = _Repository(start_date=None, service_days=0)
    unit_of_work = _UnitOfWorkFactory()
    application = OrderIntakeTermsBootstrapApplication(repository, unit_of_work)

    preview = application.preview(_CASE, _START, _DAYS)

    assert preview.apply_allowed is True
    assert preview.before_start_date is None
    assert preview.before_service_days == 0
    assert preview.after_start_date == _START
    assert preview.after_service_days == _DAYS
    assert preview.changed_fields == ("start_date", "service_days")

    receipt = application.apply(
        _CASE,
        _START,
        _DAYS,
        preview.lifecycle_version,
        preview.preview_fingerprint,
        "issue-166:create",
        "orders-operator",
        "complete missing intake terms",
    )

    assert receipt.lifecycle_version == 8
    assert receipt.start_date == _START
    assert receipt.service_days == _DAYS
    assert receipt.changed_fields == ("start_date", "service_days")
    assert repository.update_calls == [
        (_CASE, 7, _START, _DAYS, True, True)
    ]
    assert repository.case.status is OrderLifecycleStatus.PENDING_COMPLETION
    assert repository.case.actual_start_date is None
    assert repository.case.service_data_locked is False
    assert repository.for_update_calls == [True, True]
    assert unit_of_work.commits == 1
    stored = repository.receipts[("orders_intake_terms_bootstrap/v1", "issue-166:create")]
    assert stored["actor"] == "orders-operator"
    assert stored["reason"] == "complete missing intake terms"
    assert stored["preview_fingerprint"] == preview.preview_fingerprint


def test_missing_start_only_preserves_existing_service_days():
    repository = _Repository(start_date=None, service_days=21)
    application = OrderIntakeTermsBootstrapApplication(repository, _UnitOfWorkFactory())

    preview = application.preview(_CASE, _START, 21)
    assert preview.changed_fields == ("start_date",)
    application.apply(
        _CASE,
        _START,
        21,
        preview.lifecycle_version,
        preview.preview_fingerprint,
        "issue-166:start",
        "orders-operator",
        "complete start date",
    )

    assert repository.update_calls == [(_CASE, 7, _START, 21, True, False)]
    assert repository.case.service_days == 21


def test_missing_service_days_only_preserves_existing_start_date():
    repository = _Repository(start_date=_START, service_days=None)
    application = OrderIntakeTermsBootstrapApplication(repository, _UnitOfWorkFactory())

    preview = application.preview(_CASE, _START, _DAYS)
    assert preview.changed_fields == ("service_days",)
    application.apply(
        _CASE,
        _START,
        _DAYS,
        preview.lifecycle_version,
        preview.preview_fingerprint,
        "issue-166:days",
        "orders-operator",
        "complete service days",
    )

    assert repository.update_calls == [(_CASE, 7, _START, _DAYS, False, True)]
    assert repository.case.start_date == _START


def test_existing_values_cannot_be_rewritten_through_bootstrap():
    repository = _Repository(start_date=_START, service_days=_DAYS)
    application = OrderIntakeTermsBootstrapApplication(repository, _UnitOfWorkFactory())

    preview = application.preview(_CASE, date(2026, 9, 11), 31)

    assert preview.apply_allowed is False
    assert "order_intake_terms_bootstrap_start_date_already_set" in preview.blockers
    assert "order_intake_terms_bootstrap_service_days_already_set" in preview.blockers
    assert "order_intake_terms_bootstrap_nothing_missing" in preview.blockers
    with pytest.raises(OrderIntakeTermsBootstrapError, match="order_intake_terms_bootstrap_blocked"):
        application.apply(
            _CASE,
            date(2026, 9, 11),
            31,
            preview.lifecycle_version,
            preview.preview_fingerprint,
            "issue-166:rewrite",
            "orders-operator",
            "attempt rewrite",
        )
    assert repository.update_calls == []


@pytest.mark.parametrize(
    ("overrides", "expected_blocker"),
    [
        ({"service_data_locked": True}, "order_intake_terms_bootstrap_service_data_locked"),
        ({"actual_start_date": date(2026, 9, 1)}, "order_intake_terms_bootstrap_actual_start_exists"),
        ({"status": OrderLifecycleStatus.DISCUSSION}, "order_intake_terms_bootstrap_status_not_eligible"),
        ({"client_finance_present": True}, "order_intake_terms_bootstrap_client_finance_exists"),
        ({"payroll_present": True}, "order_intake_terms_bootstrap_payroll_exists"),
        (
            {"scheduling_present": True, "scheduling_pristine": False},
            "order_intake_terms_bootstrap_scheduling_not_pristine",
        ),
    ],
)
def test_existing_service_or_cross_domain_state_is_explicitly_blocked(
    overrides,
    expected_blocker,
):
    repository = _Repository(start_date=None, service_days=None)
    repository.case = replace(repository.case, **overrides)
    application = OrderIntakeTermsBootstrapApplication(repository, _UnitOfWorkFactory())

    preview = application.preview(_CASE, _START, _DAYS)

    assert preview.apply_allowed is False
    assert expected_blocker in preview.blockers
    with pytest.raises(OrderIntakeTermsBootstrapError, match="order_intake_terms_bootstrap_blocked"):
        application.apply(
            _CASE,
            _START,
            _DAYS,
            preview.lifecycle_version,
            preview.preview_fingerprint,
            f"issue-166:{expected_blocker}",
            "orders-operator",
            "blocked completion attempt",
        )
    assert repository.update_calls == []


def test_stale_version_is_rejected_after_locked_recheck():
    repository = _Repository(start_date=None, service_days=None)
    application = OrderIntakeTermsBootstrapApplication(repository, _UnitOfWorkFactory())
    preview = application.preview(_CASE, _START, _DAYS)
    repository.case = replace(repository.case, lifecycle_version=8)

    with pytest.raises(OrderIntakeTermsBootstrapError, match="order_intake_terms_bootstrap_stale_preview"):
        application.apply(
            _CASE,
            _START,
            _DAYS,
            preview.lifecycle_version,
            preview.preview_fingerprint,
            "issue-166:stale-version",
            "orders-operator",
            "stale version",
        )

    assert repository.update_calls == []
    assert repository.for_update_calls == [True]


def test_stale_preview_is_rejected_when_eligibility_facts_change_without_version():
    repository = _Repository(start_date=None, service_days=None)
    application = OrderIntakeTermsBootstrapApplication(repository, _UnitOfWorkFactory())
    preview = application.preview(_CASE, _START, _DAYS)
    repository.case = replace(repository.case, scheduling_present=True, scheduling_pristine=False)

    with pytest.raises(OrderIntakeTermsBootstrapError, match="order_intake_terms_bootstrap_stale_preview"):
        application.apply(
            _CASE,
            _START,
            _DAYS,
            preview.lifecycle_version,
            preview.preview_fingerprint,
            "issue-166:stale-fingerprint",
            "orders-operator",
            "stale fingerprint",
        )
    assert repository.update_calls == []


@pytest.mark.parametrize(
    ("proposed_start_date", "proposed_service_days", "error_code"),
    [
        ("2026-09-10", _DAYS, "order_intake_terms_bootstrap_start_date_invalid"),
        (_START, 0, "order_intake_terms_bootstrap_service_days_invalid"),
        (_START, -1, "order_intake_terms_bootstrap_service_days_invalid"),
    ],
)
def test_invalid_proposed_terms_are_rejected_before_repository_read(
    proposed_start_date,
    proposed_service_days,
    error_code,
):
    repository = _Repository(start_date=None, service_days=None)
    application = OrderIntakeTermsBootstrapApplication(repository, _UnitOfWorkFactory())

    with pytest.raises(OrderIntakeTermsBootstrapError, match=error_code):
        application.preview(_CASE, proposed_start_date, proposed_service_days)
    assert repository.load_calls == []


def test_idempotent_replay_is_safe_and_different_payload_with_same_key_is_rejected():
    repository = _Repository(start_date=None, service_days=None)
    application = OrderIntakeTermsBootstrapApplication(repository, _UnitOfWorkFactory())
    preview = application.preview(_CASE, _START, _DAYS)
    arguments = (
        _CASE,
        _START,
        _DAYS,
        preview.lifecycle_version,
        preview.preview_fingerprint,
        "issue-166:replay",
        "orders-operator",
        "complete intake terms",
    )

    first = application.apply(*arguments)
    second = application.apply(*arguments)

    assert first.replayed is False
    assert second.replayed is True
    assert first.lifecycle_version == second.lifecycle_version == 8
    assert len(repository.update_calls) == 1

    with pytest.raises(
        OrderIntakeTermsBootstrapError,
        match="order_intake_terms_bootstrap_idempotency_key_conflict",
    ):
        application.apply(
            _CASE,
            _START,
            _DAYS + 1,
            preview.lifecycle_version,
            preview.preview_fingerprint,
            "issue-166:replay",
            "orders-operator",
            "complete intake terms",
        )


class _Repository:
    def __init__(self, *, start_date, service_days):
        self.case = OrderIntakeTermsBootstrapFacts(
            case_no=_CASE,
            status=OrderLifecycleStatus.PENDING_COMPLETION,
            lifecycle_version=7,
            start_date=start_date,
            service_days=service_days,
            actual_start_date=None,
            service_data_locked=False,
            client_finance_present=False,
            payroll_present=False,
            scheduling_present=False,
            scheduling_pristine=True,
        )
        self.receipts = {}
        self.load_calls = []
        self.for_update_calls = []
        self.update_calls = []

    def load_case(self, case_no, *, for_update):
        self.load_calls.append((case_no, for_update))
        if for_update:
            self.for_update_calls.append(True)
        return self.case if case_no == _CASE else None

    def update_missing_terms(
        self,
        case_no,
        expected_lifecycle_version,
        start_date,
        service_days,
        *,
        fill_start_date,
        fill_service_days,
    ):
        self.update_calls.append(
            (
                case_no,
                expected_lifecycle_version,
                start_date,
                service_days,
                fill_start_date,
                fill_service_days,
            )
        )
        assert self.case.lifecycle_version == expected_lifecycle_version
        self.case = replace(
            self.case,
            lifecycle_version=expected_lifecycle_version + 1,
            start_date=start_date if fill_start_date else self.case.start_date,
            service_days=service_days if fill_service_days else self.case.service_days,
        )
        return self.case.lifecycle_version

    def load_receipt(self, family, key):
        stored = self.receipts.get((family, key))
        if stored is None:
            return None
        return {
            "request_fingerprint": stored["request_fingerprint"],
            "result_snapshot": stored["result_snapshot"],
        }

    def save_receipt(
        self,
        family,
        key,
        request_fingerprint,
        preview_fingerprint,
        actor,
        reason,
        result,
    ):
        self.receipts[(family, key)] = {
            "request_fingerprint": request_fingerprint,
            "preview_fingerprint": preview_fingerprint,
            "actor": actor,
            "reason": reason,
            "result_snapshot": result,
        }


class _UnitOfWorkFactory:
    def __init__(self):
        self.commits = 0

    def __call__(self):
        return _UnitOfWork(self)


class _UnitOfWork:
    def __init__(self, owner):
        self._owner = owner

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        del exception_type, exception, traceback
        return False

    def commit(self):
        self._owner.commits += 1
