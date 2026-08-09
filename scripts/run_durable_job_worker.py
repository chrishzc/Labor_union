"""Run the independently supervised durable-command worker process."""

from __future__ import annotations

import argparse
import os
import socket
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.mysql.background_job_repository import (
    BackgroundJobRepository,
    DurableJobSchemaNotReady,
)
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers


def main() -> int:
    arguments = _parse_arguments()
    if not _queue_schema_is_ready():
        return 2
    if arguments.check:
        print("durable job queue schema is ready")
        return 0
    worker_id = arguments.worker_id or socket.gethostname() + ":" + str(os.getpid())
    while True:
        connection = get_connection()
        try:
            worker = DurableJobWorker(
                BackgroundJobRepository(connection),
                default_job_handlers(),
                worker_id,
                arguments.lease_seconds,
                arguments.retry_delay_seconds,
            )
            processed = worker.recover_and_run_once()
        finally:
            connection.close()
        if arguments.once:
            return 0
        if not processed:
            time.sleep(arguments.poll_seconds)


def _queue_schema_is_ready() -> bool:
    connection = get_connection()
    try:
        BackgroundJobRepository(connection).assert_durable_queue_schema()
        return True
    except DurableJobSchemaNotReady as error:
        print(error)
        return False
    finally:
        connection.close()


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run durable background jobs.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--poll-seconds", type=int, default=2)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--retry-delay-seconds", type=int, default=15)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
