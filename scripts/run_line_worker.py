"""Run the independently supervised LINE private-API client."""

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


# Keep one-shot and supervised-loop exit semantics visible in the CLI entrypoint.
def main() -> int:
    discard_database_credentials()
    arguments = _arguments()
    worker_id = arguments.worker_id or f"{socket.gethostname()}:{os.getpid()}"
    identity = runtime_identity("line-worker", worker_id)
    client = PrivateOperationsClient("line-worker")
    while True:
        try:
            processed = client.run_line_cycle(
                {"worker_id": worker_id, "runtime_identity": identity}
            )
        except PrivateOperationError as error:
            if not error.retryable:
                print(f"[LINE WORKER] {error}", flush=True)
                return 2
            print(f"[LINE WORKER] retryable error: {error}", flush=True)
            if arguments.once:
                return 1
            processed = 0
        if arguments.once:
            return 0
        time.sleep(0.1 if processed else arguments.poll_seconds)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LINE workers through the private API.")
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
