"""
File: test_holiday_preview_apply_disposable_mysql_e2e.py
Description: 以唯一 MySQL 測試庫驗證 Holiday Preview 零寫入、Apply 原子性與冪等 replay。
"""

from __future__ import annotations

from argparse import Namespace
from datetime import date
import os

import pymysql
import pytest

from infrastructure.mysql.scheduling_holiday_query import MySqlSchedulingHolidayQuery
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from subsystems.scheduling import holiday_maintenance


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_phase3bh_* database",
)


def test_preview_zero_write_apply_rollback_commit_and_replay():
    _require_owned_database(DATABASE)
    created = False
    try:
        bootstrap(_arguments())
        created = True
        command = holiday_maintenance.HolidayCommand(
            "upsert",
            date(2026, 10, 10),
            "國慶日",
            False,
            date(2026, 10, 1),
            date(2026, 10, 31),
        )

        connection = _connect_database()
        try:
            repository = MySqlSchedulingHolidayQuery(connection)
            preview = holiday_maintenance.preview(repository, command)
            assert _counts() == (0, 0)
            pending = holiday_maintenance.apply(
                repository,
                command,
                preview.calendar.holiday_version,
                preview.preview_fingerprint,
                "phase3bh-rollback",
                "holiday-test",
                "rollback proof",
            )
            assert pending.changed is True
            assert _counts() == (0, 0)
            connection.rollback()
        finally:
            connection.close()
        assert _counts() == (0, 0)

        connection = _connect_database()
        try:
            repository = MySqlSchedulingHolidayQuery(connection)
            preview = holiday_maintenance.preview(repository, command)
            receipt = holiday_maintenance.apply(
                repository,
                command,
                preview.calendar.holiday_version,
                preview.preview_fingerprint,
                "phase3bh-commit",
                "holiday-test",
                "commit proof",
            )
            connection.commit()
            replay = holiday_maintenance.apply(
                repository,
                command,
                preview.calendar.holiday_version,
                preview.preview_fingerprint,
                "phase3bh-commit",
                "holiday-test",
                "commit proof",
            )
            connection.commit()
        finally:
            connection.close()

        assert replay == receipt
        assert _counts() == (1, 1)
    finally:
        if created:
            _drop_owned_database(DATABASE)


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _connect_database():
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _counts() -> tuple[int, int]:
    connection = _connect_database()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM holidays WHERE holiday_date=%s",
                (date(2026, 10, 10),),
            )
            holidays = int(cursor.fetchone()["count"])
            cursor.execute(
                "SELECT COUNT(*) AS count FROM admin_command_receipts "
                "WHERE command_family=%s",
                ("scheduling_holiday_maintenance/v2",),
            )
            receipts = int(cursor.fetchone()["count"])
            return holidays, receipts
    finally:
        connection.close()


def _require_owned_database(database: str | None) -> None:
    if not isinstance(database, str) or not database.startswith("lu_test_phase3bh_"):
        raise RuntimeError("owned disposable Holiday database name is required")


def _drop_owned_database(database: str) -> None:
    _require_owned_database(database)
    connection = pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE `{database}`")
    finally:
        connection.close()
