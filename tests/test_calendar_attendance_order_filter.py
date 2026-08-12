from importlib import import_module


_filter_attendance_orders = import_module(
    "ui.pages.03_calendar"
)._filter_attendance_orders
_load_all_matching_order_summaries = import_module(
    "ui.pages.03_calendar"
)._load_all_matching_order_summaries


def test_attendance_filter_keeps_started_order_when_summary_lacks_actual_start():
    orders = [
        {"case_no": "A", "staff_id": "532", "staff_name": "王明欣、胡欣", "actual_start_date": "2026-08-01", "order_status": "服務中"},
        {"case_no": "B", "staff_id": 532, "staff_name": "王明欣", "actual_start_date": None, "start_date": "2026-08-01", "order_status": "服務中"},
        {"case_no": "C", "staff_id": 558, "staff_name": "胡欣", "actual_start_date": "2026-08-01", "order_status": "服務中"},
    ]

    assert [order["case_no"] for order in _filter_attendance_orders(orders, 532, "王明欣")] == ["A", "B"]


def test_attendance_filter_falls_back_to_official_assignment_for_staff_membership():
    orders = [
        {
            "case_no": "C",
            "staff_id": None,
            "staff_name": "",
            "actual_start_date": "2026-08-01",
            "order_status": "服務中",
        }
    ]

    assert _filter_attendance_orders(
        orders,
        532,
        "王明欣",
        formal_case_nos={"C"},
    ) == orders


def test_attendance_filter_keeps_formal_assignment_without_actual_start_date():
    order = {
        "case_no": "C",
        "staff_id": None,
        "staff_name": "",
        "actual_start_date": None,
        "order_status": "訂單成立",
    }

    assert _filter_attendance_orders(
        [order],
        532,
        "王明欣",
        formal_case_nos={"C"},
    ) == [order]


def test_order_summary_loader_collects_all_pages(monkeypatch):
    pages = {
        None: ([{"case_no": "A"}], "A"),
        "A": ([{"case_no": "B"}], None),
    }
    monkeypatch.setattr(
        "ui.pages.03_calendar._load_matching_order_summaries",
        lambda _base_url, _headers, after_case_no=None: pages[after_case_no],
    )

    assert _load_all_matching_order_summaries("http://api", ()) == [
        {"case_no": "A"},
        {"case_no": "B"},
    ]
