from __future__ import annotations

from datetime import date

import pytest

from domains.staff_payables.historical_payout import (
    HistoricalStaffConfirmationKind,
    HistoricalStaffObligation,
    HistoricalStaffPayoutFacts,
    HistoricalStaffPayoutIntent,
    HistoricalStaffPayoutProjection,
    HistoricalStaffSourceAvailability,
    historical_staff_owner_is_terminal,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.staff_payables.historical_payment_settlement import (
    ApplyHistoricalStaffPayout,
    HistoricalStaffPayoutError,
    HistoricalStaffPayoutWorkflow,
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
    def __init__(self, facts: HistoricalStaffPayoutFacts) -> None:
        self.facts = facts
        self.stored = None
        self.calls: list[object] = []
        self.projections = (
            HistoricalStaffPayoutProjection("staff-obligation:1", 1800, 4),
        )

    def load(self, case_no, staff_id, *, for_update):
        assert (case_no, staff_id) == ("H-STAFF-1", 9)
        self.calls.append(("load", for_update))
        return self.facts

    def find_receipt(self, _key):
        self.calls.append("find_receipt")
        return self.stored

    def load_projections(self, case_no, staff_id):
        assert (case_no, staff_id) == ("H-STAFF-1", 9)
        self.calls.append("load_projections")
        return self.projections

    def append_event(self, _request, _candidate, event_identity):
        self.calls.append(("event", event_identity))
        return 92

    def append_obligation_links(self, event_id, candidate):
        self.calls.append(("links", event_id, len(candidate.obligations)))

    def upsert_projections(self, event_id, _candidate, version):
        self.calls.append(("projections", event_id, version))

    def append_source_outbox(self, event_id, _candidate, event_identity):
        self.calls.append(("outbox", event_id, event_identity))

    def save_receipt(self, _key, stored):
        self.calls.append("receipt")
        self.stored = stored


def _obligation(*, version=4, staff_id=9, case_no="H-STAFF-1", direction="payable_to_staff"):
    return HistoricalStaffObligation(
        "staff-obligation:1",
        case_no,
        staff_id,
        1800,
        version,
        direction,
        "open",
    )


def _facts(*, version=6, adopted=True, bank=(), obligation=None):
    return HistoricalStaffPayoutFacts(
        "H-STAFF-1",
        9,
        version,
        42 if adopted else None,
        adopted,
        bank,
        (_obligation() if obligation is None else obligation,),
    )


def _intent():
    return HistoricalStaffPayoutIntent(
        "H-STAFF-1",
        9,
        HistoricalStaffConfirmationKind.PAID,
        ("staff-obligation:1",),
        date(2025, 2, 3),
        None,
        HistoricalStaffSourceAvailability.UNRECOVERABLE,
        "masked-payout:8",
    )


def _request(preview, *, version=6):
    return ApplyHistoricalStaffPayout(
        _intent(),
        ExpectedVersion(version),
        42,
        preview.candidate.fingerprint,
        IdempotencyKey("historical-staff:1"),
        ActorContext("payables:8"),
        "Confirm adopted pre-system payout.",
        CorrelationId("historical-staff-correlation"),
    )


def test_query_preview_apply_writes_one_staff_owner_transaction() -> None:
    repository = _Repository(_facts())
    unit = _UnitOfWork()
    workflow = HistoricalStaffPayoutWorkflow(repository, lambda: unit)

    queried = workflow.query("H-STAFF-1", 9)
    preview = workflow.preview(_intent())
    receipt = workflow.apply(_request(preview))

    assert queried.normal_bank_candidate_identities == ()
    assert preview.candidate.can_apply is True
    assert receipt.resulting_staff_payables_version == 7
    assert repository.calls[2:] == [
        "find_receipt",
        ("load", True),
        ("event", receipt.event_identity),
        ("links", 92, 1),
        ("projections", 92, 7),
        ("outbox", 92, receipt.event_identity),
        "receipt",
    ]
    assert unit.committed is True


def test_bank_candidate_blocks_manual_staff_payout_without_write() -> None:
    repository = _Repository(_facts(bank=("bank-candidate:staff:1",)))
    workflow = HistoricalStaffPayoutWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_intent())
    assert preview.candidate.blockers == ("historical_staff_bank_reconciliation_required",)
    with pytest.raises(HistoricalStaffPayoutError) as raised:
        workflow.apply(_request(preview))
    assert raised.value.error.category is ErrorCategory.DOMAIN_BLOCKED
    assert repository.calls == [("load", False), "find_receipt", ("load", True)]


@pytest.mark.parametrize(
    ("obligation", "blocker"),
    [
        (_obligation(staff_id=10), "historical_staff_cross_staff_forbidden"),
        (_obligation(case_no="OTHER"), "historical_staff_cross_case_forbidden"),
    ],
)
def test_staff_payout_rejects_cross_owner_obligation(obligation, blocker) -> None:
    preview = HistoricalStaffPayoutWorkflow(_Repository(_facts(obligation=obligation)), _UnitOfWork).preview(_intent())
    assert blocker in preview.candidate.blockers


def test_replay_is_exact_and_different_reason_conflicts() -> None:
    repository = _Repository(_facts())
    workflow = HistoricalStaffPayoutWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(_intent())
    request = _request(preview)
    first = workflow.apply(request)
    repository.calls.clear()
    assert workflow.apply(request) == first
    assert repository.calls == ["find_receipt"]

    different = ApplyHistoricalStaffPayout(
        request.intent,
        request.expected_staff_payables_version,
        request.expected_adoption_receipt_id,
        request.preview_fingerprint,
        request.idempotency_key,
        request.actor,
        "Different reason.",
        request.correlation_id,
    )
    with pytest.raises(HistoricalStaffPayoutError) as raised:
        workflow.apply(different)
    assert raised.value.error.category is ErrorCategory.IDEMPOTENCY_MISMATCH


def test_new_or_changed_staff_obligation_reopens_owner_readback() -> None:
    current = _obligation(version=4)
    exact = HistoricalStaffPayoutProjection(current.identity, 1800, 4)
    assert historical_staff_owner_is_terminal((current,), (exact,)) is True
    assert historical_staff_owner_is_terminal((_obligation(version=5),), (exact,)) is False
    second = HistoricalStaffObligation(
        "staff-obligation:2",
        "H-STAFF-1",
        9,
        600,
        1,
        "payable_to_staff",
        "open",
    )
    assert historical_staff_owner_is_terminal((current, second), (exact,)) is False


def test_fresh_readback_recomputes_staff_owner_terminal_from_current_obligations() -> None:
    repository = _Repository(_facts())
    workflow = HistoricalStaffPayoutWorkflow(repository, _UnitOfWork)

    assert workflow.readback("H-STAFF-1", 9).owner_terminal is True
    repository.facts = _facts(obligation=_obligation(version=5))
    assert workflow.readback("H-STAFF-1", 9).owner_terminal is False
    assert repository.calls[-2:] == [("load", False), "load_projections"]
