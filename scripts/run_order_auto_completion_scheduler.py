"""Enqueue due G05 Orders completion commands for the durable job worker."""

from __future__ import annotations

import argparse
import time

from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.order_auto_completion_job_repository import (
    MySqlDueOrderAutoCompletionRepository,
)
from shared_kernel.clock import SystemBusinessClock
from subsystems.orders.auto_completion_job_dispatch import AutoCompletionJobDispatcher


def main() -> None:
    arguments = _parse_arguments()
    while True:
        receipt = _dispatch_once(arguments.page_size)
        if arguments.once:
            return
        if receipt.enqueued_count == 0:
            time.sleep(arguments.poll_seconds)


def _dispatch_once(page_size: int):
    connection = get_connection()
    try:
        dispatcher = AutoCompletionJobDispatcher(
            MySqlDueOrderAutoCompletionRepository(connection),
            BackgroundJobRepository(connection),
        )
        return dispatcher.dispatch_due_orders(SystemBusinessClock().now(), page_size)
    finally:
        connection.close()


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enqueue due Orders service-completion jobs.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--page-size", type=int, default=100)
    arguments = parser.parse_args()
    if arguments.poll_seconds < 1:
        parser.error("--poll-seconds must be positive")
    if not 1 <= arguments.page_size <= 200:
        parser.error("--page-size must be between 1 and 200")
    return arguments


if __name__ == "__main__":
    main()
