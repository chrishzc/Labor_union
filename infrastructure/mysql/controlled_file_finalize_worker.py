"""Bounded MySQL runner for 1015 controlled-file finalize intents."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from infrastructure.db.controlled_file_reference_finalize_repository import (
    MySqlControlledFileReferenceFinalizeRepository,
)
from subsystems.controlled_files.reference_finalize import (
    ControlledFileFinalizeWorker,
)


class MySqlControlledFileFinalizeRunner:
    """Claim and verify at most ``limit`` pending finalize intents.

    Each intent gets a short-lived connection.  The finalize worker commits its
    claim/lease/CAS checkpoints before and after the storage call, so provider
    access never occurs inside an open MySQL transaction.
    """

    def __init__(
        self,
        connection_factory: Callable[[], object],
        storage,
        worker_id: str,
        now: Callable[[], datetime],
        *,
        limit: int = 100,
    ) -> None:
        if not worker_id.strip():
            raise ValueError("controlled file finalize worker identity is required")
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("controlled file finalize limit must be between 1 and 100")
        self._connection_factory = connection_factory
        self._storage = storage
        self._worker_id = worker_id
        self._now = now
        self._limit = limit

    def run_once(self) -> int:
        observed_at = self._now()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("controlled file finalize time must be timezone-aware")
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT finalize_id
                    FROM controlled_file_finalize_intents
                    WHERE finalize_state IN ('pending','reconciliation_required')
                       OR (finalize_state='processing'
                           AND claimed_at_utc < %s)
                    ORDER BY id
                    LIMIT %s
                    """,
                    (
                        (observed_at - timedelta(hours=24)).astimezone(timezone.utc).replace(tzinfo=None),
                        self._limit,
                    ),
                )
                rows = cursor.fetchall() or ()
            finalize_ids = tuple(str(row["finalize_id"]) for row in rows)
        finally:
            connection.close()

        processed = 0
        for finalize_id in finalize_ids:
            connection = self._connection_factory()
            try:
                repository = MySqlControlledFileReferenceFinalizeRepository(connection)
                ControlledFileFinalizeWorker(
                    repository,
                    self._storage,
                    checkpoint=connection.commit,
                ).run(
                    finalize_id,
                    worker_id=self._worker_id,
                    observed_at=observed_at,
                )
                processed += 1
            finally:
                connection.close()
        return processed


__all__ = ["MySqlControlledFileFinalizeRunner"]
