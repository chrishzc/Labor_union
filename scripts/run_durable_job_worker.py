"""Run the independently supervised durable-command API client process."""

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
    arguments = _parse_arguments()
    worker_id = arguments.worker_id or f"{socket.gethostname()}:{os.getpid()}"
    identity = runtime_identity("durable-job-worker", worker_id)
    client = PrivateOperationsClient("durable-job-worker")
    if arguments.check:
        return _run_check(client, worker_id, identity, arguments)
    while True:
        try:
            processed = client.run_durable_cycle(_cycle_payload(worker_id, identity, arguments))
        except PrivateOperationError as error:
            if not error.retryable:
                print(f"[DURABLE WORKER] {error}", flush=True)
                return 2
            print(f"[DURABLE WORKER] retryable error: {error}", flush=True)
            if arguments.once:
                return 1
            processed = 0
        if arguments.once:
            return 0
        if not processed:
            time.sleep(arguments.poll_seconds)


def _run_check(client, worker_id: str, identity, arguments: argparse.Namespace) -> int:
    payload = _cycle_payload(worker_id, identity, arguments)
    payload["check_only"] = True
    try:
        client.run_durable_cycle(payload)
    except PrivateOperationError as error:
        print(f"[DURABLE WORKER] {error}", flush=True)
        return 2
    print("durable job private API and queue schema are ready")
    return 0


def _cycle_payload(worker_id: str, identity, arguments: argparse.Namespace) -> dict[str, object]:
    return {
        "worker_id": worker_id,
        "runtime_identity": identity,
        "lease_seconds": arguments.lease_seconds,
        "retry_delay_seconds": arguments.retry_delay_seconds,
        "check_only": False,
    }


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run durable background jobs through the private API.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--worker-id", default="")
    parser.add_argument("--poll-seconds", type=int, default=2)
    parser.add_argument("--lease-seconds", type=int, default=60)
    parser.add_argument("--retry-delay-seconds", type=int, default=15)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
