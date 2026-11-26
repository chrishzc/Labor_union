"""
File: scheduling_holiday_query.py
Description: 實作國定假日 horizon 查詢、鎖定、mutation 與 immutable receipt persistence。
"""

from __future__ import annotations

from infrastructure.mysql.nas_mutations import call_mutation

import json
from datetime import date

from shared_kernel.fingerprints import fingerprint_payload
from subsystems.scheduling.holiday_calendar_query import (
    HolidayCalendarFacts,
    HolidayCalendarUnavailable,
    HolidayFact,
)

_SOURCE_IDENTITY = "mysql:holidays/v1"
_HOLIDAYS_SQL = (
    "SELECT holiday_date,holiday_name,is_double_pay_default FROM holidays "
    "WHERE holiday_date BETWEEN %s AND %s ORDER BY holiday_date"
)


class MySqlSchedulingHolidayQuery:
    def __init__(self, connection) -> None:
        self._connection = connection

    def query(
        self,
        service_start_date: date,
        service_end_date: date,
        *,
        lock: bool,
    ) -> HolidayCalendarFacts:
        if service_start_date > service_end_date:
            raise HolidayCalendarUnavailable("holiday date range is invalid")
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    _HOLIDAYS_SQL + (" FOR UPDATE" if lock else ""),
                    (service_start_date, service_end_date),
                )
                holidays = tuple(_holiday_fact(row) for row in cursor.fetchall())
        except HolidayCalendarUnavailable:
            raise
        except Exception as error:
            raise HolidayCalendarUnavailable("holiday source is unavailable") from error
        return HolidayCalendarFacts(
            _SOURCE_IDENTITY,
            _calendar_version(holidays),
            holidays,
        )

    def load_receipt(self, family: str, key: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s FOR UPDATE",
                (family, key),
            )
            return cursor.fetchone()

    def save_receipt(
        self,
        family: str,
        key: str,
        request_fingerprint: str,
        preview_fingerprint: str,
        actor: str,
        reason: str,
        result: dict[str, object],
    ) -> None:
        from infrastructure.mysql.order_terms_read_model import select_order
        from infrastructure.mysql.pricing_configuration_repository import find_service_shortening_pricing_basis

        with self._connection.cursor() as cursor:
            shortening_receipts: dict[str, int] = {}
            case_results = result.get("case_results")
            if isinstance(case_results, list):
                for case_result in case_results:
                    case_no = case_result.get("case_no") if isinstance(case_result, dict) else None
                    if isinstance(case_no, str) and case_result.get("case_total_amount") is not None:
                        order = select_order(cursor, case_no, lock=True)
                        shortening = find_service_shortening_pricing_basis(cursor, order, lock=True)
                        if shortening is not None:
                            shortening_receipts[case_no] = shortening.receipt_id
            snapshot = {**result, "service_shortening_receipts": shortening_receipts} if shortening_receipts else result
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (
                    family,
                    key,
                    request_fingerprint,
                    preview_fingerprint,
                    actor,
                    reason,
                    json.dumps(snapshot, ensure_ascii=False),
                ),
            )

    def upsert_holiday(
        self,
        holiday_date: date,
        holiday_name: str,
        is_double_pay_default: bool,
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO holidays (holiday_date,holiday_name,is_double_pay_default) "
                "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE holiday_name=VALUES(holiday_name),is_double_pay_default=VALUES(is_double_pay_default)",
                (holiday_date, holiday_name, is_double_pay_default),
            )

    def delete_holiday(self, holiday_date: date) -> None:
        with self._connection.cursor() as cursor:
            call_mutation(cursor, "lu_nas_delete_holiday_v1", holiday_date)


def _holiday_fact(row) -> HolidayFact:
    holiday_date = row["holiday_date"]
    holiday_name = row["holiday_name"]
    double_pay = row["is_double_pay_default"]
    if (
        not isinstance(holiday_date, date)
        or not isinstance(holiday_name, str)
        or not isinstance(double_pay, (bool, int))
    ):
        raise HolidayCalendarUnavailable("holiday source has invalid facts")
    return HolidayFact(holiday_date, holiday_name, bool(double_pay))


def _calendar_version(holidays: tuple[HolidayFact, ...]) -> str:
    return fingerprint_payload(
        {
            "source": _SOURCE_IDENTITY,
            "holidays": tuple(
                (
                    item.holiday_date.isoformat(),
                    item.holiday_name,
                    item.is_double_pay_default,
                )
                for item in holidays
            ),
        }
    ).value
