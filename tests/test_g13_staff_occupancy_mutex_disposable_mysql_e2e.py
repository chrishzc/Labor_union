"""Global E2E proof for canonical staff occupancy mutex ordering."""

from __future__ import annotations

from argparse import Namespace
import os
from queue import Queue
from threading import Barrier, Thread
from time import sleep
from uuid import uuid4

import pymysql
import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from subsystems.scheduling.occupancy_mutex import lock_staff_occupancy_mutex


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _bootstrap_arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _connection() -> pymysql.Connection:
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def _seed_staff() -> list[int]:
    identity_prefix = "G13-" + uuid4().hex[:12]
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO staff (name, identity_card) VALUES "
                "(%s, %s), (%s, %s)",
                (
                    "G13 staff one",
                    identity_prefix + "-1",
                    "G13 staff two",
                    identity_prefix + "-2",
                ),
            )
            cursor.execute(
                "SELECT id FROM staff WHERE identity_card IN (%s, %s) "
                "ORDER BY id",
                (identity_prefix + "-1", identity_prefix + "-2"),
            )
            staff_ids = [row["id"] for row in cursor.fetchall()]
        connection.commit()
        return staff_ids
    finally:
        connection.close()


def _lock_in_parallel(
    staff_ids: list[int],
    start: Barrier,
    results: Queue,
) -> None:
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET innodb_lock_wait_timeout = 5")
            cursor.execute("START TRANSACTION")
            start.wait(timeout=5)
            locked_ids = lock_staff_occupancy_mutex(cursor, staff_ids)
            sleep(0.1)
        connection.commit()
        results.put(("locked", locked_ids))
    except Exception as exc:
        connection.rollback()
        results.put(("error", type(exc).__name__, str(exc)))
    finally:
        connection.close()


def test_g13_reverse_staff_sets_lock_in_one_canonical_order_without_deadlock():
    bootstrap(_bootstrap_arguments())
    staff_ids = _seed_staff()
    start = Barrier(2)
    results: Queue = Queue()
    first = Thread(target=_lock_in_parallel, args=([staff_ids[1], staff_ids[0]], start, results))
    second = Thread(target=_lock_in_parallel, args=([staff_ids[0], staff_ids[1]], start, results))

    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)

    assert not first.is_alive()
    assert not second.is_alive()
    outcomes = [results.get_nowait(), results.get_nowait()]
    assert outcomes == [("locked", staff_ids), ("locked", staff_ids)]
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM staff WHERE id IN (%s, %s)",
                tuple(staff_ids),
            )
            assert cursor.fetchone() == {"count": 2}
    finally:
        connection.close()
