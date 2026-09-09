from infrastructure.mysql.customer_order_change_repository import (
    MySqlCustomerOrderChangeRepository,
)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance


def _row():
    return {
        "case_no": "CASE-2026-018",
        "status": "訂單成立",
        "order_version": 7,
        "client_profile_version": 3,
        "service_city": "新竹市",
        "service_address": "北區光華街 88 號",
        "residence_type": "電梯大樓",
        "requires_cooking": 1,
        "start_date": "2026-10-01",
        "end_date": "2026-10-20",
        "service_days": 20,
        "service_start_time": "09:00:00",
        "service_end_time": "17:00:00",
        "service_end_day_offset": 0,
    }


def test_list_is_bounded_to_the_verified_client_and_maps_owner_versions():
    connection = _Connection([_row()])

    result = MySqlCustomerOrderChangeRepository(connection).list_for_client(42)

    sql, params = connection.cursor_instance.calls[0]
    assert "WHERE o.client_id=%s" in sql
    assert params == (42,)
    assert result[0].case_no == "CASE-2026-018"
    assert result[0].order_version == 7
    assert result[0].client_profile_version == 3
    assert result[0].values["requires_cooking"] == "需要"


def test_apply_read_uses_client_and_case_scope_with_row_lock():
    connection = _Connection([_row()])

    result = MySqlCustomerOrderChangeRepository(connection).load_for_client(
        42, "CASE-2026-018", lock=True
    )

    sql, params = connection.cursor_instance.calls[0]
    assert "WHERE o.client_id=%s AND o.case_no=%s FOR UPDATE" in sql
    assert params == (42, "CASE-2026-018")
    assert result is not None
    assert result.values["service_end_day_offset"] == "0"
