"""Production assembly for BeClass import review Query, Preview, and Apply."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re

from pymysql.err import IntegrityError, OperationalError

from domains.case_import.beclass_import_review import BeClassImportSourceKind
from infrastructure.mysql.beclass_import_review_repository import (
    BeClassImportReviewMySqlUnitOfWork,
    MySqlBeClassImportReviewRepository,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.validation import require_canonical_text
from subsystems.case_import.beclass_import_review_workflow import (
    BeClassImportReviewStorageError,
    BeClassImportReviewWorkflow,
    BeClassImportReviewWriteReceipt,
    BeClassImportReviewWriterError,
)


_CLIENT_COLUMNS = frozenset({"admin_notes", "address", "birth_date", "city", "created_at", "email", "ext", "name", "phone", "query_no", "refund_account_no", "refund_bank_code", "seq_num", "survey_details", "tel", "zip_code"})
_STAFF_COLUMNS = frozenset({"address", "birthday", "care_babies", "city", "email", "has_massage_cert", "identity_card", "ip_address", "name", "phone", "registered_at", "service_regions", "special_skills", "status", "tel", "tel_ext", "weekly_rest_days", "zip_code"})


@dataclass(frozen=True)
class BeClassImportReviewApplication:
    workflow: BeClassImportReviewWorkflow

    def query(self, review_identity, correlation_id):
        return self.workflow.query(review_identity, correlation_id)

    def preview(self, intent, correlation_id):
        return self.workflow.preview(intent, correlation_id)

    def apply(self, command):
        return self.workflow.apply(command)


class MySqlBeClassImportReviewWriter:
    def __init__(self, connection) -> None:
        self._connection = connection

    def apply_corrected_row(self, candidate):
        table_name, identity_field, identity_length, allowed_columns = _target(candidate.source_kind)
        payload = dict(candidate.corrected_payload)
        _validate_payload(payload, candidate.source_kind, allowed_columns)
        identity = require_canonical_text(payload[identity_field], identity_field, identity_length)
        try:
            with self._connection.cursor() as cursor:
                _require_absent(cursor, table_name, identity_field, identity)
                _insert_payload(cursor, table_name, payload)
        except OperationalError as error:
            code = int(error.args[0]) if error.args else 0
            raise BeClassImportReviewStorageError(
                "BeClass owning record write failed.", retryable=code in {1205, 1213}
            ) from error
        except IntegrityError as error:
            raise _writer_conflict() from error
        return BeClassImportReviewWriteReceipt(identity)


def build_beclass_import_review_application(connection) -> BeClassImportReviewApplication:
    repository = MySqlBeClassImportReviewRepository(connection)
    writer = MySqlBeClassImportReviewWriter(connection)
    workflow = BeClassImportReviewWorkflow(
        repository, writer, lambda: BeClassImportReviewMySqlUnitOfWork(connection)
    )
    return BeClassImportReviewApplication(workflow)


def _target(source_kind):
    if source_kind is BeClassImportSourceKind.CLIENT:
        return "beclass_records", "query_no", 50, _CLIENT_COLUMNS
    if source_kind is BeClassImportSourceKind.STAFF:
        return "staff", "identity_card", 20, _STAFF_COLUMNS
    raise ValueError("beclass_import_review_source_kind_invalid")


def _validate_payload(payload, source_kind, allowed_columns) -> None:
    if set(payload) - allowed_columns:
        raise _invalid_fields()
    if source_kind is BeClassImportSourceKind.STAFF:
        _validate_staff_business_fields(payload)
        return
    _validate_client_business_fields(payload)


def _validate_client_business_fields(payload) -> None:
    _require_text_fields(payload, ("query_no", "name", "created_at", "phone"))
    _require_phone(payload["phone"])
    _require_date(payload.get("birth_date"), "birth_date")


def _validate_staff_business_fields(payload) -> None:
    _require_text_fields(payload, ("identity_card", "name", "registered_at", "ip_address", "phone"))
    if not re.fullmatch(r"[A-Za-z]\d{9}", str(payload["identity_card"])):
        raise _invalid_fields()
    _require_phone(payload["phone"])
    _require_date(payload.get("birthday"), "birthday")


def _require_text_fields(payload, field_names) -> None:
    try:
        for field_name in field_names:
            require_canonical_text(payload.get(field_name), field_name, 191)
    except ValueError as error:
        raise _invalid_fields() from error


def _require_phone(value) -> None:
    if not re.fullmatch(r"09\d{8}", str(value or "")):
        raise _invalid_fields()


def _require_date(value, field_name) -> None:
    try:
        date.fromisoformat(str(value))
    except (TypeError, ValueError) as error:
        raise _invalid_fields() from error


def _invalid_fields():
    return BeClassImportReviewWriterError(
        "beclass_import_review_corrected_fields_invalid", ErrorCategory.VALIDATION
    )


def _require_absent(cursor, table_name, identity_field, identity) -> None:
    cursor.execute(
        f"SELECT id FROM `{table_name}` WHERE `{identity_field}`=%s FOR UPDATE",
        (identity,),
    )
    if cursor.fetchone() is not None:
        raise _writer_conflict()


def _insert_payload(cursor, table_name, payload) -> None:
    ordered_columns = tuple(sorted(payload))
    if not ordered_columns:
        raise BeClassImportReviewWriterError(
            "beclass_import_review_corrected_fields_required", ErrorCategory.VALIDATION
        )
    column_sql = ",".join(f"`{column}`" for column in ordered_columns)
    placeholder_sql = ",".join(["%s"] * len(ordered_columns))
    cursor.execute(
        f"INSERT INTO `{table_name}` ({column_sql}) VALUES ({placeholder_sql})",
        tuple(payload[column] for column in ordered_columns),
    )
    if int(cursor.rowcount) != 1:
        raise RuntimeError("beclass_import_review_owning_write_failed")


def _writer_conflict():
    return BeClassImportReviewWriterError(
        "beclass_import_review_owning_record_conflict", ErrorCategory.CONFLICT
    )


__all__ = [
    "BeClassImportReviewApplication",
    "MySqlBeClassImportReviewWriter",
    "build_beclass_import_review_application",
]
