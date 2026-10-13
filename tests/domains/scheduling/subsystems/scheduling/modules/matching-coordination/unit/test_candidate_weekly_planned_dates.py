from datetime import date

from infrastructure.mysql.matching_notification_repository import MySqlMatchingNotificationRepository


class Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def execute(self, sql, params):
        assert sql.lstrip().startswith("SELECT")
        assert "CASE-PLAN" in params

    def fetchone(self):
        return {"segment_id": 1, "staff_id": 100, "assigned_start_date": date(2026, 11, 5),
                "assigned_end_date": date(2026, 11, 9), "case_no": "CASE-PLAN", "client_name": "合成客戶",
                "staff_name": "合成月嫂", "weekly_rest_days": '["週六", "週日"]',
                "custom_rest_dates": [], "service_hours_per_day": 8, "service_days": 3}

    def fetchall(self):
        return [{"service_date": value} for value in (date(2026, 11, 5), date(2026, 11, 6), date(2026, 11, 9))]


class Connection:
    def cursor(self):
        return Cursor()


def test_transient_dates_override_saved_dates_and_staff_preferences_without_writes():
    result = MySqlMatchingNotificationRepository(Connection()).candidate_weekly_service_preview(
        "CASE-PLAN", 1, (date(2026, 11, 5), date(2026, 11, 7), date(2026, 11, 9)),
    )
    assert result["date_basis"] == "draft"
    assert [(row["weekly_work_days"], row["weekly_hours"]) for row in result["rows"]] == [(2, 16), (1, 8)]
    assert result["projected_service_days"] == 3


def test_reopen_reads_saved_dates_without_reinterpreting_service_text_or_weekdays():
    result = MySqlMatchingNotificationRepository(Connection()).candidate_weekly_service_preview("CASE-PLAN", 1)
    assert result["date_basis"] == "confirmed"
    assert result["projected_service_days"] == 3
