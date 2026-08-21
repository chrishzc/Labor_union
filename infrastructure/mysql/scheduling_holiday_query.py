"""
File: scheduling_holiday_query.py
Description: 實作國定假日 horizon 查詢、鎖定、mutation 與 immutable receipt persistence。
"""

from __future__ import annotations

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
        with self._connection.cursor() as cursor:
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
                    json.dumps(result, ensure_ascii=False),
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
                "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE "
                "holiday_name=VALUES(holiday_name),"
                "is_double_pay_default=VALUES(is_double_pay_default)",
                (holiday_date, holiday_name, is_double_pay_default),
            )

    def delete_holiday(self, holiday_date: date) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("DELETE FROM holidays WHERE holiday_date=%s", (holiday_date,))


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
