from datetime import date, datetime

import pytest

from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.order_auto_completion_job_repository import _DUE_ORDER_SQL
from shared_kernel.clock import TAIPEI_TIME_ZONE
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.orders.auto_completion_job_dispatch import (
    DueOrderAutoCompletion,
    build_auto_completion_job_command,
)
from subsystems.orders.historical_completion_apply import (
    ApplyHistoricalServiceCompletion,
    HistoricalCompletionClaimState,
    HistoricalServiceCompletionApplyError,
    HistoricalServiceCompletionApplyWorkflow,
    HistoricalServiceCompletionFacts,
    HistoricalServiceCompletionReceipt,
    StoredHistoricalServiceCompletionReceipt,
)


class _Unit:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self) -> None:
        self.committed = True


class _Repository:
    def __init__(self, facts: HistoricalServiceCompletionFacts) -> None:
        self.facts = facts
        self.persisted = []
        self.stored = None

    def claim(self, _request, _fingerprint):
        return (
            HistoricalCompletionClaimState.MATCHED
            if self.stored is not None
            else HistoricalCompletionClaimState.CREATED
        )

    def find_service_completion_receipt(self, _key):
        return self.stored

    def load(self, _case_no, *, for_update):
        assert for_update is True
        return self.facts

    def persist_service_completion(self, _request, candidate):
        self.persisted.append(candidate)
        return HistoricalServiceCompletionReceipt(
            candidate.lifecycle.case_no,
            81,
            candidate.resulting_order_version,
            candidate.lifecycle.after_status,
        )


class _Accounting:
    def __init__(self) -> None:
        self.calls = []

    def establish_default_in_current_unit_of_work(self, **values):
        self.calls.append(values)


class _RejectedAccounting(_Accounting):
    def establish_default_in_current_unit_of_work(self, **values):
        super().establish_default_in_current_unit_of_work(**values)
        raise ValueError("historical_default_accounting_blocked")


def _facts(*, end=date(2026, 9, 21), version=7):
    return HistoricalServiceCompletionFacts(
        "115000069",
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
        version,
        end,
        "historical-source:115000069",
    )


def _request(*, version=7, evaluation=date(2026, 9, 22)):
    return ApplyHistoricalServiceCompletion(
        "115000069",
        version,
        evaluation,
        IdempotencyKey("historical-service-completion:115000069:7"),
        ActorContext("system:historical-service-completion"),
        "historical source service end date passed",
        CorrelationId("historical-service-completion:115000069:7"),
    )


def test_due_historical_service_advances_and_establishes_accounting_in_one_unit() -> None:
    repository = _Repository(_facts())
    accounting = _Accounting()
    unit = _Unit()

    receipt = HistoricalServiceCompletionApplyWorkflow(
        repository, lambda: unit, accounting
    ).apply(_request())

    assert receipt.after_status is OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED
    assert receipt.resulting_order_version == 8
    assert unit.committed is True
    assert len(repository.persisted) == 1
    assert accounting.calls == [{
        "case_no": "115000069",
        "source_identity": "historical-source:115000069",
        "actor": "system:historical-service-completion",
        "correlation_id": "historical-service-completion:115000069:7",
    }]


def test_end_date_equal_to_business_date_does_not_advance() -> None:
    repository = _Repository(_facts(end=date(2026, 9, 22)))
    accounting = _Accounting()
    unit = _Unit()

    with pytest.raises(
        HistoricalServiceCompletionApplyError,
        match="historical_service_completion_not_due",
    ):
        HistoricalServiceCompletionApplyWorkflow(
            repository, lambda: unit, accounting
        ).apply(_request())

    assert unit.committed is False
    assert repository.persisted == []
    assert accounting.calls == []


def test_version_drift_fails_closed_before_persistence() -> None:
    repository = _Repository(_facts(version=8))
    unit = _Unit()

    with pytest.raises(
        HistoricalServiceCompletionApplyError,
        match="historical_service_completion_candidate_stale",
    ):
        HistoricalServiceCompletionApplyWorkflow(
            repository, lambda: unit, _Accounting()
        ).apply(_request(version=7))

    assert unit.committed is False
    assert repository.persisted == []


def test_accounting_failure_prevents_transaction_commit() -> None:
    repository = _Repository(_facts())
    unit = _Unit()

    with pytest.raises(
        HistoricalServiceCompletionApplyError,
        match="historical_default_accounting_blocked",
    ):
        HistoricalServiceCompletionApplyWorkflow(
            repository, lambda: unit, _RejectedAccounting()
        ).apply(_request())

    assert unit.committed is False


def test_historical_due_job_uses_dedicated_command_and_replays_receipt() -> None:
    due = DueOrderAutoCompletion(
        "115000069",
        7,
        datetime(2026, 9, 22, tzinfo=TAIPEI_TIME_ZONE),
        "historical",
    )
    command = build_auto_completion_job_command(due)
    assert command.command_type == "orders_historical_service_completion_apply"
    assert command.payload["reason"] == "historical source service end date passed"

    request = _request()
    command_fingerprint = fingerprint_payload({
        "case_no": request.case_no,
        "expected_order_version": request.expected_order_version,
        "evaluation_date": request.evaluation_date.isoformat(),
        "actor": request.actor.actor_id,
        "reason": request.reason,
    })
    repository = _Repository(_facts())
    repository.stored = StoredHistoricalServiceCompletionReceipt(
        command_fingerprint,
        HistoricalServiceCompletionReceipt(
            request.case_no,
            81,
            8,
            OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        ),
    )

    receipt = HistoricalServiceCompletionApplyWorkflow(
        repository, lambda: _Unit(), _Accounting()
    ).apply(request)
    assert receipt.replayed is True
    assert repository.persisted == []


def test_historical_discovery_is_date_driven_without_scheduling_dependency() -> None:
    historical_select = _DUE_ORDER_SQL.split("UNION ALL", maxsplit=1)[1]

    assert "orders.status = '歷史訂單－服務中'" in historical_select
    assert "orders.actual_end_date < DATE(%s)" in historical_select
    assert "scheduling_aggregates" not in historical_select
    assert "staff_schedule" not in historical_select


def test_durable_worker_registers_historical_service_completion_handler() -> None:
    from api.dependencies.durable_job_handlers import default_job_handlers

    assert (
        default_job_handlers()["orders_historical_service_completion_apply"]
        .__name__
        == "historical_service_completion_handler"
    )
