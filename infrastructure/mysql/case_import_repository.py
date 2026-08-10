"""MySQL adapter for atomic case import and architecture bootstrap."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, time
import json
from typing import Iterator, Mapping

from pymysql.err import IntegrityError, OperationalError

from domains.bootstrap.case_architecture import (
    BootstrapDomainError,
    PayrollPolicyKind,
    RatePolicyFacts,
    policy_kind_for_identity,
)
from domains.case_import.case_import import (
    CaseImportCandidate,
    CaseImportDomainError,
    CaseImportFacts,
    CaseImportIssue,
)
from infrastructure.mysql.case_architecture_bootstrap_repository import (
    MySqlCaseArchitectureBootstrapRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.case_import.case_import_workflow import (
    ApplyCaseImport,
    CaseImportClaimState,
    CaseImportReceipt,
    CaseImportStorageError,
    StoredCaseImportReceipt,
)

_COMMAND_FAMILY = "case_import"
_RETRYABLE_MYSQL_CODES = frozenset({1062, 1205, 1213})


class CaseImportMySqlUnitOfWork(MySqlUnitOfWork):
    def __enter__(self):
        try:
            return super().__enter__()
        except OperationalError as error:
            _raise_storage_error(error)

    def commit(self) -> None:
        try:
            super().commit()
        except OperationalError as error:
            _raise_storage_error(error)


class MySqlCaseImportRepository:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._bootstrap = MySqlCaseArchitectureBootstrapRepository(connection)

    def case_exists(self, case_no: str) -> bool:
        with _mysql_cursor(self._connection) as cursor:
            return _case_exists(cursor, case_no, lock=False)

    def load(self, intent, *, for_update):
        with _mysql_cursor(self._connection) as cursor:
            exists = _case_exists(cursor, intent.case_no, lock=for_update)
            policy = _load_rate_policy(cursor, intent, lock=for_update)
        return CaseImportFacts(exists, policy)

    def claim_command(self, command, command_fingerprint):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _CLAIM_INSERT_SQL,
                (
                    command.idempotency_key.value,
                    _COMMAND_FAMILY,
                    command.intent.case_no,
                    command_fingerprint.value,
                    command.correlation_id.value,
                ),
            )
            if int(cursor.rowcount) == 1:
                return CaseImportClaimState.CREATED
            return _load_claim_state(cursor, command, command_fingerprint)

    def find_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def insert_case_roots(self, candidate) -> int:
        with _mysql_cursor(self._connection) as cursor:
            client_id = _insert_client(cursor, candidate)
            _insert_order(cursor, candidate, client_id)
        return client_id

    def create_architecture_bootstrap(self, command, candidate) -> int:
        return self._bootstrap.create_bootstrap(command, candidate.bootstrap)

    # Kept cohesive because this is one immutable event serialization boundary.
    def append_import_event(
        self,
        command,
        candidate,
        client_id,
        bootstrap_event_id,
    ) -> int:
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _IMPORT_EVENT_INSERT_SQL,
                (
                    candidate.case_no,
                    client_id,
                    bootstrap_event_id,
                    candidate.source_fingerprint.value,
                    candidate.fingerprint.value,
                    _canonical_json(_source_snapshot(candidate)),
                    command.idempotency_key.value,
                    command.actor.actor_id,
                    command.reason,
                    command.correlation_id.value,
                ),
            )
            event_id = int(cursor.lastrowid or 0)
        if event_id <= 0:
            raise RuntimeError("case_import_event_insert_failed")
        return event_id

    # Kept cohesive because receipt columns mirror one replay evidence payload.
    def save_receipt(self, key, stored) -> None:
        receipt = stored.receipt
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (
                    key.value,
                    stored.command_fingerprint.value,
                    receipt.source_fingerprint.value,
                    receipt.preview_fingerprint.value,
                    receipt.case_no,
                    receipt.client_id,
                    receipt.import_event_id,
                    receipt.bootstrap_event_id,
                    receipt.order_version,
                    receipt.client_finance_version,
                    receipt.payroll_version,
                    receipt.scheduling_version,
                    receipt.scheduling_generation,
                    _canonical_json(_receipt_payload(receipt)),
                ),
            )


@contextmanager
def _mysql_cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except (OperationalError, IntegrityError) as error:
        _raise_storage_error(error)


def _raise_storage_error(error):
    code = int(error.args[0]) if error.args else 0
    raise CaseImportStorageError(
        "Case import MySQL transaction failed.",
        retryable=code in _RETRYABLE_MYSQL_CODES,
    ) from error


def _case_exists(cursor, case_no, *, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT case_no FROM clients WHERE case_no=%s" + suffix,
        (case_no,),
    )
    client_exists = cursor.fetchone() is not None
    cursor.execute(
        "SELECT case_no FROM orders WHERE case_no=%s" + suffix,
        (case_no,),
    )
    return client_exists or cursor.fetchone() is not None


def _load_rate_policy(cursor, intent, *, lock):
    identity = str(_client_attribute(intent, "identity_status"))
    try:
        policy_kind = policy_kind_for_identity(identity)
    except BootstrapDomainError as error:
        raise CaseImportDomainError(
            CaseImportIssue.BOOTSTRAP_BLOCKED,
            str(error),
        ) from error
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT policy_version,policy_kind,hourly_rate_ntd,effective_from,"
        "effective_until FROM payroll_rate_policies "
        "WHERE policy_version=%s AND policy_kind=%s" + suffix,
        (intent.bootstrap.payroll_policy_version, policy_kind.value),
    )
    return _rate_policy(cursor.fetchone())


def _rate_policy(row):
    if not isinstance(row, Mapping):
        return None
    return RatePolicyFacts(
        str(row["policy_version"]),
        PayrollPolicyKind(str(row["policy_kind"])),
        MoneyNTD(_integer_ntd(row["hourly_rate_ntd"])),
        row["effective_from"],
        row["effective_until"],
    )


def _insert_client(cursor, candidate):
    attributes = candidate.client_attributes
    columns = ",".join(f"`{item.name}`" for item in attributes)
    placeholders = ",".join("%s" for _ in attributes)
    cursor.execute(
        f"INSERT INTO clients ({columns}) VALUES ({placeholders})",
        tuple(item.value for item in attributes),
    )
    client_id = int(cursor.lastrowid or 0)
    if client_id <= 0:
        raise RuntimeError("case_import_client_insert_failed")
    return client_id


def _insert_order(cursor, candidate, client_id) -> None:
    order = candidate.order
    cursor.execute(
        _ORDER_INSERT_SQL,
        (
            candidate.case_no,
            client_id,
            order.service_days,
            order.service_hours_per_day,
            order.planned_start_date,
            order.planned_end_date,
            order.service_start_time,
            order.service_end_time,
            order.service_end_day_offset,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise RuntimeError("case_import_order_insert_failed")


def _load_claim_state(cursor, command, fingerprint):
    cursor.execute(
        "SELECT command_family,aggregate_identity,command_fingerprint "
        "FROM application_command_claims "
        "WHERE idempotency_key=%s FOR UPDATE",
        (command.idempotency_key.value,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise RuntimeError("case_import_command_claim_missing")
    matches = (
        str(row["command_family"]) == _COMMAND_FAMILY
        and str(row["aggregate_identity"]) == command.intent.case_no
        and str(row["command_fingerprint"]) == fingerprint.value
    )
    return CaseImportClaimState.MATCHED if matches else CaseImportClaimState.MISMATCH


def _stored_receipt(row):
    receipt = CaseImportReceipt(
        str(row["case_no"]),
        int(row["client_id"]),
        int(row["order_version"]),
        int(row["client_finance_version"]),
        int(row["payroll_version"]),
        int(row["scheduling_version"]),
        int(row["scheduling_generation"]),
        int(row["import_event_id"]),
        int(row["bootstrap_event_id"]),
        PreviewFingerprint(str(row["source_fingerprint"])),
        PreviewFingerprint(str(row["preview_fingerprint"])),
    )
    if _json_object(row["result_snapshot"]) != _receipt_payload(receipt):
        raise RuntimeError("case_import_receipt_corrupt")
    return StoredCaseImportReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _receipt_payload(receipt):
    return {
        "bootstrap_event_id": receipt.bootstrap_event_id,
        "case_no": receipt.case_no,
        "client_finance_version": receipt.client_finance_version,
        "client_id": receipt.client_id,
        "import_event_id": receipt.import_event_id,
        "order_version": receipt.order_version,
        "payroll_version": receipt.payroll_version,
        "scheduling_generation": receipt.scheduling_generation,
        "scheduling_version": receipt.scheduling_version,
    }


def _source_snapshot(candidate):
    return {
        "case_no": candidate.case_no,
        "client_attributes": {
            item.name: _json_value(item.value)
            for item in candidate.client_attributes
        },
        "order": {
            "planned_end_date": candidate.order.planned_end_date.isoformat(),
            "planned_start_date": candidate.order.planned_start_date.isoformat(),
            "service_days": candidate.order.service_days,
            "service_end_day_offset": candidate.order.service_end_day_offset,
            "service_end_time": candidate.order.service_end_time.isoformat(),
            "service_hours_per_day": candidate.order.service_hours_per_day,
            "service_start_time": candidate.order.service_start_time.isoformat(),
        },
    }


def _client_attribute(intent, name):
    return next(item.value for item in intent.client_attributes if item.name == name)


def _json_value(value):
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    return value


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, Mapping) else {}


def _integer_ntd(value):
    integer = int(value)
    if integer != value:
        raise ValueError("non_integer_payroll_input")
    return integer


_CLAIM_INSERT_SQL = (
    "INSERT IGNORE INTO application_command_claims "
    "(idempotency_key,command_family,aggregate_identity,"
    "command_fingerprint,correlation_id) VALUES (%s,%s,%s,%s,%s)"
)
_ORDER_INSERT_SQL = (
    "INSERT INTO orders "
    "(case_no,client_id,status,lifecycle_version,service_days,"
    "service_hours_per_day,start_date,end_date,service_start_time,"
    "service_end_time,service_end_day_offset) "
    "VALUES (%s,%s,'洽談中',0,%s,%s,%s,%s,%s,%s,%s)"
)
_IMPORT_EVENT_INSERT_SQL = (
    "INSERT INTO case_import_events "
    "(case_no,client_id,bootstrap_event_id,source_fingerprint,"
    "candidate_fingerprint,source_snapshot,idempotency_key,actor,reason,"
    "correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,source_fingerprint,preview_fingerprint,"
    "case_no,client_id,import_event_id,bootstrap_event_id,order_version,"
    "client_finance_version,payroll_version,scheduling_version,"
    "scheduling_generation,result_snapshot FROM case_import_receipts "
    "WHERE idempotency_key=%s FOR UPDATE"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO case_import_receipts "
    "(idempotency_key,command_fingerprint,source_fingerprint,"
    "preview_fingerprint,case_no,client_id,import_event_id,"
    "bootstrap_event_id,order_version,client_finance_version,"
    "payroll_version,scheduling_version,scheduling_generation,"
    "result_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)

__all__ = ["CaseImportMySqlUnitOfWork", "MySqlCaseImportRepository"]
