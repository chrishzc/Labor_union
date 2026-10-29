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
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationConflict,
    ProvisionalRegistrationConflictError,
    ProvisionalRegistrationReceipt,
    ProvisionalRegistrationStorageError,
    RegistrationApplicationSnapshot,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork


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
            replayed = bool(record.get("already_submitted"))
            # Intake and its durable reply are committed by the same outer UoW.
            # Replaying an existing intake must not regenerate a timestamped
            # delivery fingerprint for the already committed idempotency key.
            if not replayed:
                self._enqueue_confirmation(candidate, int(record["id"]), approved=False)
            return ProvisionalRegistrationReceipt(
                int(record["id"]), None, None,
                str(candidate.client_payload["name"]), replayed, not replayed,
            )

    def pending_applications(self, *, after_id=0, limit=50) -> tuple[RegistrationApplicationSnapshot, ...]:
        with _cursor(self._connection) as cursor:
            cursor.execute(_APPLICATION_SELECT + " WHERE id>%s AND client_id IS NULL AND beclass_record_id IS NULL "
                           "AND application_payload IS NOT NULL ORDER BY id LIMIT %s", (after_id, limit))
            return tuple(_application_snapshot(row) for row in cursor.fetchall())

    def load_application(self, registration_id, *, for_update=False) -> RegistrationApplicationSnapshot:
        with _cursor(self._connection) as cursor:
            cursor.execute(_APPLICATION_SELECT + " WHERE id=%s" + (" FOR UPDATE" if for_update else ""), (registration_id,))
            row = cursor.fetchone()
            if row is None or row.get("application_payload") is None:
                raise ProvisionalRegistrationConflictError("registration_application_not_found")
            return _application_snapshot(row)

    def approve(self, registration_id, expected_version, actor) -> ProvisionalRegistrationReceipt:
        snapshot = self.load_application(registration_id, for_update=True)
        candidate = snapshot.candidate
        if snapshot.client_id is not None and snapshot.beclass_record_id is not None:
            if candidate.registration_kind == "non_citizen" and snapshot.case_no is None:
                raise ProvisionalRegistrationConflictError("registration_case_issue_incomplete")
            return ProvisionalRegistrationReceipt(registration_id, snapshot.client_id, snapshot.beclass_record_id,
                                                   str(candidate.client_payload["name"]), True, False, snapshot.case_no)
        if snapshot.version != expected_version or snapshot.client_id is not None or snapshot.beclass_record_id is not None:
            raise ProvisionalRegistrationConflictError("registration_application_stale")
        approved_at = self._now()
        with _cursor(self._connection) as cursor:
            client_id = _insert_client(cursor, candidate)
            beclass_id = _insert_beclass_record(cursor, candidate)
            cursor.execute("UPDATE provisional_client_registrations SET client_id=%s,beclass_record_id=%s,"
                           "application_version=application_version+1,approved_by_actor=%s,approved_at_utc=%s "
                           "WHERE id=%s AND application_version=%s AND client_id IS NULL AND beclass_record_id IS NULL",
                           (client_id, beclass_id, actor, approved_at.astimezone(timezone.utc).replace(tzinfo=None),
                            registration_id, expected_version))
            if cursor.rowcount != 1:
                raise ProvisionalRegistrationConflictError("registration_application_stale")
        case_no = self._issue_non_citizen_case(registration_id, candidate, actor, approved_at) if candidate.registration_kind == "non_citizen" else None
        self._enqueue_confirmation(candidate, registration_id, approved=True, case_no=case_no)
        return ProvisionalRegistrationReceipt(registration_id, client_id, beclass_id,
                                               str(candidate.client_payload["name"]), False, True, case_no)

    def _issue_non_citizen_case(self, registration_id, candidate, actor, approved_at) -> str:
        from infrastructure.mysql.case_import_repository import MySqlCaseImportRepository
        from infrastructure.mysql.non_citizen_case_number_repository import allocate_non_citizen_case_number
        from shared_kernel.identities import ActorContext, ExpectedVersion
        from subsystems.case_import.case_import_workflow import ApplyCaseImport, CaseImportWorkflow
        from subsystems.case_import.non_citizen_registration_application import non_citizen_case_intent
        case_no = allocate_non_citizen_case_number(self._connection, approved_at)
        with _cursor(self._connection) as cursor:
            cursor.execute("SELECT holiday_date FROM holidays")
            holidays = {row["holiday_date"] for row in cursor.fetchall()}
        intent = non_citizen_case_intent(candidate, case_no, approved_at, registration_id, holidays)
        workflow = CaseImportWorkflow(MySqlCaseImportRepository(self._connection), lambda: None)
        correlation = CorrelationId(f"non-citizen-approval:{registration_id}")
        preview = workflow.preview(intent, correlation)
        receipt = workflow.apply_in_current_uow(ApplyCaseImport(
            intent, ExpectedVersion(preview.import_version), preview.fingerprint,
            IdempotencyKey(f"non-citizen-approval:{registration_id}"), ActorContext(actor),
            "工會核准非市民服務申請", correlation,
        ))
        return receipt.case_no

    def _enqueue_confirmation(self, candidate, registration_id, *, approved, case_no=None) -> None:
        self._delivery_tasks.enqueue(
            _confirmation_request(candidate, registration_id, self._now(), approved=approved, case_no=case_no)
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
    cursor.execute(_CLAIM_SQL, (candidate.line_user_id, candidate.line_user_id, candidate.payload_fingerprint.value,
                              json.dumps(_candidate_snapshot(candidate), ensure_ascii=False, sort_keys=True)))
    created = int(cursor.rowcount) == 1
    cursor.execute(_ACTIVE_SELECT_SQL, (candidate.line_user_id,))
    record = cursor.fetchone()
    if not isinstance(record, Mapping):
        raise ProvisionalRegistrationStorageError("registration_claim_missing")
    return {**record, "already_submitted": not created}


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
    cursor.execute("SELECT id FROM provisional_registration_conflicts WHERE registration_id=%s "
                   "AND proposed_payload_fingerprint=%s FOR UPDATE", (int(record["id"]), candidate.payload_fingerprint.value))
    conflict = cursor.fetchone()
    if not conflict:
        raise ProvisionalRegistrationStorageError("registration_conflict_insert_failed")
    conflict_id = int(conflict["id"])
    return ProvisionalRegistrationConflict(int(record["id"]), conflict_id)


def _is_complete(record) -> bool:
    return bool(record.get("client_id")) and bool(record.get("beclass_record_id"))


def _receipt(record, candidate, *, replayed):
    if not _is_complete(record):
        raise ProvisionalRegistrationStorageError("registration_receipt_incomplete")
    return ProvisionalRegistrationReceipt(
        int(record["id"]), int(record["client_id"]), int(record["beclass_record_id"]),
        str(candidate.client_payload["name"]), replayed, False,
        record.get("case_no"),
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


def _confirmation_request(candidate, registration_id, scheduled_at, *, approved, case_no=None):
    stage = "approved" if approved else "submitted"
    return LineDeliveryRequest(
        LineRecipient(LineRecipientType.USER, LineUserId(candidate.line_user_id)),
        LineMessageKind.TEXT,
        canonical_line_payload_json(
            {"type": "text", "text": _confirmation_message(candidate, approved=approved, case_no=case_no)}
        ),
        scheduled_at,
        IdempotencyKey(f"line-registration:{registration_id}:{stage}"),
        CorrelationId(f"line-registration:{registration_id}"),
        "provisional_registration",
        str(registration_id),
    )


def _confirmation_message(candidate, *, approved, case_no=None) -> str:
    name = str(candidate.client_payload["name"])
    if not approved:
        return f"【系統通知】\n{name}您好，需求申請已送出，待工會人員核准後才建立正式客戶資料。送出申請不代表已完成媒合。"
    if case_no:
        return f"【系統通知】\n{name}您好，非市民服務申請已核准。\n案件編號：{case_no}\n工會將與您確認後續服務安排。"
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
    "INSERT IGNORE INTO provisional_client_registrations "
    "(line_user_id,active_line_user_id,payload_fingerprint,application_payload,status) VALUES (%s,%s,%s,%s,'submitted')"
)
_ACTIVE_SELECT_SQL = (
    "SELECT id,payload_fingerprint,client_id,beclass_record_id "
    "FROM provisional_client_registrations WHERE active_line_user_id=%s FOR UPDATE"
)
_CONFLICT_INSERT_SQL = (
    "INSERT IGNORE INTO provisional_registration_conflicts "
    "(registration_id,proposed_payload_fingerprint,proposed_payload) VALUES (%s,%s,%s)"
)

_APPLICATION_SELECT = ("SELECT id,application_version,application_payload,payload_fingerprint,line_user_id,"
                       "client_id,beclass_record_id,approved_by_actor,approved_at_utc,"
                       "(SELECT e.case_no FROM provisional_registration_case_issue_events e "
                       "WHERE e.registration_id=provisional_client_registrations.id) AS case_no "
                       "FROM provisional_client_registrations")


def _application_snapshot(row) -> RegistrationApplicationSnapshot:
    payload = row["application_payload"]
    payload = json.loads(payload) if isinstance(payload, str) else payload
    if fingerprint_payload(payload).value != row["payload_fingerprint"]:
        raise ProvisionalRegistrationStorageError("registration_application_payload_mismatch")
    if payload["client"]["line_user_id"] != row["line_user_id"]:
        raise ProvisionalRegistrationStorageError("registration_application_identity_mismatch")
    candidate = ProvisionalRegistrationCandidate(str(row["line_user_id"]), payload["client"], payload["beclass"],
                                                 PreviewFingerprint(row["payload_fingerprint"]))
    approved_at = row.get("approved_at_utc")
    if approved_at is not None and approved_at.tzinfo is None:
        approved_at = approved_at.replace(tzinfo=timezone.utc)
    return RegistrationApplicationSnapshot(int(row["id"]), int(row["application_version"]), candidate,
                                           row["client_id"], row["beclass_record_id"], row["approved_by_actor"],
                                           row.get("case_no"), approved_at)


def _candidate_snapshot(candidate):
    return {"client": candidate.client_payload, "beclass": candidate.beclass_payload}


__all__ = [
    "MySqlProvisionalRegistrationRepository",
    "ProvisionalRegistrationMySqlUnitOfWork",
    "ProvisionalRegistrationStorageError",
]
