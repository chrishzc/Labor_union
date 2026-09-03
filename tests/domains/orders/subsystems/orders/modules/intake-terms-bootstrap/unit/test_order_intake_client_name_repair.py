from __future__ import annotations

from dataclasses import replace

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.order_intake_client_name_repair import (
    OrderIntakeClientNameRepairApplication,
    OrderIntakeClientNameRepairError,
)
from subsystems.orders.order_intake_terms_bootstrap import OrderIntakeTermsBootstrapFacts


_CASE = "CASE-153"


def test_missing_client_name_can_be_repaired_with_version_fingerprint_and_audit():
    repository = _Repository(client_name=None)
    unit_of_work = _UnitOfWorkFactory()
    application = OrderIntakeClientNameRepairApplication(repository, unit_of_work)

    preview = application.preview(_CASE, "王小明")

    assert preview.lifecycle_version == 7
    assert preview.before_client_name is None
    assert preview.after_client_name == "王小明"
    assert preview.blockers == ()
    assert preview.apply_allowed is True

    receipt = application.apply(
        _CASE,
        "王小明",
        preview.lifecycle_version,
        preview.preview_fingerprint,
        "issue-153:name",
        "orders-operator",
        "補齊缺失姓名",
    )

    assert receipt.lifecycle_version == 7
    assert receipt.client_name == "王小明"
    assert receipt.replayed is False
    assert repository.update_calls == [(_CASE, "王小明")]
    assert repository.case.client_name == "王小明"
    assert unit_of_work.commits == 1
    stored = repository.receipts[("orders_intake_client_name_repair/v1", "issue-153:name")]
    assert stored["actor"] == "orders-operator"
    assert stored["reason"] == "補齊缺失姓名"
    assert stored["preview_fingerprint"] == preview.preview_fingerprint


def test_existing_name_or_non_pending_order_cannot_use_missing_name_repair():
    repository = _Repository(client_name="既有姓名")
    application = OrderIntakeClientNameRepairApplication(repository, _UnitOfWorkFactory())

    preview = application.preview(_CASE, "新姓名")
    assert preview.apply_allowed is False
    assert "order_intake_client_name_already_set" in preview.blockers

    repository.case = replace(
        repository.case,
        client_name=None,
        status=OrderLifecycleStatus.DISCUSSION,
    )
    preview = application.preview(_CASE, "新姓名")
    assert preview.apply_allowed is False
    assert "order_intake_client_name_status_not_eligible" in preview.blockers


def test_client_name_repair_rechecks_lifecycle_version_before_write():
    repository = _Repository(client_name=None)
    application = OrderIntakeClientNameRepairApplication(repository, _UnitOfWorkFactory())
    preview = application.preview(_CASE, "王小明")
    repository.case = replace(repository.case, lifecycle_version=8)

    with pytest.raises(
        OrderIntakeClientNameRepairError,
        match="order_intake_client_name_stale_preview",
    ):
        application.apply(
            _CASE,
            "王小明",
            preview.lifecycle_version,
            preview.preview_fingerprint,
            "issue-153:stale-name",
            "orders-operator",
            "stale",
        )

    assert repository.update_calls == []
    assert repository.for_update_calls == [True]


def test_client_name_repair_idempotent_replay_is_safe():
    repository = _Repository(client_name=None)
    application = OrderIntakeClientNameRepairApplication(repository, _UnitOfWorkFactory())
    preview = application.preview(_CASE, "王小明")
    arguments = (
        _CASE,
        "王小明",
        preview.lifecycle_version,
        preview.preview_fingerprint,
        "issue-153:name-replay",
        "orders-operator",
        "補姓名",
    )

    first = application.apply(*arguments)
    second = application.apply(*arguments)

    assert first.replayed is False
    assert second.replayed is True
    assert repository.update_calls == [(_CASE, "王小明")]


class _Repository:
    def __init__(self, *, client_name):
        self.case = OrderIntakeTermsBootstrapFacts(
            case_no=_CASE,
            status=OrderLifecycleStatus.PENDING_COMPLETION,
            lifecycle_version=7,
            start_date=None,
            service_days=None,
            actual_start_date=None,
            service_data_locked=False,
            client_finance_present=False,
            payroll_present=False,
            scheduling_present=False,
            scheduling_pristine=True,
            client_name=client_name,
        )
        self.receipts = {}
        self.update_calls = []
        self.for_update_calls = []

    def load_case(self, case_no, *, for_update):
        if for_update:
            self.for_update_calls.append(True)
        return self.case if case_no == _CASE else None

    def update_missing_client_name(self, case_no, client_name):
        self.update_calls.append((case_no, client_name))
        assert self.case.client_name is None
        self.case = replace(self.case, client_name=client_name)

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
