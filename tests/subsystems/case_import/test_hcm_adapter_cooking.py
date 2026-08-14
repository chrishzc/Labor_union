from datetime import date, datetime

from subsystems.case_import.hcm_adapter import build_hcm_case_import_intent


def test_hcm_adapter_creates_unknown_cooking_requirement_without_beclass():
    intent = build_hcm_case_import_intent(
        {
            "case_no": "115000888",
            "identity_status": "一般市民",
            "service_start_date": date(2026, 8, 20),
            "created_at": datetime(2026, 8, 1, 9, 0),
            "service_time": "8 小時 09:00 17:00",
            "service_days": 5,
            "name": "測試客戶",
        },
        date(2026, 8, 24),
    )

    assert intent.order.requires_cooking is None
    assert intent.order.case_no == "115000888"
