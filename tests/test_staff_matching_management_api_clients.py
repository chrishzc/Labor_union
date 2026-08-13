from datetime import date

from ui.api_clients.staff_availability_api_client import StaffAvailabilityApiClient
from ui.api_clients.staff_matching_preferences_api_client import (
    StaffMatchingPreferencesApiClient,
)


class Response:
    ok = True
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_preference_client_returns_typed_definitions(monkeypatch):
    monkeypatch.setattr(
        "ui.api_clients.staff_matching_preferences_api_client.requests.request",
        lambda *args, **kwargs: Response(
            {
                "success": True,
                "data": [
                    {
                        "preference_key": "preferred_service_days",
                        "display_name": "可承接服務天數",
                        "value_kind": "integer_range",
                        "is_filterable": True,
                        "order_fact_key": "service_days",
                        "comparison_operator": "range_with_tolerance",
                        "active": True,
                        "version": 1,
                    }
                ],
            }
        ),
    )

    definitions = StaffMatchingPreferencesApiClient(
        base_url="http://api", headers={}
    ).definitions()

    assert definitions[0].preference_key == "preferred_service_days"


def test_availability_client_returns_typed_blocks(monkeypatch):
    monkeypatch.setattr(
        "ui.api_clients.staff_availability_api_client.requests.request",
        lambda *args, **kwargs: Response(
            {
                "success": True,
                "data": [
                    {
                        "block_id": 1,
                        "staff_id": 9,
                        "kind": "long_leave",
                        "start_date": "2026-08-13",
                        "end_date": "2026-08-20",
                        "status": "effective",
                        "reason": "家庭休假",
                    }
                ],
            }
        ),
    )

    blocks = StaffAvailabilityApiClient(
        base_url="http://api", headers={}
    ).query(9, date(2026, 8, 1), date(2026, 8, 31))

    assert blocks[0].start_date == date(2026, 8, 13)
