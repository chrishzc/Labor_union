"""Daily bounded mover for audit records outside the two-year online window."""

from __future__ import annotations

import asyncio

from subsystems.access.security_audit_query import archive_expired_admin_audits


_ARCHIVE_INTERVAL_SECONDS = 24 * 60 * 60


def start_security_audit_retention_worker() -> asyncio.Task[None]:
    return asyncio.create_task(_run_retention_loop())


async def stop_security_audit_retention_worker(task: asyncio.Task[None]) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def _run_retention_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(_archive_all_due_records)
        except Exception as exc:
            print(f"[Admin Audit] Retention archive failed: {exc}")
        await asyncio.sleep(_ARCHIVE_INTERVAL_SECONDS)


def archive_due_security_audits_once() -> int:
    """Archive all currently due pages and return the moved row count."""
    archived_count = 0
    while True:
        moved_count = archive_expired_admin_audits()
        archived_count += moved_count
        if moved_count <= 0:
            return archived_count


def _archive_all_due_records() -> None:
    archive_due_security_audits_once()
