"""
File: test_hcm_beclass_reconciliation_adapter.py
Description: 驗證 reconciliation adapter 借用 caller UoW，且 standalone wrapper 唯一提交。
"""

from datetime import date, time
from types import SimpleNamespace

import pytest

from domains.orders.terms import OrderTerms, ServiceTimeTerms
from infrastructure.mysql import hcm_beclass_reconciliation_adapter as adapter
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.money import MoneyNTD
from subsystems.case_import.hcm_beclass_reconciliation import (
    CaseImportReconciliationApplication,
    reconcile_hcm_beclass_cooking,
)


class _Connection:
    def __init__(self):
        self.begins = 0
        self.commits = 0
        self.rollbacks = 0

    def begin(self):
        self.begins += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _terms(requires_cooking=None):
    return OrderTerms(
        date(2026, 9, 1),
        5,
        8,
        MoneyNTD(0),
        ServiceTimeTerms(time(9), time(17), 0),
        requires_cooking,
    )


def test_apply_cooking_terms_uses_current_uow_without_hidden_commit(monkeypatch):
    connection = _Connection()
    calls = []

    class Repository:
        def __init__(self, supplied_connection):
            assert supplied_connection is connection

        def load_for_preview(self, _case_no):
            return SimpleNamespace(order=SimpleNamespace(terms=_terms()))

    class Workflow:
        def __init__(self, repository, factory, _clock):
            self.repository = repository
            with pytest.raises(
                RuntimeError, match="hcm_reconciliation_requires_caller_owned_uow"
            ):
                factory()

        def preview(self, _case_no, proposed_terms):
            return SimpleNamespace(
                after=proposed_terms,
                order_version=1,
                scheduling_version=2,
                client_finance_version=3,
                payroll_version=4,
                fingerprint=SimpleNamespace(value="f" * 64),
            )

        def apply(self, _request):
            raise AssertionError("adapter must not own a nested UoW")

        def apply_in_current_uow(self, request):
            calls.append(request)

    monkeypatch.setattr(adapter, "MySqlOrderTermsRepository", Repository)
    monkeypatch.setattr(adapter, "OrderTermsWorkflow", Workflow)

    adapter.MySqlHcmBeClassReconciliationAdapter(connection).apply_cooking_terms(
        "115990823", 9, True
    )

    assert calls[0].case_no == "115990823"
    assert calls[0].proposed_terms.requires_cooking is True
    assert connection.begins == connection.commits == connection.rollbacks == 0


def test_case_import_application_owns_exactly_one_uow(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(
        adapter.MySqlHcmBeClassReconciliationAdapter,
        "reconcile",
        lambda _self, case_no: SimpleNamespace(status="reconciled", case_no=case_no),
    )

    result = CaseImportReconciliationApplication(
        adapter.MySqlHcmBeClassReconciliationAdapter(connection),
        lambda: MySqlUnitOfWork(connection),
    ).reconcile("115990823")

    assert result.status == "reconciled"
    assert connection.begins == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_case_import_application_borrows_existing_uow(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(
        adapter.MySqlHcmBeClassReconciliationAdapter,
        "reconcile",
        lambda _self, case_no: SimpleNamespace(status="reconciled", case_no=case_no),
    )

    result = CaseImportReconciliationApplication(
        adapter.MySqlHcmBeClassReconciliationAdapter(connection),
        lambda: (_ for _ in ()).throw(AssertionError("current path must not create a UoW")),
    ).reconcile_in_current_uow("115990823")

    assert result.status == "reconciled"
    assert connection.begins == connection.commits == connection.rollbacks == 0


def test_case_import_application_rolls_back_reconciliation_failure(monkeypatch):
    connection = _Connection()

    def fail(_self, _case_no):
        raise RuntimeError("orders_apply_failed")

    monkeypatch.setattr(
        adapter.MySqlHcmBeClassReconciliationAdapter,
        "reconcile",
        fail,
    )

    application = CaseImportReconciliationApplication(
        adapter.MySqlHcmBeClassReconciliationAdapter(connection),
        lambda: MySqlUnitOfWork(connection),
    )
    try:
        application.reconcile("115990823")
    except RuntimeError as error:
        assert str(error) == "orders_apply_failed"
    else:
        raise AssertionError("reconciliation failure must escape")

    assert connection.begins == 1
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_stale_owner_version_is_zero_write_and_rolls_back_outer_uow():
    connection = _Connection()

    class StalePort:
        writes = 0

        def reconcile(self, _case_no):
            raise RuntimeError("stale_owner_version")

    port = StalePort()
    application = CaseImportReconciliationApplication(
        port,
        lambda: MySqlUnitOfWork(connection),
    )

    with pytest.raises(RuntimeError, match="stale_owner_version"):
        application.reconcile("115990823")

    assert port.writes == 0
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_reconciliation_replay_does_not_repeat_typed_terms_apply():
    class Port:
        def __init__(self):
            self.requires_cooking = None
            self.apply_count = 0

        def load_pair_facts(self, _case_no):
            return {
                "hcm_count": 1,
                "beclass_count": 1,
                "beclass_id": 9,
                "survey_details": {
                    "月子餐點調理喜好/飲食習慣：": "複合週期題目",
                    "葷食": "Y",
                },
                "requires_cooking": self.requires_cooking,
            }

        def record_cooking_review(self, *_args):
            raise AssertionError("controlled checkbox must not create a review")

        def apply_cooking_terms(self, _case_no, _beclass_id, requires_cooking):
            self.apply_count += 1
            self.requires_cooking = requires_cooking

    port = Port()

    first = reconcile_hcm_beclass_cooking(port, "115990823")
    replay = reconcile_hcm_beclass_cooking(port, "115990823")

    assert first.requires_cooking is replay.requires_cooking is True
    assert port.apply_count == 1
