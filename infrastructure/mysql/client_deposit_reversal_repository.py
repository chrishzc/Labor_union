"""MySQL facts and atomic persistence for canonical deposit reversal."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import hashlib
import json
from typing import Iterator, Mapping

from pymysql.err import IntegrityError, OperationalError

from domains.client_finance.deposit_lifecycle import DepositLifecycleEvent
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.client_finance.deposit_reversal_workflow import (
    DepositReversalApplyRequest,
    DepositReversalFacts,
    DepositReversalReceipt,
    StoredDepositReversalReceipt,
)


_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})


class ClientDepositReversalRepositoryUnavailable(RuntimeError):
    """Signals a transient MySQL failure that permits exact command retry."""


class ClientDepositReversalMySqlUnitOfWork(MySqlUnitOfWork):
    def __enter__(self):
        try:
            return super().__enter__()
        except OperationalError as error:
            _raise_if_retryable(error)
            raise

    def commit(self) -> None:
        try:
            super().commit()
        except OperationalError as error:
            _raise_if_retryable(error)
            raise


class MySqlClientDepositReversalRepository:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._request: DepositReversalApplyRequest | None = None
        self._reversal_ledger_entry_id: int | None = None
        self._deposit_due_date: date | None = None

    def bind_apply_request(self, request: DepositReversalApplyRequest) -> None:
        self._request = request

    def clear_apply_request(self) -> None:
        self._request = None
        self._reversal_ledger_entry_id = None
        self._deposit_due_date = None

    def load(self, selection, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_FACTS_SELECT_SQL + suffix, (selection.case_no,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError("deposit settlement is not available")
            cursor.execute(_CONTROL_SELECT_SQL + suffix, (selection.case_no,))
            control = cursor.fetchone()
        facts = _facts(row, control)
        self._deposit_due_date = facts.deposit_due_date
        return facts

    def find_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def append_reversal_ledger_entry(self, candidate) -> None:
        request = self._require_request()
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _REVERSAL_LEDGER_INSERT_SQL,
                (
                    candidate.case_no,
                    candidate.reversal_amount_ntd,
                    candidate.reversal_occurred_on,
                    candidate.reversed_settlement_identity.value,
                    candidate.original_ledger_entry_id,
                    _child_key(request, "reversal-ledger"),
                    request.actor.actor_id,
                    request.reason,
                ),
            )
            self._reversal_ledger_entry_id = int(cursor.lastrowid or 0)
        if self._reversal_ledger_entry_id < 1:
            raise RuntimeError("deposit reversal ledger identity was not generated")

    def reopen_deposit_obligation(self, candidate) -> None:
        request = self._require_request()
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _OBLIGATION_EVENT_INSERT_SQL,
                (
                    candidate.deposit_obligation_identity,
                    candidate.case_no,
                    candidate.reversal_amount_ntd,
                    self._deposit_due_date,
                    self._deposit_due_date,
                    _child_key(request, "obligation-event"),
                    request.expected_account_version.value,
                    _child_key(request, "obligation"),
                    request.actor.actor_id,
                    request.reason,
                ),
            )
            event_id = int(cursor.lastrowid or 0)
            if event_id < 1:
                raise RuntimeError("deposit reversal obligation event was not generated")
            cursor.execute(
                _OBLIGATION_REOPEN_SQL,
                (
                    candidate.reversal_amount_ntd,
                    candidate.resulting_account_version,
                    event_id,
                    candidate.deposit_obligation_identity,
                    candidate.case_no,
                ),
            )
            if int(cursor.rowcount) != 1:
                raise RuntimeError("deposit obligation changed during reversal")

    def replace_deposit_settlement(self, candidate) -> None:
        request = self._require_request()
        reversal_entry_id = self._require_reversal_entry_id()
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _DEPOSIT_SETTLEMENT_REVERSE_SQL,
                (
                    candidate.fingerprint.value,
                    candidate.resulting_account_version,
                    reversal_entry_id,
                    candidate.case_no,
                    candidate.reversed_settlement_identity.value,
                    candidate.original_ledger_entry_id,
                ),
            )
            if int(cursor.rowcount) != 1:
                raise RuntimeError("deposit settlement changed during reversal")
            cursor.execute(
                _ACCOUNT_VERSION_UPDATE_SQL,
                (
                    candidate.resulting_account_version,
                    candidate.case_no,
                    request.expected_account_version.value,
                ),
            )
            if int(cursor.rowcount) != 1:
                raise RuntimeError("deposit reversal candidate is stale")

    def append_orders_lifecycle_intent(self, candidate) -> None:
        request = self._require_request()
        payload = {
            "case_no": candidate.case_no,
            "reversed_settlement_identity": candidate.reversed_settlement_identity.value,
            "reversal_occurred_on": candidate.reversal_occurred_on.isoformat(),
            "resulting_account_version": candidate.resulting_account_version,
            "preserve_service_state": candidate.lifecycle_impact.preserve_service_state,
            "require_actual_start_reconfirmation": candidate.lifecycle_impact.require_actual_start_reconfirmation,
        }
        self._append_outbox("orders_deposit_reversed", "orders-deposit", payload)

    def append_anomaly_intent(self, candidate) -> None:
        self._append_outbox(
            "anomaly_review_required",
            "deposit-reversal-anomaly",
            {"case_no": candidate.case_no, "code": candidate.lifecycle_impact.anomaly_code},
        )

    def save_receipt(self, key, stored_receipt) -> None:
        receipt = stored_receipt.receipt
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (
                    key.value,
                    stored_receipt.command_fingerprint.value,
                    self._require_request().preview_fingerprint.value,
                    receipt.case_no,
                    receipt.account_version,
                    _canonical_json(_receipt_payload(receipt)),
                ),
            )

    def _append_outbox(self, intent_type, purpose, payload) -> None:
        request = self._require_request()
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                (
                    request.selection.case_no,
                    intent_type,
                    _outbox_key(request, purpose),
                    _canonical_json(payload),
                ),
            )

    def _require_request(self) -> DepositReversalApplyRequest:
        if self._request is None:
            raise RuntimeError("Deposit Reversal Apply request is not bound")
        return self._request

    def _require_reversal_entry_id(self) -> int:
        if self._reversal_ledger_entry_id is None:
            raise RuntimeError("deposit reversal ledger entry is missing")
        return self._reversal_ledger_entry_id


@contextmanager
def _mysql_cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except OperationalError as error:
        _raise_if_retryable(error)
        raise
    except IntegrityError as error:
        if error.args and int(error.args[0]) == 1062:
            raise ClientDepositReversalRepositoryUnavailable(
                "concurrent deposit reversal requires exact retry"
            ) from error
        raise


def _raise_if_retryable(error: OperationalError) -> None:
    if error.args and int(error.args[0]) in _RETRYABLE_MYSQL_CODES:
        raise ClientDepositReversalRepositoryUnavailable(
            "deposit reversal is temporarily unavailable"
        ) from error


def _facts(row, control) -> DepositReversalFacts:
    projection = _mapping(row, "deposit settlement projection")
    if projection.get("settlement_state") != "settled":
        raise ValueError("deposit reversal requires a settled deposit")
    if projection.get("ledger_entry_type") != "receipt":
        raise ValueError("deposit reversal requires an original receipt")
    identity = PreviewFingerprint(str(projection["settlement_identity"]))
    confirmed = _confirmed_identity(control)
    status = str(projection["order_status"])
    return DepositReversalFacts(
        str(projection["case_no"]),
        int(projection["aggregate_version"]),
        str(projection["deposit_obligation_identity"]),
        int(projection["contracted_amount_ntd"]),
        projection.get("deposit_due_date"),
        identity,
        int(projection["latest_ledger_entry_id"]),
        int(projection["ledger_amount_ntd"]),
        projection.get("actual_start_date") is not None,
        status in {"服務中", "訂單完成"},
        status == "訂單完成",
        confirmed,
    )


def _confirmed_identity(control):
    if control is None or control.get("state") != "cleared":
        return None
    value = control.get("deposit_settlement_identity_hash")
    return None if value is None else PreviewFingerprint(str(value))


def _mapping(value, name):
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} is invalid")
    return value


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = DepositReversalReceipt(
        str(payload["case_no"]),
        int(payload["account_version"]),
        int(payload["original_ledger_entry_id"]),
        int(payload["reversal_amount_ntd"]),
        DepositLifecycleEvent(str(payload["lifecycle_intent"])),
        None if payload.get("anomaly_code") is None else str(payload["anomaly_code"]),
    )
    return StoredDepositReversalReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])), receipt
    )


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "account_version": receipt.account_version,
        "original_ledger_entry_id": receipt.original_ledger_entry_id,
        "reversal_amount_ntd": receipt.reversal_amount_ntd,
        "lifecycle_intent": receipt.lifecycle_intent.value,
        "anomaly_code": receipt.anomaly_code,
    }


def _child_key(request, purpose):
    digest = hashlib.sha256(f"{request.idempotency_key.value}:{purpose}".encode()).hexdigest()
    return f"deposit-reversal:{digest}"


def _outbox_key(request, purpose):
    digest = hashlib.sha256(f"{request.idempotency_key.value}:{purpose}".encode()).hexdigest()
    return f"client-finance:{digest}"


def _canonical_json(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_object(value):
    payload = json.loads(value) if isinstance(value, str) else value
    return _mapping(payload, "result snapshot")


_FACTS_SELECT_SQL = (
    "SELECT projection.case_no,account.aggregate_version,"
    "projection.deposit_obligation_identity,projection.settlement_state,"
    "projection.contracted_amount_ntd,projection.settlement_identity,"
    "projection.latest_ledger_entry_id,ledger.entry_type AS ledger_entry_type,"
    "ledger.amount_ntd AS ledger_amount_ntd,orders.status AS order_status,"
    "orders.actual_start_date,obligation.due_date AS deposit_due_date "
    "FROM client_deposit_settlement_projection projection "
    "JOIN client_finance_accounts account ON account.case_no=projection.case_no "
    "JOIN client_ledger_entries ledger ON ledger.id=projection.latest_ledger_entry_id "
    "JOIN client_obligations obligation ON obligation.obligation_identity=projection.deposit_obligation_identity "
    "AND obligation.case_no=projection.case_no "
    "JOIN orders ON orders.case_no=projection.case_no "
    "WHERE projection.case_no=%s"
)
_CONTROL_SELECT_SQL = (
    "SELECT state,deposit_settlement_identity_hash "
    "FROM order_lifecycle_control_state "
    "WHERE case_no=%s AND control_type='actual_start_reconfirmation' "
    "AND control_key='actual_start_reconfirmation'"
)
_REVERSAL_LEDGER_INSERT_SQL = (
    "INSERT INTO client_ledger_entries "
    "(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
    "reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) "
    "VALUES (%s,NULL,'reversal',%s,%s,%s,%s,%s,%s,%s)"
)
_OBLIGATION_REOPEN_SQL = (
    "UPDATE client_obligations SET amount_due_ntd=%s,status='open',projection_version=%s,current_event_id=%s "
    "WHERE obligation_identity=%s AND case_no=%s AND status='settled' AND amount_due_ntd=0"
)
_OBLIGATION_EVENT_INSERT_SQL = (
    "INSERT INTO client_obligation_events "
    "(obligation_identity,case_no,obligation_type,direction,event_type,"
    "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,"
    "source_event_identity,source_obligation_identity,expected_account_version,"
    "idempotency_key,actor,reason) "
    "VALUES (%s,%s,'deposit','receivable_from_client','reversed',0,%s,%s,%s,"
    "%s,NULL,%s,%s,%s,%s)"
)
_DEPOSIT_SETTLEMENT_REVERSE_SQL = (
    "UPDATE client_deposit_settlement_projection SET settlement_state='unsettled',"
    "allocated_net_amount_ntd=0,settlement_identity=NULL,source_fingerprint=%s,"
    "projection_version=%s,latest_ledger_entry_id=%s "
    "WHERE case_no=%s AND settlement_state='settled' AND settlement_identity=%s "
    "AND latest_ledger_entry_id=%s"
)
_ACCOUNT_VERSION_UPDATE_SQL = (
    "UPDATE client_finance_accounts SET aggregate_version=%s "
    "WHERE case_no=%s AND aggregate_version=%s"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO client_finance_outbox(case_no,intent_type,intent_key,payload_snapshot) "
    "VALUES (%s,%s,%s,%s)"
)
_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,result_snapshot FROM client_deposit_reversal_apply_receipts "
    "WHERE idempotency_key=%s FOR UPDATE"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO client_deposit_reversal_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "resulting_account_version,result_snapshot) VALUES (%s,%s,%s,%s,%s,%s)"
)
