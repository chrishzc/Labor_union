"""
File: test_historical_order_adoption_outbox_consumer.py
Description: 驗證 Orders 歷史 review outbox 只確認 canonical receipt 並保留 delivery retry。
"""

from subsystems.orders import historical_order_adoption_outbox_consumer as consumer


def test_historical_order_review_event_requires_canonical_receipt_and_review():
    consumer._validate_canonical_event(
        {
            "id": 7,
            "receipt_id": 11,
            "intent_type": "historical_order_review_required",
            "bounded_snapshot": '{"review_identity":"historical-order-review:one","case_no":"RAW-SECRET"}',
        },
        {
            "id": 11,
            "outcome": "review_required",
            "review_identity": "historical-order-review:one",
            "result_snapshot": {},
        },
        {
            "review_identity": "historical-order-review:one",
            "source_event_identity": "source:one",
            "case_identity": "AB****89",
            "issue_codes": ["staff_missing", "unknown_status"],
            "evidence_snapshot": {},
        },
        "historical-order-review:one",
    )


def test_historical_order_review_requires_review_identity():
    try:
        consumer._review_identity({"bounded_snapshot": "{}"})
    except ValueError as error:
        assert str(error) == "historical_order_review_identity_missing"
    else:
        raise AssertionError("missing review identity must fail closed")


def test_historical_order_review_event_rejects_receipt_binding_mismatch():
    try:
        consumer._validate_canonical_event(
            {
                "receipt_id": 7,
                "intent_type": "historical_order_review_required",
                "bounded_snapshot": '{"review_identity":"review"}',
            },
            {"id": 8, "outcome": "review_required", "review_identity": "review", "result_snapshot": {}},
            {
                "review_identity": "review",
                "source_event_identity": "source",
                "case_identity": "CA****01",
                "issue_codes": [],
                "evidence_snapshot": {},
            },
            "review",
        )
    except ValueError as error:
        assert str(error) == "historical_order_adoption_receipt_binding_mismatch"
    else:
        raise AssertionError("receipt mismatch must fail closed")
