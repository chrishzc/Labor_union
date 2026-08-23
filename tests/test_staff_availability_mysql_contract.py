"""
File: test_staff_availability_mysql_contract.py
Description: 驗證 Availability repository 的欄位、衝突來源與 mutex contract。
"""

from pathlib import Path

from pymysql.err import IntegrityError

from infrastructure.mysql.staff_availability_repository import (
    _is_receipt_identity_race,
)


def test_repository_and_schema_share_staff_availability_column_contract():
    schema = Path(
        "db/schema_parts/188_matching_preferences_and_staff_availability.sql"
    ).read_text(encoding="utf-8")
    repository = Path(
        "infrastructure/mysql/staff_availability_repository.py"
    ).read_text(encoding="utf-8")

    for column in (
        "event_key",
        "aggregate_version",
        "before_snapshot",
        "after_snapshot",
        "request_fingerprint",
        "preview_fingerprint",
        "result_snapshot",
        "correlation_id",
    ):
        assert column in schema
        assert column in repository

    assert "ENUM('created','pause_ended','cancelled')" in schema
    assert 'StaffAvailabilityAction.END_PAUSE: "pause_ended"' in repository
    assert "_canonical_json(_block_payload(before) or {})" in repository


def test_repository_uses_canonical_occupancy_mutex_for_fresh_apply_path():
    repository = Path(
        "infrastructure/mysql/staff_availability_repository.py"
    ).read_text(encoding="utf-8")

    assert "from subsystems.scheduling.occupancy_mutex import" in repository
    assert "lock_staff_occupancy_mutex" in repository
    assert "_ASSIGNMENT_CONFLICT_SQL" in repository
    assert "_WAITING_LOCK_CONFLICT_SQL" in repository
    assert "_BUFFER_CONFLICT_SQL" in repository
    assert "def commit(" not in repository
    assert "def rollback(" not in repository


def test_repository_only_classifies_duplicate_receipt_identity_as_a_race():
    assert _is_receipt_identity_race(IntegrityError(1062, "duplicate primary key")) is True
    assert _is_receipt_identity_race(IntegrityError(1452, "foreign key failure")) is False
    assert _is_receipt_identity_race(IntegrityError(3819, "check constraint failure")) is False
