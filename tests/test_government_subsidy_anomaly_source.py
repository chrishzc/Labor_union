from subsystems.anomalies.government_subsidy_anomaly_source import (
    GovernmentSubsidyEligibleBatch,
    GovernmentSubsidyItemOutstanding,
    GovernmentSubsidyReceiptRootFact,
    build_government_subsidy_alert_requests,
)


def test_no_unique_batch_alert_stays_active_without_an_eligible_batch():
    requests = build_government_subsidy_alert_requests(_root_fact())

    assert len(requests) == 1
    assert requests[0].desired.definition_code == "GOVSUB-001"
    assert requests[0].desired.active is True
    assert requests[0].display_snapshot["candidate_batch_ids"] == ()


def test_unique_batch_with_multiple_partial_items_projects_ambiguous_allocation():
    batch = GovernmentSubsidyEligibleBatch(
        11,
        200,
        (GovernmentSubsidyItemOutstanding(1, 120), GovernmentSubsidyItemOutstanding(2, 80)),
    )

    requests = build_government_subsidy_alert_requests(_root_fact(amount_ntd=100, batches=(batch,)))

    assert [(request.desired.definition_code, request.desired.active) for request in requests] == [
        ("GOVSUB-001", False),
        ("GOVSUB-002", True),
    ]
    assert requests[1].desired.source_identity == "finance-import-row:7:batch:11"
    assert requests[1].display_snapshot["item_outstanding"] == (
        {"claim_item_id": 1, "outstanding_ntd": 120},
        {"claim_item_id": 2, "outstanding_ntd": 80},
    )


def test_historical_ambiguous_batch_is_projected_closed_after_receipt_succeeds():
    requests = build_government_subsidy_alert_requests(
        _root_fact(previous_batch_ids=(3,), succeeded_batch_id=11),
    )

    assert [(request.desired.definition_code, request.desired.source_identity, request.desired.active) for request in requests] == [
        ("GOVSUB-001", "finance-import-row:7", False),
        ("GOVSUB-002", "finance-import-row:7:batch:3", False),
        ("GOVSUB-002", "finance-import-row:7:batch:11", False),
    ]


def _root_fact(amount_ntd=100, batches=(), previous_batch_ids=(), succeeded_batch_id=None):
    return GovernmentSubsidyReceiptRootFact(
        7,
        "bank-7",
        amount_ntd,
        True,
        succeeded_batch_id,
        batches,
        previous_batch_ids,
        2,
        "event-7",
    )
