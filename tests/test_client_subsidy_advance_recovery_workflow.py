from datetime import date

from domains.client_finance.subsidy_advance import SubsidyAdvanceFacts
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.subsidy_advance_recovery import (
    GovernmentReceiptAllocationEvent,
    SubsidyAdvanceRecoveryTarget,
    SubsidyAdvanceRecoveryWorkflow,
)


class _Repository:
    def __init__(self, target=None, saved=True):
        self.target = target
        self.saved = saved
        self.anomalies = []
        self.recoveries = []

    def find_target(self, event):
        return self.target

    def save_recovery(self, event, recovery):
        self.recoveries.append((event, recovery))
        return self.saved

    def record_anomaly(self, event, reason):
        self.anomalies.append((event, reason))


def _event(amount=6000):
    return GovernmentReceiptAllocationEvent(7, "government-allocation-3", 9, "CASE-1", 3, MoneyNTD(amount))


def _target(advance_paid=6000, recovered=0):
    facts = SubsidyAdvanceFacts("CASE-1", date(2026, 1, 5), MoneyNTD(6000), MoneyNTD(0))
    return SubsidyAdvanceRecoveryTarget("client-ledger-2", MoneyNTD(advance_paid), MoneyNTD(recovered), facts)


def test_consumer_records_exact_recovery_once():
    repository = _Repository(_target())

    outcome = SubsidyAdvanceRecoveryWorkflow(repository).consume(_event())

    assert outcome == "recovered"
    assert repository.recoveries[0][1].amount == MoneyNTD(6000)


def test_consumer_replay_is_existing_without_second_recovery():
    repository = _Repository(_target(recovered=6000), saved=False)

    outcome = SubsidyAdvanceRecoveryWorkflow(repository).consume(_event())

    assert outcome == "existing"
    assert repository.recoveries == []


def test_consumer_routes_missing_or_mismatched_targets_to_review():
    missing = _Repository()
    mismatch = _Repository(_target(advance_paid=5000))

    assert SubsidyAdvanceRecoveryWorkflow(missing).consume(_event()) == "review_required"
    assert SubsidyAdvanceRecoveryWorkflow(mismatch).consume(_event()) == "review_required"
    assert missing.anomalies[0][1] == "subsidy_advance_settlement_ambiguous"
    assert mismatch.anomalies[0][1] == "subsidy_advance_settlement_ambiguous"
