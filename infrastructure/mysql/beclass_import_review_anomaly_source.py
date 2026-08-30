"""
File: beclass_import_review_anomaly_source.py
Description: 有界掃描 BeClass review 根事實並重建可衍生的 current anomaly projection。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone
import json

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import (
    AnomalyMySqlUnitOfWork,
    MySqlAnomalyRepository,
)
from subsystems.anomalies.alert_workflow import AnomalyApplication
from subsystems.anomalies.beclass_import_anomaly_consumer import (
    BeClassImportReviewItem,
    consume_beclass_import_review_item,
)


@dataclass(frozen=True, slots=True)
class BeClassReviewAnomalyPage:
    projected_count: int
    next_review_row_id: int | None


def project_beclass_import_review_page(
    connection, *, after_review_row_id: int = 0, limit: int = 25
) -> BeClassReviewAnomalyPage:
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    rows = _load_review_page(connection, after_review_row_id, limit)
    application = AnomalyApplication(
        default_anomaly_registry(),
        MySqlAnomalyRepository(connection),
        lambda: AnomalyMySqlUnitOfWork(connection),
    )
    for row in rows:
        consume_beclass_import_review_item(application, _review_item(row))
    next_row_id = int(rows[-1]["id"]) if len(rows) == limit else None
    return BeClassReviewAnomalyPage(len(rows), next_row_id)


def _load_review_page(connection, after_review_row_id, limit):
    with connection.cursor() as cursor:
        cursor.execute(_REVIEW_PAGE_SQL, (after_review_row_id, limit))
        return tuple(cursor.fetchall())


def _review_item(row) -> BeClassImportReviewItem:
    issues = _text_tuple(row["issue_codes"])
    version = int(row["resulting_version"] or 0)
    active = row["resulting_version"] is None
    review_identity = str(row["review_identity"])
    return BeClassImportReviewItem(
        definition_code=_definition_code(issues),
        review_item_id=review_identity,
        entity_kind=str(row["source_kind"]),
        source_sheet=str(row["source_sheet"]),
        source_row=int(row["source_row"]),
        error_codes=issues,
        source_version=version,
        masked_identifier=str(row["masked_identifier"]),
        active=active,
        source_event_id=f"beclass-review-rescan:{review_identity}:{version}:{int(active)}",
        occurred_at=row["created_at"].replace(tzinfo=timezone.utc),
    )


def _definition_code(issue_codes) -> str:
    markers = ("identity", "duplicate", "collision", "conflict")
    return "IMPORT-003" if any(marker in code.lower() for code in issue_codes for marker in markers) else "IMPORT-001"


def _text_tuple(value) -> tuple[str, ...]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list):
        raise ValueError("BeClass review issue codes must be an array")
    return tuple(sorted({str(item) for item in parsed}))


_REVIEW_PAGE_SQL = """
SELECT root.id,root.review_identity,root.source_kind,root.source_sheet,
       root.source_row,root.masked_identifier,root.issue_codes,root.created_at,
       latest.resulting_version
FROM beclass_import_review_rows AS root
LEFT JOIN beclass_import_review_events AS latest ON latest.id=(
    SELECT MAX(event.id) FROM beclass_import_review_events AS event
    WHERE event.review_row_id=root.id
)
WHERE root.id>%s
ORDER BY root.id
LIMIT %s
"""


__all__ = ["BeClassReviewAnomalyPage", "project_beclass_import_review_page"]
