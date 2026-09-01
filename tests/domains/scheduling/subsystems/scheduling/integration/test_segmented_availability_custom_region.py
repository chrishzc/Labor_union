"""Regression coverage for custom Staff service-region facts in Matching Query."""

from infrastructure.mysql.segmented_availability_repository import (
    MySqlSegmentedAvailabilityFactsRepository,
)
from subsystems.scheduling.segmented_availability_query import _staff_filter_results


class _RegionCursor:
    def __init__(self) -> None:
        self.current = []
        self.statements: list[str] = []

    def execute(self, sql: str, _params=None) -> None:
        self.statements.append(sql)
        if "FROM staff s" in sql:
            self.current = [{"id": 531, "name": "自訂區域月嫂"}]
        elif "FROM staff_regions" in sql:
            self.current = [
                {
                    "staff_id": 531,
                    "region_name": "其他",
                    "custom_region_detail": "新竹市",
                },
                {
                    "staff_id": 531,
                    "region_name": "北區",
                    "custom_region_detail": "不得覆蓋標準區域",
                },
                {
                    "staff_id": 531,
                    "region_name": "其他",
                    "custom_region_detail": None,
                },
            ]
        else:
            self.current = []

    def fetchall(self):
        return self.current


def test_segmented_availability_uses_custom_detail_for_other_region() -> None:
    cursor = _RegionCursor()
    repository = MySqlSegmentedAvailabilityFactsRepository(lambda: None)

    staff = repository._load_active_staff(cursor)[0]

    assert staff["regions"] == ["新竹市", "北區", "其他"]
    assert any(
        "custom_region_detail" in statement for statement in cursor.statements
    )
    assert _staff_filter_results(
        staff,
        {"city": "新竹市", "address": "東區測試路", "requires_cooking": False},
        {
            "region": True,
            "cooking": False,
            "preferred_service_days": False,
            "daily_service_hours": False,
            "enabled_preference_keys": (),
        },
    )["region"] is True
