"""Project bounded BeClass import-review facts into canonical anomalies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domains.anomalies.registry import CurrentAlertProjection, DesiredAlertState
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer, require_positive_integer
from subsystems.anomalies.alert_workflow import AnomalyApplication, ProjectAlertRequest


_SUPPORTED_DEFINITION_CODES = frozenset({"IMPORT-001", "IMPORT-003"})
_TEXT_MAXIMUM_LENGTH = 191


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
        _validate_definition_code(self.definition_code)
        _validate_text_fields(self)
        require_positive_integer(self.source_row, "source row")
        require_nonnegative_integer(self.source_version, "source version")
        _validate_error_codes(self.error_codes)
        _validate_active_flag(self.active)
        _validate_occurred_at(self.occurred_at)


def consume_beclass_import_review_item(application: AnomalyApplication, review_item: BeClassImportReviewItem) -> CurrentAlertProjection | None:
    return application.project(_project_request(review_item))


def _project_request(review_item: BeClassImportReviewItem) -> ProjectAlertRequest:
    source_identity = _review_source_identity(review_item.review_item_id)
    return ProjectAlertRequest(
        desired=_desired_state(review_item),
        source_event_identity=review_item.source_event_id,
        consumer_identity="beclass-import-anomaly-projector-v1",
        partition_identity=f"{review_item.definition_code}:{source_identity}",
        display_snapshot=_display_snapshot(review_item),
    )


def _desired_state(review_item: BeClassImportReviewItem) -> DesiredAlertState:
    return DesiredAlertState(
        definition_code=review_item.definition_code,
        source_identity=_review_source_identity(review_item.review_item_id),
        source_version=review_item.source_version,
        active=review_item.active,
        fingerprint_values={"entity_kind": review_item.entity_kind, "review_item_id": review_item.review_item_id},
    )


def _review_source_identity(review_item_id: str) -> str:
    return review_item_id if review_item_id.startswith("beclass-review:") else f"beclass-review:{review_item_id}"


def _display_snapshot(review_item: BeClassImportReviewItem) -> dict[str, object]:
    return {
        "review_item_id": review_item.review_item_id,
        "entity_kind": review_item.entity_kind,
        "source_sheet": review_item.source_sheet,
        "source_row": review_item.source_row,
        "error_codes": review_item.error_codes,
        "version": review_item.source_version,
        "masked_identifier": review_item.masked_identifier,
    }


def _validate_definition_code(value: str) -> None:
    if value not in _SUPPORTED_DEFINITION_CODES:
        raise ValueError("unsupported BeClass import anomaly definition")


def _validate_text_fields(review_item: BeClassImportReviewItem) -> None:
    for value, field in (
        (review_item.review_item_id, "review item id"),
        (review_item.entity_kind, "entity kind"),
        (review_item.source_sheet, "source sheet"),
        (review_item.masked_identifier, "masked identifier"),
        (review_item.source_event_id, "source event id"),
    ):
        require_canonical_text(value, field, _TEXT_MAXIMUM_LENGTH)


def _validate_error_codes(error_codes: tuple[str, ...]) -> None:
    if not isinstance(error_codes, tuple) or not error_codes:
        raise ValueError("error codes must be a non-empty tuple")
    if error_codes != tuple(sorted(set(error_codes))):
        raise ValueError("error codes must be sorted and unique")
    for error_code in error_codes:
        require_canonical_text(error_code, "error code", _TEXT_MAXIMUM_LENGTH)


def _validate_active_flag(active: bool) -> None:
    if not isinstance(active, bool):
        raise TypeError("review item active flag must be bool")


def _validate_occurred_at(occurred_at: datetime) -> None:
    if not isinstance(occurred_at, datetime) or occurred_at.utcoffset() is None:
        raise ValueError("occurred at must be a timezone-aware datetime")
