"""Run the independently supervised durable-command worker process."""

from __future__ import annotations

import argparse
import os
import socket
import time

from infrastructure.mysql.background_job_repository import BackgroundJobRepository
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.jobs.durable_job_worker import DurableJobWorker, default_job_handlers


def main() -> None:
    arguments = _parse_arguments()
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
            return
        if not processed:
            time.sleep(arguments.poll_seconds)


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run durable background jobs.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--poll-seconds", type=int, default=2)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--retry-delay-seconds", type=int, default=15)
    return parser.parse_args()


if __name__ == "__main__":
    main()
