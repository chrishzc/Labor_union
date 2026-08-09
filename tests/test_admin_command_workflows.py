import pytest

from subsystems.orders import client_name_maintenance
from subsystems.scheduling import holiday_maintenance


class FakeRepository:
    def __init__(self):
        self.holidays = {}
        self.clients = {"CASE-1": {"name": "原客戶"}}
        self.receipts = {}

    def load_holiday(self, holiday_date, **_kwargs):
        return self.holidays.get(holiday_date)

    def load_client_name(self, case_no, **_kwargs):
        return self.clients.get(case_no)

    def load_receipt(self, family, key):
        return self.receipts.get((family, key))

    def save_receipt(self, family, key, request_fingerprint, _preview, _actor, _reason, result):
        self.receipts[(family, key)] = {
            "request_fingerprint": request_fingerprint,
            "result_snapshot": result,
        }

    def upsert_holiday(self, holiday_date, holiday_name, double_pay):
        self.holidays[holiday_date] = {"holiday_name": holiday_name, "is_double_pay_default": double_pay}

    def delete_holiday(self, holiday_date):
        self.holidays.pop(holiday_date)

    def update_client_name(self, case_no, client_name):
        self.clients[case_no]["name"] = client_name

    def commit(self):
        return None


def test_holiday_apply_replays_same_key_and_rejects_different_request():
    repository = FakeRepository()
    command = {"action": "upsert", "holiday_date": "2026-10-10", "holiday_name": "國慶日", "is_double_pay_default": False}
    preview = holiday_maintenance.preview(repository, command)

    first = holiday_maintenance.apply(repository, command, preview["preview_fingerprint"], "key-1", "admin", "年度設定")
    replay = holiday_maintenance.apply(repository, command, preview["preview_fingerprint"], "key-1", "admin", "年度設定")

    assert replay == first
    with pytest.raises(ValueError, match="idempotency_key_conflict"):
        holiday_maintenance.apply(repository, {**command, "holiday_name": "不同名稱"}, preview["preview_fingerprint"], "key-1", "admin", "年度設定")


def test_client_name_apply_rejects_stale_preview():
    repository = FakeRepository()
    preview = client_name_maintenance.preview(repository, "CASE-1", "新客戶")
    repository.clients["CASE-1"]["name"] = "其他人已修改"

    with pytest.raises(ValueError, match="stale_preview"):
        client_name_maintenance.apply(repository, "CASE-1", "新客戶", preview["preview_fingerprint"], "key-2", "admin", "更正姓名")
