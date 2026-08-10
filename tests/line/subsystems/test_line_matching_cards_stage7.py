"""Stage 7 caregiver and customer Flex card privacy contracts."""

import json

from domains.scheduling.matching_communication import MatchingNotificationKind
from subsystems.scheduling.matching_line_cards import (
    caregiver_information_card,
    customer_profiles_card,
)


def test_caregiver_card_contains_one_time_actions_without_customer_pii() -> None:
    payload = caregiver_information_card(
        MatchingNotificationKind.CAREGIVER_INFO_1,
        {
            "case_no": "CASE-1",
            "start_date": "2026-09-01",
            "end_date": "2026-09-10",
            "city": "台北市",
            "service_type": "到府服務",
            "customer_name": "不應出現",
            "customer_phone": "0900000000",
        },
        "safe-token-12345678901234567890",
    )
    decoded = json.loads(payload)
    rendered = json.dumps(decoded, ensure_ascii=False)

    assert "matching:safe-token-12345678901234567890:willing" in rendered
    assert "不應出現" not in rendered
    assert "0900000000" not in rendered


def test_customer_profile_carousel_excludes_sensitive_staff_fields() -> None:
    payload = customer_profiles_card(
        "CASE-1",
        (
            {
                "name": "林月嫂",
                "city": "台中市",
                "care_babies": 2,
                "has_massage_cert": True,
                "service_regions": ["台中市"],
                "special_skills": ["月子餐"],
                "identity_card": "A123456789",
                "phone": "0912345678",
                "address": "不應出現的地址",
            },
        ),
        "safe-token-12345678901234567890",
        "請確認服務區段。",
    )
    rendered = json.dumps(json.loads(payload), ensure_ascii=False)

    assert "林月嫂" in rendered
    assert "接受此配對" in rendered
    assert "A123456789" not in rendered
    assert "0912345678" not in rendered
    assert "不應出現的地址" not in rendered
