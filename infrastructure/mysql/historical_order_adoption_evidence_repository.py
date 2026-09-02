"""Read the latest immutable Historical Orders adoption receipt and pairing evidence."""

from __future__ import annotations

from datetime import date
import json
from typing import Mapping

from subsystems.orders.historical_adoption_evidence_query import (
    HistoricalAdoptionPairedStaffEvidence,
    HistoricalOrderAdoptionEvidence,
)


_VISIBLE_PAIRING_RESOLUTIONS = {
    "evidence_only",
    "assignment_candidate",
    "assignment_reused",
}


class MySqlHistoricalOrderAdoptionEvidenceRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def fetch_latest_adopted(self, case_no: str) -> HistoricalOrderAdoptionEvidence | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT receipt.id,receipt.case_no,receipt.source_event_identity,"
                "receipt.source_fingerprint,receipt.preview_fingerprint,receipt.result_snapshot,"
                "lifecycle.facts_snapshot AS lifecycle_facts_snapshot "
                "FROM historical_order_adoption_receipts receipt "
                "LEFT JOIN order_lifecycle_state_events lifecycle "
                "ON lifecycle.id=receipt.lifecycle_event_id "
                "WHERE receipt.case_no=%s AND receipt.outcome='adopted' "
                "ORDER BY receipt.id DESC LIMIT 1",
                (case_no,),
            )
            receipt = cursor.fetchone()
        if receipt is None:
            return None

        receipt_id = _positive_int(receipt.get("id"), "receipt_id")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT caregiver_ordinal,masked_staff_name,staff_id,resolution,"
                "source_start_date,source_end_date,assignment_id "
                "FROM historical_order_pairing_evidence "
                "WHERE receipt_id=%s ORDER BY caregiver_ordinal,id",
                (receipt_id,),
            )
            pairing_rows = tuple(cursor.fetchall() or ())

        result_snapshot = _json_object(receipt.get("result_snapshot"))
        lifecycle_snapshot = _json_object(receipt.get("lifecycle_facts_snapshot"))
        source_start_date, source_end_date = _source_period(pairing_rows, lifecycle_snapshot)
        paired_staff = tuple(
            _paired_staff(row)
            for row in pairing_rows
            if row.get("staff_id") is not None
            and str(row.get("resolution")) in _VISIBLE_PAIRING_RESOLUTIONS
        )
        return HistoricalOrderAdoptionEvidence(
            case_no=str(receipt["case_no"]),
            receipt_id=receipt_id,
            receipt_identity=f"historical-order-adoption-receipt:{receipt_id}",
            source_identity=_required_text(receipt.get("source_event_identity"), "source_identity"),
            source_fingerprint=_required_sha(receipt.get("source_fingerprint"), "source_fingerprint"),
            preview_fingerprint=_required_sha(receipt.get("preview_fingerprint"), "preview_fingerprint"),
            evidence_owner="Historical Orders Adoption",
            historical_source_status=_optional_text(result_snapshot.get("historical_source_status")),
            operational_baseline_step=_optional_step(result_snapshot.get("operational_baseline_step")),
            source_start_date=source_start_date,
            source_end_date=source_end_date,
            source_period_availability=(
                "available"
                if source_start_date is not None or source_end_date is not None
                else "unavailable"
            ),
            paired_staff=paired_staff,
            paired_staff_availability="available" if paired_staff else "unavailable",
        )


def _paired_staff(row: Mapping[str, object]) -> HistoricalAdoptionPairedStaffEvidence:
    resolution = str(row.get("resolution"))
    if resolution not in _VISIBLE_PAIRING_RESOLUTIONS:
        raise ValueError("historical_order_pairing_resolution_invalid")
    return HistoricalAdoptionPairedStaffEvidence(
        caregiver_ordinal=_positive_int(row.get("caregiver_ordinal"), "caregiver_ordinal"),
        masked_staff_name=_required_text(row.get("masked_staff_name"), "masked_staff_name"),
        staff_id=_positive_int(row.get("staff_id"), "staff_id"),
        resolution=resolution,  # type: ignore[arg-type]
        source_start_date=_optional_date(row.get("source_start_date")),
        source_end_date=_optional_date(row.get("source_end_date")),
        assignment_id=_optional_positive_int(row.get("assignment_id"), "assignment_id"),
    )


def _source_period(
    pairing_rows: tuple[Mapping[str, object], ...],
    lifecycle_snapshot: Mapping[str, object],
) -> tuple[date | None, date | None]:
    starts = tuple(
        value
        for value in (_optional_date(row.get("source_start_date")) for row in pairing_rows)
        if value is not None
    )
    ends = tuple(
        value
        for value in (_optional_date(row.get("source_end_date")) for row in pairing_rows)
        if value is not None
    )
    start = min(starts) if starts else None
    end = max(ends) if ends else None
    if start is not None or end is not None:
        return start, end

    date_patch = lifecycle_snapshot.get("date_patch")
    if isinstance(date_patch, (list, tuple)):
        patch = {
            item[0]: item[1]
            for item in date_patch
            if isinstance(item, (list, tuple)) and len(item) == 2
        }
        return (
            _optional_date(patch.get("actual_start_date")),
            _optional_date(patch.get("actual_end_date")),
        )
    return None, None


def _json_object(value: object) -> Mapping[str, object]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str):
        raise ValueError("historical_order_adoption_evidence_snapshot_invalid")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("historical_order_adoption_evidence_snapshot_invalid")
    return parsed


def _required_text(value: object, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"historical_order_adoption_evidence_{field}_invalid")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_sha(value: object, field: str) -> str:
    text = _required_text(value, field)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"historical_order_adoption_evidence_{field}_invalid")
    return text


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"historical_order_adoption_evidence_{field}_invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"historical_order_adoption_evidence_{field}_invalid") from error
    if result <= 0:
        raise ValueError(f"historical_order_adoption_evidence_{field}_invalid")
    return result


def _optional_positive_int(value: object, field: str) -> int | None:
    return None if value is None else _positive_int(value, field)


def _optional_step(value: object) -> int | None:
    if value is None:
        return None
    step = _positive_int(value, "operational_baseline_step")
    if step > 11:
        raise ValueError("historical_order_adoption_evidence_operational_baseline_step_invalid")
    return step


def _optional_date(value: object) -> date | None:
    if value is None or type(value) is date:
        return value
    return date.fromisoformat(str(value))


__all__ = ["MySqlHistoricalOrderAdoptionEvidenceRepository"]
