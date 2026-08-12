"""MySQL owner for provisional LINE customer registration root facts."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable, Iterator, Mapping

from pymysql.err import IntegrityError, OperationalError

from domains.case_import.provisional_registration import ProvisionalRegistrationCandidate
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineUserId
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationConflict,
    ProvisionalRegistrationReceipt,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork


class ProvisionalRegistrationStorageError(RuntimeError):
    pass


class ProvisionalRegistrationMySqlUnitOfWork(MySqlUnitOfWork):
    def __enter__(self):
        try:
            return super().__enter__()
        except OperationalError as error:
            raise ProvisionalRegistrationStorageError("registration_transaction_start_failed") from error


class MySqlProvisionalRegistrationRepository:
    def __init__(
        self,
        connection,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._connection = connection
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._delivery_tasks = MySqlLineDeliveryTaskRepository(connection)

    def apply(self, candidate) -> ProvisionalRegistrationReceipt | ProvisionalRegistrationConflict:
        with _cursor(self._connection) as cursor:
            record = _claim_active_registration(cursor, candidate)
            if _has_different_payload(record, candidate):
                return _record_conflict(cursor, record, candidate)
            if _is_complete(record):
                return _receipt(record, candidate, replayed=True)
            client_id = _insert_client(cursor, candidate)
            beclass_record_id = _insert_beclass_record(cursor, candidate)
            self._enqueue_confirmation(candidate, int(record["id"]))
            _complete_registration(cursor, int(record["id"]), client_id, beclass_record_id)
            return ProvisionalRegistrationReceipt(
                int(record["id"]), client_id, beclass_record_id,
                str(candidate.client_payload["name"]), False, True,
            )

    def _enqueue_confirmation(self, candidate, registration_id) -> None:
        self._delivery_tasks.enqueue(
            _confirmation_request(candidate, registration_id, self._now())
        )


@contextmanager
def _cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except OperationalError as error:
        raise ProvisionalRegistrationStorageError("registration_database_unavailable") from error
    except IntegrityError as error:
        raise ProvisionalRegistrationStorageError("registration_database_conflict") from error


def _claim_active_registration(cursor, candidate):
    cursor.execute(_CLAIM_SQL, (candidate.line_user_id, candidate.line_user_id, candidate.payload_fingerprint.value))
    cursor.execute(_ACTIVE_SELECT_SQL, (candidate.line_user_id,))
    record = cursor.fetchone()
    if not isinstance(record, Mapping):
        raise ProvisionalRegistrationStorageError("registration_claim_missing")
    return record


def _has_different_payload(record, candidate) -> bool:
    return str(record["payload_fingerprint"]) != candidate.payload_fingerprint.value


def _record_conflict(cursor, record, candidate):
    cursor.execute(
        _CONFLICT_INSERT_SQL,
        (
            int(record["id"]),
            candidate.payload_fingerprint.value,
            json.dumps(_candidate_snapshot(candidate), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        ),
    )
    conflict_id = _last_insert_id(cursor, "registration_conflict_insert_failed")
    return ProvisionalRegistrationConflict(int(record["id"]), conflict_id)


def _is_complete(record) -> bool:
    return bool(record.get("client_id")) and bool(record.get("beclass_record_id"))


def _receipt(record, candidate, *, replayed):
    if not _is_complete(record):
        raise ProvisionalRegistrationStorageError("registration_receipt_incomplete")
    return ProvisionalRegistrationReceipt(
        int(record["id"]), int(record["client_id"]), int(record["beclass_record_id"]),
        str(candidate.client_payload["name"]), replayed, False,
    )


def _insert_client(cursor, candidate) -> int:
    payload = candidate.client_payload
    cursor.execute(
        "INSERT INTO clients (name,phone,address,service_days,due_month,line_user_id,gender,city) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        tuple(payload[name] for name in ("name", "phone", "address", "service_days", "due_month", "line_user_id", "gender", "city")),
    )
    return _last_insert_id(cursor, "provisional_registration_client_insert_failed")


def _insert_beclass_record(cursor, candidate) -> int:
    payload = candidate.beclass_payload
    survey = dict(payload["survey_details"])
    survey["_liff_meta"] = {**dict(survey["_liff_meta"]), "submitted_at": datetime.now(timezone.utc).isoformat()}
    cursor.execute(
        "INSERT INTO beclass_records (name,email,birth_date,phone,tel,ext,city,zip_code,address,created_at,survey_details) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(),%s)",
        tuple(payload[name] for name in ("name", "email", "birth_date", "phone", "tel", "ext", "city", "zip_code", "address"))
        + (json.dumps(survey, ensure_ascii=False, sort_keys=True, separators=(",", ":")),),
    )
    return _last_insert_id(cursor, "provisional_registration_beclass_insert_failed")


def _confirmation_request(candidate, registration_id, scheduled_at):
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId(candidate.line_user_id)),
        LineMessageKind.TEXT,
        canonical_line_payload_json(
            {"type": "text", "text": _confirmation_message(candidate)}
        ),
        scheduled_at,
        IdempotencyKey(f"line-registration:{registration_id}"),
        CorrelationId(f"line-registration:{registration_id}"),
        "provisional_registration",
        str(registration_id),
    )


def _confirmation_message(candidate) -> str:
    name = str(candidate.client_payload["name"])
    return (
        f"【系統通知】\n服務登記與綁定成功！您的 LINE 帳號已連結至客戶「{name}」的專屬資料庫。\n"
        "您的案件編號尚待行政核發；完成核對後將主動通知您。\n"
        "工會行政專員將於上班時間透過 LINE 與您聯繫確認服務細節，請您耐心等候！"
    )


def _complete_registration(cursor, registration_id, client_id, beclass_record_id) -> None:
    cursor.execute(
        "UPDATE provisional_client_registrations SET client_id=%s,beclass_record_id=%s "
        "WHERE id=%s AND client_id IS NULL AND beclass_record_id IS NULL",
        (client_id, beclass_record_id, registration_id),
    )
    if int(cursor.rowcount) != 1:
        raise ProvisionalRegistrationStorageError("registration_completion_conflict")


def _last_insert_id(cursor, code) -> int:
    value = int(cursor.lastrowid or 0)
    if value <= 0:
        raise ProvisionalRegistrationStorageError(code)
    return value


_CLAIM_SQL = (
    "INSERT INTO provisional_client_registrations "
    "(line_user_id,active_line_user_id,payload_fingerprint,status) VALUES (%s,%s,%s,'submitted') "
    "ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)"
)
_ACTIVE_SELECT_SQL = (
    "SELECT id,payload_fingerprint,client_id,beclass_record_id "
    "FROM provisional_client_registrations WHERE active_line_user_id=%s FOR UPDATE"
)
_CONFLICT_INSERT_SQL = (
    "INSERT INTO provisional_registration_conflicts "
    "(registration_id,proposed_payload_fingerprint,proposed_payload) VALUES (%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)"
)


def _candidate_snapshot(candidate):
    return {"client": candidate.client_payload, "beclass": candidate.beclass_payload}


__all__ = [
    "MySqlProvisionalRegistrationRepository",
    "ProvisionalRegistrationMySqlUnitOfWork",
    "ProvisionalRegistrationStorageError",
]
