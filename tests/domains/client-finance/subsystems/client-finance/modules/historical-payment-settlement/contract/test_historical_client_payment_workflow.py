from __future__ import annotations

from datetime import date

import pytest

from domains.client_finance.historical_payment import (
    HistoricalClientConfirmationKind,
    HistoricalClientDirection,
    HistoricalClientObligation,
    HistoricalClientPaymentFacts,
    HistoricalClientPaymentIntent,
    HistoricalClientPaymentProjection,
    HistoricalClientSourceAvailability,
    historical_client_owner_is_terminal,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.historical_payment_settlement import (
    ApplyHistoricalClientPayment,
    HistoricalClientPaymentError,
    HistoricalClientPaymentWorkflow,
)


class _UnitOfWork:
    def __init__(self) -> None:
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self) -> None:
        self.committed = True


class _Repository:
    def __init__(self, facts: HistoricalClientPaymentFacts) -> None:
        self.facts = facts
        self.stored = None
        self.calls: list[object] = []
        self.projections = (
            HistoricalClientPaymentProjection("client-obligation:1", 1200, 3),
        )

    def load(self, case_no, *, for_update):
        assert case_no == "H-CLIENT-1"
        self.calls.append(("load", for_update))
        return self.facts

    def find_receipt(self, _key):
        self.calls.append("find_receipt")
        return self.stored

    def load_projections(self, case_no):
        assert case_no == "H-CLIENT-1"
        self.calls.append("load_projections")
        return self.projections

    def append_event(self, _request, _candidate, event_identity):
        self.calls.append(("event", event_identity))
        return 91

    def append_obligation_links(self, event_id, candidate):
        self.calls.append(("links", event_id, len(candidate.obligations)))

    def upsert_projections(self, event_id, _candidate, version):
        self.calls.append(("projections", event_id, version))

    def append_source_outbox(self, event_id, _candidate, event_identity):
        self.calls.append(("outbox", event_id, event_identity))

    def save_receipt(self, _key, stored):
        self.calls.append("receipt")
        self.stored = stored


def _obligation(*, version=3, direction=HistoricalClientDirection.RECEIVABLE_FROM_CLIENT, kind="first"):
    return HistoricalClientObligation(
        "client-obligation:1",
        "H-CLIENT-1",
        kind,
        direction,
        1200,
        version,
        "open",
    )


def _facts(*, version=7, adopted=True, bank=(), obligation=None):
    return HistoricalClientPaymentFacts(
        "H-CLIENT-1",
        version,
        41 if adopted else None,
        adopted,
        bank,
        (_obligation() if obligation is None else obligation,),
    )


def _intent(direction=HistoricalClientDirection.RECEIVABLE_FROM_CLIENT):
    return HistoricalClientPaymentIntent(
        "H-CLIENT-1",
        direction,
        HistoricalClientConfirmationKind.PAID,
        ("client-obligation:1",),
        date(2025, 1, 8),
        None,
        HistoricalClientSourceAvailability.MISSING,
        "masked-ledger:12",
    )


def _request(preview, *, version=7, key="historical-client:1"):
    return ApplyHistoricalClientPayment(
        _intent(),
        ExpectedVersion(version),
        41,
        preview.candidate.fingerprint,
        IdempotencyKey(key),
        ActorContext("finance:8"),
        "Confirm adopted pre-system payment.",
        CorrelationId("historical-client-correlation"),
    )


def test_query_preview_apply_writes_one_client_owner_transaction() -> None:
    repository = _Repository(_facts())
    unit = _UnitOfWork()
    workflow = HistoricalClientPaymentWorkflow(repository, lambda: unit)

    queried = workflow.query("H-CLIENT-1")
    preview = workflow.preview(_intent())
    receipt = workflow.apply(_request(preview))

    assert queried.normal_bank_candidate_identities == ()
    assert preview.candidate.can_apply is True
    assert receipt.resulting_account_version == 8
    assert receipt.obligation_identities == ("client-obligation:1",)
    assert repository.calls[2:] == [
        "find_receipt",
        ("load", True),
        ("event", receipt.event_identity),
        ("links", 91, 1),
        ("projections", 91, 8),
        ("outbox", 91, receipt.event_identity),
        "receipt",
    ]
    assert unit.committed is True


def test_bank_candidate_blocks_manual_historical_payment_without_write() -> None:
    repository = _Repository(_facts(bank=("bank-candidate:1",)))
    workflow = HistoricalClientPaymentWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_intent())

    assert preview.candidate.blockers == ("historical_client_bank_reconciliation_required",)
    with pytest.raises(HistoricalClientPaymentError) as raised:
        workflow.apply(_request(preview))
    assert raised.value.error.category is ErrorCategory.DOMAIN_BLOCKED
    assert repository.calls == [("load", False), "find_receipt", ("load", True)]


def test_client_direction_is_exact_and_does_not_settle_another_owner_direction() -> None:
    refund = _obligation(direction=HistoricalClientDirection.PAYABLE_TO_CLIENT, kind="subsidy_return")
    preview = HistoricalClientPaymentWorkflow(_Repository(_facts(obligation=refund)), _UnitOfWork).preview(_intent())
    assert preview.candidate.blockers == (
        "historical_client_direction_mismatch",
        "historical_client_obligation_type_mismatch",
    )


def test_replay_is_exact_and_same_key_different_command_conflicts() -> None:
    repository = _Repository(_facts())
    workflow = HistoricalClientPaymentWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_intent())
    request = _request(preview)
    first = workflow.apply(request)
    repository.calls.clear()
    assert workflow.apply(request) == first
    assert repository.calls == ["find_receipt"]

    different = _request(preview, key="historical-client:1")
    different = ApplyHistoricalClientPayment(
        different.intent,
        different.expected_account_version,
        different.expected_adoption_receipt_id,
        different.preview_fingerprint,
        different.idempotency_key,
        different.actor,
        "Different reason.",
        different.correlation_id,
    )
    with pytest.raises(HistoricalClientPaymentError) as raised:
        workflow.apply(different)
    assert raised.value.error.category is ErrorCategory.IDEMPOTENCY_MISMATCH


def test_new_or_changed_client_obligation_reopens_owner_readback() -> None:
    current = _obligation(version=3)
    exact = HistoricalClientPaymentProjection(current.identity, 1200, 3)
    assert historical_client_owner_is_terminal((current,), (exact,)) is True
    assert historical_client_owner_is_terminal((_obligation(version=4),), (exact,)) is False
    second = HistoricalClientObligation(
        "client-obligation:2",
        "H-CLIENT-1",
        "second",
        HistoricalClientDirection.RECEIVABLE_FROM_CLIENT,
        800,
        1,
        "open",
    )
    assert historical_client_owner_is_terminal((current, second), (exact,)) is False


def test_fresh_readback_recomputes_client_owner_terminal_from_current_obligations() -> None:
    repository = _Repository(_facts())
    workflow = HistoricalClientPaymentWorkflow(repository, _UnitOfWork)

    assert workflow.readback("H-CLIENT-1").owner_terminal is True
    repository.facts = _facts(obligation=_obligation(version=4))
    assert workflow.readback("H-CLIENT-1").owner_terminal is False
    assert repository.calls[-2:] == [("load", False), "load_projections"]
