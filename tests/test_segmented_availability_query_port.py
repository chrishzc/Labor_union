"""
File: test_segmented_availability_query_port.py
Description: 驗證媒合可用性查詢能透過注入的 fresh-facts port 執行。
"""

from datetime import date

from subsystems.scheduling import segmented_availability_query as service


class FactsPort:
    def __init__(self):
        self.case_numbers = []

    def load_case_facts(self, case_no):
        self.case_numbers.append(case_no)
        return {
            "order": {
                "case_no": case_no,
                "status": "洽談中",
                "start_date": "2026-07-01",
                "end_date": "2026-07-02",
                "requires_cooking": False,
            },
            "staff_rows": [{"id": 1}],
            "assignments": [],
            "schedule_rows": [],
            "legacy_schedule_rows": [],
            "buffer_rows": [],
            "active_lock_rows": [],
            "waiting_buffer_rows": [],
        }


def test_search_uses_injected_scheduling_facts_port():
    facts_port = FactsPort()

    result = service.search_segmented_caregiver_availability(
        "CASE-001", 1, [], date(2026, 7, 1), facts_port=facts_port
    )

    assert facts_port.case_numbers == ["CASE-001"]
    assert result["case_no"] == "CASE-001"
