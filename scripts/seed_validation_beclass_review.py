"""Seed one invalid BeClass row, then repair it through the owning workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domains.case_import.beclass_import_review import (
    BeClassImportReviewIntent,
    BeClassImportReviewStatus,
    BeClassImportSourceKind,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.anomaly_runtime import build_anomaly_runtime
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.case_import.beclass_import_outbox_consumer import (
    consume_beclass_import_review_events,
)
from subsystems.case_import.beclass_import_review_workflow import (
    ApplyBeClassImportReview,
)
from api.dependencies.beclass_import_review import build_beclass_import_review_application
from infrastructure.mysql.beclass_import_review_repository import MySqlBeClassImportReviewRepository
from subsystems.case_import.beclass_review_intake import record_invalid_beclass_row


_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")
_FIXTURE_PATH = PROJECT_ROOT / "validation" / "external_inputs" / "beclass_invalid_client_v1.json"
_OPEN_FIXTURE_PATH = PROJECT_ROOT / "validation" / "external_inputs" / "beclass_invalid_client_open_v1.json"


def seed() -> dict[str, object]:
    _require_dataset_database()
    fixture, source_digest = _fixture(_FIXTURE_PATH)
    review_identity = _record_invalid_root(fixture, source_digest)
    _deliver_outbox()
    _repair_if_open(review_identity, fixture)
    _deliver_outbox()
    return _verify(review_identity, fixture)


def seed_open_review() -> dict[str, object]:
    """Create a review item that an operator can repair from the existing UI."""
    _require_dataset_database()
    fixture, source_digest = _fixture(_OPEN_FIXTURE_PATH)
    review_identity = _record_invalid_root(fixture, source_digest)
    _deliver_outbox()
    return _verify_open(review_identity, fixture)


def _require_dataset_database() -> None:
    from infrastructure.mysql.mysql_adapter import DB_CONFIG

    if not _DATABASE_PATTERN.fullmatch(str(DB_CONFIG["database"])):
        raise ValueError("DB_DATABASE must match lu_test_dataset_[a-z0-9_]+")
    if os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}:
        raise ValueError("validation dataset seed requires a development validation profile")


def _fixture(path: Path) -> tuple[dict[str, object], str]:
    content = path.read_bytes()
    fixture = json.loads(content.decode("utf-8"))
    if not isinstance(fixture, dict):
        raise ValueError("BeClass validation fixture must be an object")
    return fixture, hashlib.sha256(content).hexdigest()


def _record_invalid_root(fixture: dict[str, object], source_digest: str) -> str:
    connection = get_connection()
    try:
        review_identity = record_invalid_beclass_row(
            connection,
            source_kind=BeClassImportSourceKind(str(fixture["source_kind"])),
            source_content_digest=source_digest,
            source_sheet=str(fixture["source_sheet"]),
            source_row=int(fixture["source_row"]),
            masked_identifier=str(fixture["masked_identifier"]),
            source_payload=_object(fixture, "source_payload"),
            issue_codes=_text_items(fixture, "issue_codes"),
            repository=MySqlBeClassImportReviewRepository(connection),
        )
        connection.commit()
        return review_identity
    finally:
        connection.close()


def _deliver_outbox() -> None:
    connection = get_connection()
    try:
        result = consume_beclass_import_review_events(
            connection,
            runtime=build_anomaly_runtime(),
        )
    finally:
        connection.close()
    if result.failed_count:
        raise RuntimeError("BeClass review outbox delivery failed")


def _repair_if_open(review_identity: str, fixture: dict[str, object]) -> None:
    connection = get_connection()
    try:
        application = build_beclass_import_review_application(connection)
        query = application.query(review_identity, CorrelationId("validation-beclass-query"))
        if query.facts.status is BeClassImportReviewStatus.RESOLVED:
            return
        preview = application.preview(
            BeClassImportReviewIntent(
                review_identity,
                _object(fixture, "corrected_payload"),
                _text_items(fixture, "issue_codes"),
            ),
            CorrelationId("validation-beclass-preview"),
        )
        command = ApplyBeClassImportReview(
            BeClassImportReviewIntent(
                review_identity,
                _object(fixture, "corrected_payload"),
                _text_items(fixture, "issue_codes"),
            ),
            ExpectedVersion(preview.expected_version.value),
            preview.fingerprint,
            IdempotencyKey("validation-beclass-review-apply"),
            ActorContext("validation-dataset-seed"),
            "repair invalid phone from source evidence",
            CorrelationId("validation-beclass-apply"),
        )
        receipt = application.apply(command)
        if application.apply(command) != receipt:
            raise RuntimeError("BeClass review replay returned a different receipt")
    finally:
        connection.close()


def _verify(review_identity: str, fixture: dict[str, object]) -> dict[str, object]:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT event.resulting_version FROM beclass_import_review_rows root "
                "JOIN beclass_import_review_events event ON event.review_row_id=root.id "
                "WHERE root.review_identity=%s",
                (review_identity,),
            )
            review = cursor.fetchone()
            cursor.execute(
                "SELECT workflow_status,predicate_active FROM anomaly_current_alerts "
                "WHERE definition_code='IMPORT-001' AND source_identity=%s",
                (review_identity,),
            )
            alert = cursor.fetchone()
            query_no = str(_object(fixture, "corrected_payload")["query_no"])
            cursor.execute("SELECT COUNT(*) AS count FROM beclass_records WHERE query_no=%s", (query_no,))
            record_count = int(cursor.fetchone()["count"])
    finally:
        connection.close()
    if review is None or alert is None or record_count != 1:
        raise RuntimeError("BeClass validation review scenario was not fully repaired")
    return {
        "review_identity": review_identity,
        "review_version": int(review["resulting_version"]),
        "alert_workflow_status": str(alert["workflow_status"]),
        "alert_predicate_active": int(alert["predicate_active"]),
        "beclass_record_count": record_count,
    }


def _verify_open(review_identity: str, fixture: dict[str, object]) -> dict[str, object]:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM beclass_import_review_events event "
                "JOIN beclass_import_review_rows root ON root.id=event.review_row_id "
                "WHERE root.review_identity=%s",
                (review_identity,),
            )
            event_count = int(cursor.fetchone()["count"])
            cursor.execute(
                "SELECT workflow_status,predicate_active FROM anomaly_current_alerts "
                "WHERE definition_code='IMPORT-001' AND source_identity=%s",
                (review_identity,),
            )
            alert = cursor.fetchone()
            query_no = str(_object(fixture, "source_payload")["query_no"])
            cursor.execute("SELECT COUNT(*) AS count FROM beclass_records WHERE query_no=%s", (query_no,))
            record_count = int(cursor.fetchone()["count"])
    finally:
        connection.close()
    if alert is None or event_count != 0 or record_count != 0:
        raise RuntimeError("BeClass validation review scenario did not remain open")
    return {
        "review_identity": review_identity,
        "review_version": 0,
        "alert_workflow_status": str(alert["workflow_status"]),
        "alert_predicate_active": int(alert["predicate_active"]),
        "beclass_record_count": record_count,
    }


def _object(source: dict[str, object], field: str) -> dict[str, object]:
    value = source[field]
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _text_items(source: dict[str, object], field: str) -> tuple[str, ...]:
    value = source[field]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a list of text")
    return tuple(sorted(value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    print(seed())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
