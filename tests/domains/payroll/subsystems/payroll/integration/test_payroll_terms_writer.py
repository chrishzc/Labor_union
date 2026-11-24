from datetime import date
from types import SimpleNamespace

import pytest

from infrastructure.mysql.payroll_terms_writer import (
    _action_requires_event,
)
from shared_kernel.money import MoneyNTD
from subsystems.payroll.terms_impact import (
    _candidate,
    PayrollTermsActionKind,
)


def test_zero_amount_payroll_action_does_not_create_an_immutable_event():
    action = SimpleNamespace(
        action=PayrollTermsActionKind.ESTABLISH,
        amount=MoneyNTD(0),
    )

    assert _action_requires_event(action) is False


def test_nonzero_payroll_action_still_creates_an_immutable_event():
    action = SimpleNamespace(
        action=PayrollTermsActionKind.CLOSE_UNPAID,
        amount=MoneyNTD(1),
    )

    assert _action_requires_event(action) is True


def test_legacy_dates_do_not_create_payroll_events_or_change_candidate_fingerprint():
    def facts(service_date):
        return SimpleNamespace(
            case_no="CASE-1",
            payroll_version=3,
            scheduling=SimpleNamespace(
                assignments=(
                    SimpleNamespace(
                        candidate_key="case-1:g2:a1",
                        sequence=1,
                        double_pay_dates=(service_date,),
                    ),
                )
            ),
        )

    payroll = SimpleNamespace(fingerprint=SimpleNamespace(value="payroll-facts"))

    first = _candidate(facts(date(2026, 8, 8)), payroll, (), ())
    second = _candidate(facts(date(2026, 8, 9)), payroll, (), ())

    assert first.special_pay_events == ()
    assert first.fingerprint == second.fingerprint


class InstallmentCursor:
    def __init__(self):
        self.calls = []
        self.statement = ""

    def execute(self, statement, parameters):
        self.statement = statement
        self.calls.append((statement, parameters))

    def fetchone(self):
        if "AS actual_end_date" in self.statement:
            return {"actual_end_date": date(2026, 10, 2)}
        return None

    def fetchall(self):
        if "FROM staff_obligations" in self.statement:
            return ({"obligation_identity": "new-unpaid-root"},)
        return ()


def _tiered_terms_command(frozen):
    from subsystems.orders.terms_workflow import PayrollImpactPersistenceCommand
    from subsystems.payroll.terms_impact import PayrollTermsImpactCandidate
    from shared_kernel.fingerprints import fingerprint_payload
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey

    assignment = SimpleNamespace(
        assignment_identity="tiered:g2:a1", staff_id=7, tiered_pricing=True,
        directly_subsidized=True, covered_salary=2400, total_payable=MoneyNTD(5800),
    )
    candidate = PayrollTermsImpactCandidate(
        "TIERED", 2, 3, SimpleNamespace(assignments=(assignment,)), (), (), (),
        fingerprint_payload({"case": "TIERED"}), frozen_settlements=frozen,
    )
    return PayrollImpactPersistenceCommand(
        candidate, SimpleNamespace(assignment_id_by_candidate_key={assignment.assignment_identity: 200}),
        IdempotencyKey("tiered-terms"), ActorContext("synthetic"), "confirmed shorter service",
        CorrelationId("tiered-terms"), 1,
    )


def _isolate_terms_side_effects(monkeypatch):
    from infrastructure.mysql import payroll_terms_writer as writer
    from infrastructure.mysql import payroll_amount_correction_repository as amounts
    from infrastructure.mysql import staff_payable_payroll_correction as corrections

    calls = []
    monkeypatch.setattr(writer, "persist_payroll_rate_snapshots", lambda *args: None)
    monkeypatch.setattr(amounts, "controlled_payroll_terms", lambda *args: (set(), {}))
    monkeypatch.setattr(writer, "_advance_payroll_version", lambda *args: calls.append("version"))
    monkeypatch.setattr(writer, "_append_outbox", lambda *args: calls.append("outbox"))
    monkeypatch.setattr(corrections, "persist_staff_payable_payroll_corrections",
                        lambda connection, command: calls.append(command.candidate.frozen_settlements))
    return writer, calls


@pytest.mark.parametrize("previous", [5800, 13000])
def test_tiered_paid_root_keeps_original_installments_after_assignment_replacement(monkeypatch, previous):
    from subsystems.payroll.terms_impact import PayrollFrozenSettlement

    frozen = PayrollFrozenSettlement(
        "original-paid-root", "staff-handover:correction" if previous != 5800 else None,
        7, MoneyNTD(previous), MoneyNTD(5800), MoneyNTD(1000), MoneyNTD(0), "tiered:g2:a1",
    )
    command = _tiered_terms_command((frozen,))
    cursor = InstallmentCursor()
    cursor.connection = object()
    writer, calls = _isolate_terms_side_effects(monkeypatch)

    writer.persist_payroll_terms_impact(cursor, command)

    # The retained paid root belongs to assignment 1, not the replacement 200.
    # No root lookup or installment write may replace its funding evidence.
    assert cursor.calls == []
    assert calls == ["version", "outbox", (frozen,)]
    assert frozen.obligation_identity == "original-paid-root"
    assert frozen.paid_net_amount == MoneyNTD(1000)


def test_tiered_unpaid_replacement_still_persists_the_owner_installment_plan(monkeypatch):
    command = _tiered_terms_command(())
    cursor = InstallmentCursor()
    writer, calls = _isolate_terms_side_effects(monkeypatch)

    writer.persist_payroll_terms_impact(cursor, command)

    root_query = next(parameters for statement, parameters in cursor.calls if "FROM staff_obligations" in statement)
    assert root_query == ("TIERED", 200)
    inserts = [parameters for statement, parameters in cursor.calls
               if statement.startswith("INSERT INTO staff_obligation_installments")]
    assert inserts == [
        ("new-unpaid-root", "client", 3400, date(2026, 11, 15)),
        ("new-unpaid-root", "subsidy", 2400, date(2026, 12, 15)),
    ]
    assert calls == ["version", "outbox"]


def test_preserved_funding_mismatch_stays_unknown_for_original_confirmation(monkeypatch):
    from infrastructure.mysql import staff_payout_repository as payouts

    original = (
        {"funding_kind": "client", "amount_ntd": 1000, "due_date": date(2026, 11, 15)},
        {"funding_kind": "subsidy", "amount_ntd": 12000, "due_date": date(2026, 12, 15)},
    )

    class FundingCursor:
        calls = []

        def execute(self, statement, parameters):
            self.calls.append((statement, parameters))

        def fetchall(self):
            return original

    cursor = FundingCursor()
    monkeypatch.setattr(payouts, "_funding_settlements",
                        lambda *args: ({"client": 1000, "subsidy": 0}, False))

    portions = payouts.query_staff_funding_portions(
        cursor, "original-paid-root", settled_total=1000, amount_total=5800,
    )

    assert [(p.funding_kind, p.amount_ntd, p.due_date) for p in portions] == [
        (row["funding_kind"], row["amount_ntd"], row["due_date"]) for row in original
    ]
    assert all(p.settled_ntd is None and p.remaining_ntd is None for p in portions)
    assert all(statement.startswith("SELECT ") for statement, _ in cursor.calls)
