"""
File: test_admin_command_workflows.py
Description: 驗證共用管理命令的 stale preview 與 Holiday 冪等 receipt 行為。
"""

from __future__ import annotations

from datetime import date

import pytest

from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders import client_name_maintenance
from subsystems.scheduling import holiday_maintenance
from subsystems.scheduling.holiday_calendar_query import HolidayCalendarFacts, HolidayFact


class FakeRepository:
    def __init__(self):
        self.holidays: dict[date, HolidayFact] = {}
        self.clients = {"CASE-1": {"name": "原客戶"}}
        self.receipts = {}
        self.lock_calls: list[bool] = []

    def query(self, from_date, to_date, *, lock):
        self.lock_calls.append(lock)
        holidays = tuple(
            self.holidays[key]
            for key in sorted(self.holidays)
            if from_date <= key <= to_date
        )
        version = fingerprint_payload(
            {
                "source": "fake:holidays/v1",
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
        return HolidayCalendarFacts("fake:holidays/v1", version, holidays)

    def load_client_name(self, case_no, **_kwargs):
        return self.clients.get(case_no)

    def load_receipt(self, family, key):
        return self.receipts.get((family, key))

    def save_receipt(
        self,
        family,
        key,
        request_fingerprint,
        _preview,
        _actor,
        _reason,
        result,
    ):
        self.receipts[(family, key)] = {
            "request_fingerprint": request_fingerprint,
            "result_snapshot": result,
        }

    def upsert_holiday(self, holiday_date, holiday_name, double_pay):
        self.holidays[holiday_date] = HolidayFact(
            holiday_date,
            holiday_name,
            double_pay,
        )

    def delete_holiday(self, holiday_date):
        self.holidays.pop(holiday_date)

    def update_client_name(self, case_no, client_name):
        self.clients[case_no]["name"] = client_name


class FakeUnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


def _holiday_command(name: str = "國慶日") -> holiday_maintenance.HolidayCommand:
    target = date(2026, 10, 10)
    return holiday_maintenance.HolidayCommand(
        "upsert",
        target,
        name,
        False,
        date(2026, 10, 1),
        date(2026, 10, 31),
    )


def test_holiday_apply_replays_same_key_and_rejects_different_request():
    repository = FakeRepository()
    command = _holiday_command()
    preview = holiday_maintenance.preview(repository, command)

    first = holiday_maintenance.apply(
        repository,
        command,
        preview.calendar.holiday_version,
        preview.preview_fingerprint,
        "key-1",
        "admin",
        "年度設定",
    )
    replay = holiday_maintenance.apply(
        repository,
        command,
        preview.calendar.holiday_version,
        preview.preview_fingerprint,
        "key-1",
        "admin",
        "年度設定",
    )

    assert replay == first
    with pytest.raises(
        holiday_maintenance.HolidayWorkflowError,
        match="idempotency_key_conflict",
    ):
        holiday_maintenance.apply(
            repository,
            _holiday_command("不同名稱"),
            preview.calendar.holiday_version,
            preview.preview_fingerprint,
            "key-1",
            "admin",
            "年度設定",
        )


def test_holiday_apply_fresh_locks_complete_horizon_and_rejects_stale_version():
    repository = FakeRepository()
    command = _holiday_command()
    preview = holiday_maintenance.preview(repository, command)
    repository.holidays[date(2026, 10, 9)] = HolidayFact(
        date(2026, 10, 9),
        "新增根事實",
        False,
    )

    with pytest.raises(holiday_maintenance.HolidayWorkflowError, match="stale_preview"):
        holiday_maintenance.apply(
            repository,
            command,
            preview.calendar.holiday_version,
            preview.preview_fingerprint,
            "key-stale",
            "admin",
            "年度設定",
        )

    assert repository.lock_calls[-1] is True
    assert date(2026, 10, 10) not in repository.holidays


def test_client_name_apply_rejects_stale_preview():
    repository = FakeRepository()
    preview = client_name_maintenance.preview(repository, "CASE-1", "新客戶")
    repository.clients["CASE-1"]["name"] = "其他人已修改"

    with pytest.raises(ValueError, match="stale_preview"):
        client_name_maintenance.apply(
            repository,
            FakeUnitOfWork,
            "CASE-1",
            "新客戶",
            preview["preview_fingerprint"],
            "key-2",
            "admin",
            "更正姓名",
        )
