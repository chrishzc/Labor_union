"""
File: test_government_subsidy_reversal_anomaly_source.py
Description: 驗證 GOVSUB-004 reversal predicate 與 source receipt 守恆。
"""

from subsystems.anomalies.government_subsidy_reversal_anomaly_source import (
    GovernmentSubsidyReversalAllocationRootFact,
    GovernmentSubsidyReversalRootFact,
    GovernmentSubsidySourceReceiptRootFact,
    build_reversal_alert_requests,
)


def test_reversal_projects_current_and_historical_source_coordinates():
    requests = build_reversal_alert_requests(_root_fact(previous_coordinates=("12",)))

    assert [(item.desired.source_identity, item.desired.active) for item in requests] == [
        ("finance-import-row:7:source-receipt:12", False),
        ("finance-import-row:7:source-receipt:17", False),
    ]
    assert requests[0].display_snapshot["remaining_reversible_ntd"] is None
    assert requests[1].display_snapshot["remaining_reversible_ntd"] == 60


def test_reversal_requires_review_when_partial_allocation_is_ambiguous():
    requests = build_reversal_alert_requests(_root_fact(amount_ntd=30, multiple_remaining_allocations=True))

    assert len(requests) == 1
    assert requests[0].desired.active is True


def test_single_remaining_allocation_partial_is_unambiguous_for_automation():
    request = build_reversal_alert_requests(_root_fact(amount_ntd=30))[0]

    assert request.desired.active is False


def test_successful_reversal_id_does_not_bypass_ambiguous_remaining_allocations():
    requests = build_reversal_alert_requests(
        _root_fact(
            amount_ntd=30,
            successful_reversal_source_receipt_id=17,
            multiple_remaining_allocations=True,
        )
    )

    assert requests[0].desired.active is True


def test_successful_reversal_id_does_not_bypass_invalid_source_receipt():
    requests = build_reversal_alert_requests(
        _root_fact(successful_reversal_source_receipt_id=17, transaction_status="failed")
    )

    assert requests[0].desired.active is True


def test_successful_reversal_id_does_not_bypass_over_amount():
    requests = build_reversal_alert_requests(
        _root_fact(amount_ntd=61, successful_reversal_source_receipt_id=17)
    )

    assert requests[0].desired.active is True


def test_reversal_closes_current_alert_after_successful_exact_remaining_reversal():
    root_fact = _root_fact(successful_reversal_source_receipt_id=17)

    request = build_reversal_alert_requests(root_fact)[0]

    assert request.desired.active is False
    assert request.desired.source_identity == "finance-import-row:7:source-receipt:17"


def _root_fact(
    amount_ntd=60,
    previous_coordinates=(),
    successful_reversal_source_receipt_id=None,
    multiple_remaining_allocations=False,
    transaction_status="succeeded",
):
    allocations = (
        GovernmentSubsidyReversalAllocationRootFact(1, 60, 0),
        GovernmentSubsidyReversalAllocationRootFact(2, 40, 0),
    ) if multiple_remaining_allocations else (
        GovernmentSubsidyReversalAllocationRootFact(1, 100, 40),
    )
    receipt = GovernmentSubsidySourceReceiptRootFact(
        17,
        "receipt",
        transaction_status,
        100,
        allocations,
    )
    return GovernmentSubsidyReversalRootFact(
        7,
        "bank-7",
        amount_ntd,
        True,
        17,
        successful_reversal_source_receipt_id,
        receipt,
        previous_coordinates,
        2,
        "event-7",
    )
