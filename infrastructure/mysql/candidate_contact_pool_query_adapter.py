"""
File: candidate_contact_pool_query_adapter.py
Description: 以借用連線提供 M3 唯讀 candidate-pool typed query boundary。
"""

from __future__ import annotations

from typing import Any

from subsystems.scheduling.candidate_contact_pool_workflow import (
    CandidateContactPoolState,
    query_pool,
)


class MySqlCandidateContactPoolQueryAdapter:
    """Read the owner pool without commit, rollback, or connection ownership."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_candidate_pool(
        self, case_no: str, *, for_update: bool = False
    ) -> CandidateContactPoolState:
        return query_pool(
            case_no,
            connection=self._connection,
            for_update=for_update,
        )

    def load_staff_ids(self, case_no: str) -> tuple[int, ...]:
        """Return the current pool lock set in deterministic owner identity order."""

        pool = self.load_candidate_pool(case_no)
        return tuple(sorted({candidate.staff_id for candidate in pool.candidates}))


__all__ = ["MySqlCandidateContactPoolQueryAdapter"]
