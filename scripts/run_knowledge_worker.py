"""Run the independently restartable Knowledge Retrieval index/answer worker."""

from __future__ import annotations

import argparse
import os
import socket
import time
from datetime import datetime, timezone

from infrastructure.knowledge.chroma_gateway import ChromaKnowledgeGateway
from infrastructure.mysql.knowledge_retrieval_unit_of_work import (
    open_knowledge_retrieval_unit_of_work,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from subsystems.knowledge_retrieval.application import KnowledgeWorker


def main() -> int:
    arguments = _arguments()
    worker_id = arguments.worker_id or f"knowledge:{socket.gethostname()}:{os.getpid()}"
    gateway = ChromaKnowledgeGateway(os.getenv("KNOWLEDGE_CHROMA_PATH", "db/chroma_knowledge"))
    worker = KnowledgeWorker(open_knowledge_retrieval_unit_of_work, gateway, worker_id)
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
            "knowledge-retrieval-worker", worker_id, os.getpid(), socket.gethostname(),
            "running", {"processed_last_cycle": processed}, datetime.now(timezone.utc),
        )
        connection.commit()
    finally:
        connection.close()


def _arguments():
    parser = argparse.ArgumentParser(description="Run Knowledge Retrieval worker")
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
