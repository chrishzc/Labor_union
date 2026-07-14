import json

from line.main import app, ensure_order_for_case_no


class FakeCursor:
    def __init__(self, existing_order=None):
        self.existing_order = existing_order
        self.calls = []

    def execute(self, sql, params):
        self.calls.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.existing_order


def test_openapi_uses_case_no_for_order_contracts():
    openapi = app.openapi()
    serialized = json.dumps(openapi)
    legacy_key = "order" + "_id"

    assert legacy_key not in serialized
    assert "/api/v1/orders/{case_no}" in openapi["paths"]
    assert "/api/v1/orders/{case_no}/full-details" in openapi["paths"]
    assert "/api/v1/orders/{case_no}/status" in openapi["paths"]
    assert "/api/v1/orders/{case_no}/assign-staff" in openapi["paths"]

    recommend_params = openapi["paths"][
        "/api/v1/matches/recommend-staff"
    ]["get"]["parameters"]
    assert any(param["name"] == "case_no" for param in recommend_params)


def test_line_creates_order_only_after_case_no_is_available():
    pending_cursor = FakeCursor()
    ensure_order_for_case_no(pending_cursor, client_id=51, case_no=None)
    assert pending_cursor.calls == []

    official_cursor = FakeCursor()
    ensure_order_for_case_no(
        official_cursor,
        client_id=51,
        case_no="115000001",
    )

    assert official_cursor.calls[0] == (
        "SELECT client_id FROM orders WHERE case_no = %s",
        ("115000001",),
    )
    assert official_cursor.calls[1] == (
        "INSERT INTO orders (case_no, client_id) VALUES (%s, %s)",
        ("115000001", 51),
    )
