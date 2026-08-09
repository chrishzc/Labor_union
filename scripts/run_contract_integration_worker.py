"""Run the independently restartable Contract Integration evidence worker."""

from __future__ import annotations

import argparse
import os
import socket
import time
from datetime import datetime, timezone

from infrastructure.mysql.contract_integration_unit_of_work import (
    open_contract_integration_unit_of_work,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from subsystems.contract_integration.application import ContractEvidenceWorker


def main() -> int:
    arguments = _arguments()
    worker_id = arguments.worker_id or f"contract:{socket.gethostname()}:{os.getpid()}"
    worker = ContractEvidenceWorker(open_contract_integration_unit_of_work, worker_id)
    while True:
        processed = worker.run_once()
        _heartbeat(worker_id, processed)
        if arguments.once:
            return 0
        time.sleep(0.1 if processed else arguments.poll_seconds)


def _heartbeat(worker_id: str, processed: int) -> None:
    connection = get_connection()
    try:
        connection.begin()
        MySqlRuntimeMonitorRepository(connection).record_heartbeat(
            "contract-integration-worker", worker_id, os.getpid(), socket.gethostname(),
            "running", {"processed_last_cycle": processed}, datetime.now(timezone.utc),
        )
        connection.commit()
    finally:
        connection.close()


def _arguments():
    parser = argparse.ArgumentParser(description="Run Contract Integration worker")
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())

