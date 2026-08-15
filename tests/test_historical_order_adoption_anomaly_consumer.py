"""
File: test_historical_order_adoption_anomaly_consumer.py
Description: 驗證歷史訂單 review 僅以遮罩 evidence 投影 HISTORICAL-ORDER-001。
"""

from subsystems.anomalies import historical_order_adoption_outbox_consumer as consumer


def test_historical_order_review_project_request_uses_review_root_not_raw_case_snapshot():
    request = consumer._project_request(
        {"id": 7, "bounded_snapshot": '{"review_identity":"historical-order-review:one","case_no":"RAW-SECRET"}'},
        {
            "review_identity": "historical-order-review:one",
            "masked_case_identity": "AB****89",
            "issue_codes": '["staff_missing","unknown_status"]',
        },
    )

    assert request.desired.definition_code == "HISTORICAL-ORDER-001"
    assert request.desired.fingerprint_values == {"review_identity": "historical-order-review:one"}
    assert request.display_snapshot == {
        "review_identity": "historical-order-review:one",
        "masked_case_identity": "AB****89",
        "issue_codes": ("staff_missing", "unknown_status"),
    }
    assert "RAW-SECRET" not in str(request.display_snapshot)


def test_historical_order_review_requires_review_identity():
    try:
        consumer._review_identity({"bounded_snapshot": "{}"})
    except ValueError as error:
        assert str(error) == "historical_order_review_identity_missing"
    else:
        raise AssertionError("missing review identity must fail closed")


def test_historical_order_review_is_visible_in_import_alert_tab():
    from api.schemas.anomaly_registry import AnomalySummaryView
    import importlib

    panel = importlib.import_module("ui.pages.06_finance_alerts")
    review_alert = AnomalySummaryView(
        fingerprint="c" * 64,
        definition_code="HISTORICAL-ORDER-001",
        source_domain="orders",
        source_identity="historical-order-review:test",
        source_version=0,
        workflow_status="open",
        workflow_version=1,
        severity="warning",
        predicate_active=True,
        display_snapshot={"masked_case_identity": "AB****89", "issue_codes": ["staff_missing"]},
    )

    assert panel._filter((review_alert,), panel._IMPORT_CODES) == (review_alert,)
    assert panel._alert_code_label(review_alert.definition_code) == "歷史訂單匯入待人工確認"
