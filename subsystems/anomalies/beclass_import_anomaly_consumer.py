"""Retired BeClass-to-Anomalies compatibility boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domains.anomalies.registry import CurrentAlertProjection
from subsystems.anomalies.alert_workflow import AnomalyApplication


@dataclass(frozen=True, slots=True)
class BeClassImportReviewItem:
    definition_code: str
    review_item_id: str
    entity_kind: str
    source_sheet: str
    source_row: int
    error_codes: tuple[str, ...]
    source_version: int
    masked_identifier: str
    active: bool
    source_event_id: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        raise ValueError(
            "BeClass anomaly projection is retired; use Case Import owner follow-up"
        )


def consume_beclass_import_review_item(application: AnomalyApplication, review_item: BeClassImportReviewItem) -> CurrentAlertProjection | None:
    del application, review_item
    raise RuntimeError(
        "BeClass anomaly projection is retired; use Case Import owner follow-up"
    )
