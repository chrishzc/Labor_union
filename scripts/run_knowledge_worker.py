"""Run the independently restartable Knowledge Retrieval API client."""

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

from infrastructure.http.private_operations_client import (
    PrivateOperationError,
    PrivateOperationsClient,
    discard_database_credentials,
    runtime_identity,
)


def _deliver_line_messages(worker_identity: str) -> int:
    from datetime import datetime, timezone
    from api.dependencies.line_worker_operation import _required_access_token
    from infrastructure.line.messaging_api_adapter import LineMessagingApiAdapter
    from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
    from subsystems.line.delivery_worker import LineDeliveryWorker

    worker = LineDeliveryWorker(
        open_line_unit_of_work,
        LineMessagingApiAdapter(_required_access_token()),
        worker_identity,
        lambda: datetime.now(timezone.utc),
    )
    return worker.run_once()


# Keep one-shot and supervised-loop exit semantics visible in the CLI entrypoint.
def main() -> int:
    from api.dependencies.private_operations import run_knowledge_cycle
    from api.schemas.private_operations import WorkerRuntimeIdentity

    arguments = _arguments()
    worker_id = arguments.worker_id or f"knowledge:{socket.gethostname()}:{os.getpid()}"
    raw_identity = runtime_identity("knowledge-retrieval-worker", worker_id)
    identity = WorkerRuntimeIdentity.model_validate(raw_identity)

    print(f"[KNOWLEDGE WORKER] Started worker {worker_id}", flush=True)
    while True:
        processed = 0
        try:
            processed = run_knowledge_cycle(worker_id, identity)
            if processed:
                print(f"[KNOWLEDGE WORKER] Processed {processed} question(s). Delivering to LINE...", flush=True)
                sent = _deliver_line_messages(worker_id)
                print(f"[KNOWLEDGE WORKER] Delivered {sent} message(s) to LINE.", flush=True)
            else:
                # 即使無新提問，若有待發送訊息亦一併派送
                _deliver_line_messages(worker_id)
        except Exception as error:
            print(f"[KNOWLEDGE WORKER] Error: {error}", flush=True)
            if arguments.once:
                return 1
            processed = 0

        if arguments.once:
            return 0
        time.sleep(0.1 if processed else arguments.poll_seconds)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Knowledge Retrieval worker")
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
