"""Read the latest saved holiday receipt per date without changing accounts."""
import json
from datetime import date

from pymysql.connections import Connection
from pymysql.cursors import DictCursor

from subsystems.scheduling.holiday_accounting_results import HolidayAccountingReceipt
from subsystems.scheduling.holiday_maintenance import _receipt_from_snapshot


def query_holiday_accounting_results(
    connection: Connection, from_date: date, to_date: date,
) -> tuple[HolidayAccountingReceipt, ...]:
    with connection.cursor(DictCursor) as cursor:
        cursor.execute(
            "SELECT result_snapshot FROM (SELECT result_snapshot,ROW_NUMBER() OVER ("
            "PARTITION BY JSON_UNQUOTE(JSON_EXTRACT(result_snapshot,'$.holiday_date')) ORDER BY id DESC) AS rank_no "
            "FROM admin_command_receipts WHERE command_family=%s "
            "AND JSON_LENGTH(JSON_EXTRACT(result_snapshot,'$.case_results'))>0 "
            "AND JSON_UNQUOTE(JSON_EXTRACT(result_snapshot,'$.holiday_date')) BETWEEN %s AND %s) latest "
            "WHERE rank_no=1",
            ("scheduling_holiday_maintenance/v2", from_date.isoformat(), to_date.isoformat()),
        )
        rows = tuple(cursor.fetchall())
    result: list[HolidayAccountingReceipt] = []
    for row in rows:
        payload = row["result_snapshot"]
        receipt = _receipt_from_snapshot(json.loads(payload) if isinstance(payload, str) else payload)
        result.append(HolidayAccountingReceipt(receipt.holiday_date, receipt.receipt_key, receipt.case_results))
    return tuple(sorted(result, key=lambda item: item.holiday_date))
