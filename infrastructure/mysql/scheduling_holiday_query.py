"""MySQL adapter for the Scheduling-owned canonical Holiday Query."""

from __future__ import annotations

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
        except Exception as error:
            raise HolidayCalendarUnavailable("holiday source is unavailable") from error
        return HolidayCalendarFacts(
            _SOURCE_IDENTITY,
            fingerprint_payload(
                {
                    "source": _SOURCE_IDENTITY,
                    "holidays": tuple(
                        (item.holiday_date.isoformat(), item.holiday_name)
                        for item in holidays
                    ),
                }
            ).value,
            holidays,
        )


def _holiday_fact(row) -> HolidayFact:
    holiday_date = row["holiday_date"]
    holiday_name = row["holiday_name"]
    if not isinstance(holiday_date, date) or not isinstance(holiday_name, str):
        raise HolidayCalendarUnavailable("holiday source has invalid facts")
    return HolidayFact(holiday_date, holiday_name)
