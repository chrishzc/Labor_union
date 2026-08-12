from datetime import datetime, timezone

from subsystems.anomalies.government_overpayment_anomaly_consumer import (
    build_government_overpayment_root_fact,
)


def test_government_overpayment_event_builds_bound_govsub_root_fact() -> None:
    fact = build_government_overpayment_root_fact(
        {"id": 9, "batch_id": 4, "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc), "payload_snapshot": {"overpayment_identity": "over-1"}},
        {
            "finance_import_row_id": 7,
            "finance_import_batch_id": 3,
            "projection_version": 1,
        },
    )
    assert fact.definition_code == "GOVSUB-006"
    assert dict(fact.recovery_bindings) == {"overpayment_identity": "over-1", "overpayment_version": 1}


def test_government_overpayment_root_fact_uses_canonical_bank_batch_not_claim_batch() -> None:
    fact = build_government_overpayment_root_fact(
        {"id": 9, "batch_id": 999, "created_at": datetime(2026, 8, 11, tzinfo=timezone.utc), "payload_snapshot": {"overpayment_identity": "over-1"}},
        {
            "finance_import_row_id": 7,
            "finance_import_batch_id": 3,
            "projection_version": 1,
        },
    )

    assert fact.finance_import_batch_id == 3
