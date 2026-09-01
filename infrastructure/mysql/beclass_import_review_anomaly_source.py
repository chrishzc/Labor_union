"""
File: beclass_import_review_anomaly_source.py
Description: 保留舊 BeClass anomaly rescan 入口的相容形狀；不再建立 anomaly projection。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BeClassReviewAnomalyPage:
    projected_count: int
    next_review_row_id: int | None


def project_beclass_import_review_page(
    connection, *, after_review_row_id: int = 0, limit: int = 25
) -> BeClassReviewAnomalyPage:
    """Return an empty page after BeClass moved to Case Import owner follow-up.

    Case Import review rows and its outbox remain authoritative. Anomalies
    must not materialize the former Anomalies projection.
    """
    del connection, after_review_row_id
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    return BeClassReviewAnomalyPage(0, None)


__all__ = ["BeClassReviewAnomalyPage", "project_beclass_import_review_page"]
