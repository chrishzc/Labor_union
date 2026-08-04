"""MySQL facts and atomic persistence for Client Receipt reconciliation."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Iterator, Mapping

from pymysql.err import IntegrityError, OperationalError

from domains.client_finance.reconciliation import (
    ClientObligation,
    ClientReconciliationCandidate,
    IncomingBankFact,
    PaymentStage,
    ReconciliationStatus,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationFacts,
    ClientReconciliationReceipt,
    StoredClientReconciliationReceipt,
)

_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})
_VIRTUAL_ACCOUNT_PATTERN = re.compile(r"^99781699([0-9]{3})([0-9]{3})$")
_SUPPORTED_RECEIPT_STAGES = frozenset(
    {
        PaymentStage.DEPOSIT,
        PaymentStage.FIRST,
        PaymentStage.SECOND,
        PaymentStage.ADJUSTMENT,
    }
)


@dataclass(frozen=True, slots=True)
class _BankMetadata:
    row_id: int
    occurred_on: date


class ClientReceiptRepositoryUnavailable(RuntimeError):
    """Signals a transient MySQL failure that permits exact command retry."""


class ClientReceiptMySqlUnitOfWork(MySqlUnitOfWork):
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


class MySqlClientReceiptReconciliationRepository:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._request: ClientReconciliationApplyRequest | None = None
        self._bank_metadata: dict[str, _BankMetadata] = {}
        self._ledger_entry_ids: dict[str, int] = {}
        self._obligation_amounts: dict[str, int] = {}
        self._settlement_identity: str | None = None

    def bind_apply_request(
        self,
        request: ClientReconciliationApplyRequest,
    ) -> None:
        self._request = request

    def clear_apply_request(self) -> None:
        self._request = None
        self._bank_metadata.clear()
        self._ledger_entry_ids.clear()
        self._obligation_amounts.clear()
        self._settlement_identity = None

    # Kept cohesive so Apply follows account, bank-row, then obligation lock order.
    def load(self, selection, *, for_update):
        with _mysql_cursor(self._connection) as cursor:
            account_version = _load_account_version(
                cursor,
                selection.case_no,
                lock=for_update,
            )
            bank_rows = _load_selected_bank_rows(
                cursor,
                selection,
                lock=for_update,
            )
            obligation_rows = _load_selected_obligations(
                cursor,
                selection,
                lock=for_update,
            )
        self._capture_loaded_facts(bank_rows, obligation_rows)
        return ClientReconciliationFacts(
            account_version,
            _bank_facts(bank_rows, selection),
            _obligation_facts(obligation_rows),
        )

    def find_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    # Kept cohesive so each immutable entry claims its source bank row.
    def append_ledger_entries(self, candidate) -> None:
        request = self._require_request()
        self._settlement_identity = candidate.settlement_identity.value
        amounts = _allocated_amounts_by_bank(candidate)
        with _mysql_cursor(self._connection) as cursor:
            for ordinal, identity in enumerate(sorted(amounts), start=1):
                entry_id = _insert_ledger_entry(
                    cursor,
                    request,
                    candidate,
                    identity,
                    amounts[identity],
                    self._bank_metadata[identity],
                    ordinal,
                )
                self._ledger_entry_ids[identity] = entry_id
                _mark_bank_row_reconciled(
                    cursor,
                    self._bank_metadata[identity].row_id,
                    candidate.settlement_identity.value,
                )

    def append_allocations(self, candidate) -> None:
        ordinals: dict[str, int] = {}
        with _mysql_cursor(self._connection) as cursor:
            for allocation in candidate.allocations:
                identity = allocation.bank_fact_identity
                ordinal = ordinals.get(identity, 0) + 1
                ordinals[identity] = ordinal
                _insert_allocation(
                    cursor,
                    self._ledger_entry_ids,
                    allocation,
                    ordinal,
                )

    # Kept cohesive so exact-zero, projection CAS, and outbox cannot diverge.
    def update_projection(self, selection, resulting_version) -> None:
        request = self._require_request()
        settlement_identity = self._require_settlement_identity()
        with _mysql_cursor(self._connection) as cursor:
            allocated = _load_persisted_allocation_totals(
                cursor,
                selection.obligation_identities,
                settlement_identity,
            )
            _validate_exact_zero(self._obligation_amounts, allocated)
            _settle_selected_obligations(
                cursor,
                selection,
                self._obligation_amounts,
                resulting_version,
            )
            _advance_account_version(cursor, request, resulting_version)
            _upsert_deposit_settlement_projection(
                cursor,
                selection,
                self._obligation_amounts,
                self._ledger_entry_ids,
                settlement_identity,
                resulting_version,
            )
            _append_projection_outbox(
                cursor,
                request,
                settlement_identity,
                resulting_version,
            )

    def append_orders_deposit_intent(self, candidate) -> None:
        request = self._require_request()
        if request.selection.payment_stage is not PaymentStage.DEPOSIT:
            raise RuntimeError("orders deposit intent requires deposit stage")
        payload = {
            "case_no": request.selection.case_no,
            "settlement_identity": candidate.settlement_identity.value,
            "resulting_account_version": (
                request.expected_account_version.value + 1
            ),
        }
        self._append_outbox(
            "orders_deposit_reconciled",
            "orders-deposit",
            payload,
        )

    def append_anomaly_intent(self, candidate) -> None:
        request = self._require_request()
        payload = {
            "case_no": request.selection.case_no,
            "payment_stage": request.selection.payment_stage.value,
            "bank_fact_identities": request.selection.bank_fact_identities,
            "obligation_identities": request.selection.obligation_identities,
            "bank_total_ntd": candidate.bank_total.amount,
            "obligation_total_ntd": candidate.obligation_total.amount,
            "blockers": candidate.blockers,
        }
        self._append_outbox(
            "anomaly_review_required",
            "receipt-anomaly",
            payload,
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

    def query(self, case_no: str) -> dict[str, object]:
        with _mysql_cursor(self._connection) as cursor:
            account_version = _read_account_version(cursor, case_no, lock=False)
            obligations = _query_obligations(cursor, case_no)
            bank_rows = _query_candidate_bank_rows(cursor)
        return {
            "case_no": case_no,
            "account_version": account_version,
            "obligations": obligations,
            "bank_facts": _query_bank_facts(bank_rows, case_no),
        }

    def _capture_loaded_facts(self, bank_rows, obligation_rows) -> None:
        self._bank_metadata = {
            str(row["id"]): _BankMetadata(
                int(row["id"]),
                row["transaction_date"],
            )
            for row in bank_rows
            if isinstance(row.get("transaction_date"), date)
        }
        self._obligation_amounts = {
            str(row["obligation_identity"]): int(row["amount_due_ntd"])
            for row in obligation_rows
        }

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

    def _require_request(self) -> ClientReconciliationApplyRequest:
        if self._request is None:
            raise RuntimeError("Client Receipt Apply request is not bound")
        return self._request

    def _require_settlement_identity(self) -> str:
        if self._settlement_identity is None:
            raise RuntimeError("Client Receipt settlement identity is missing")
        return self._settlement_identity


@contextmanager
def _mysql_cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except OperationalError as error:
        _raise_if_retryable(error)
        raise
    except IntegrityError as error:
        if int(error.args[0]) == 1062:
            raise ClientReceiptRepositoryUnavailable(
                "concurrent Client Receipt write requires exact retry"
            ) from error
        raise


def _raise_if_retryable(error: OperationalError) -> None:
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        raise ClientReceiptRepositoryUnavailable(
            "Client Receipt MySQL transaction is temporarily unavailable"
        ) from error


def _load_account_version(cursor, case_no, *, lock):
    if lock:
        cursor.execute(
            "INSERT IGNORE INTO client_finance_accounts "
            "(case_no,aggregate_version) VALUES (%s,0)",
            (case_no,),
        )
    return _read_account_version(cursor, case_no, lock=lock)


def _read_account_version(cursor, case_no, *, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT aggregate_version FROM client_finance_accounts "
        f"WHERE case_no=%s{suffix}",
        (case_no,),
    )
    row = cursor.fetchone()
    return 0 if row is None else int(row["aggregate_version"])


# Kept as one query so authoritative classification and ledger claim share a row lock.
def _load_selected_bank_rows(cursor, selection, *, lock):
    row_ids = tuple(
        _positive_row_id(value)
        for value in selection.bank_fact_identities
    )
    placeholders = _placeholders(row_ids)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT fir.id,fir.dedup_fingerprint,fir.format_id,"
        "fir.transaction_date,fir.debit,fir.credit,fir.direction,fir.currency,"
        "fir.cancellation_code,fir.bank_references,"
        "fir.classification_type,"
        "classification.classification_type AS authoritative_classification_type,"
        "classification.target_identities AS authoritative_target_identities,"
        "classification.reason AS authoritative_reason,"
        "selected_order.client_id AS selected_client_id,"
        "fir.reconciliation_status,"
        "ledger.id AS ledger_entry_id "
        "FROM finance_import_rows fir "
        "LEFT JOIN finance_import_classification_events classification "
        "ON classification.id=("
        "SELECT MAX(latest.id) FROM finance_import_classification_events latest "
        "WHERE latest.finance_import_row_id=fir.id) "
        "LEFT JOIN client_ledger_entries ledger "
        "ON ledger.finance_import_row_id=fir.id "
        "JOIN orders selected_order ON selected_order.case_no=%s "
        f"WHERE fir.id IN ({placeholders}) ORDER BY fir.id{suffix}",
        (selection.case_no, *row_ids),
    )
    return tuple(cursor.fetchall())


def _load_selected_obligations(cursor, selection, *, lock):
    placeholders = _placeholders(selection.obligation_identities)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT obligation_identity,case_no,obligation_type,direction,"
        "amount_due_ntd,status FROM client_obligations "
        f"WHERE obligation_identity IN ({placeholders}) "
        "AND case_no=%s AND direction='receivable_from_client' "
        "AND status='open' AND amount_due_ntd>0 "
        f"ORDER BY obligation_identity{suffix}",
        (*selection.obligation_identities, selection.case_no),
    )
    return tuple(cursor.fetchall())


def _bank_facts(bank_rows, selection):
    facts = tuple(
        _incoming_bank_fact(row, selection.payment_stage)
        for row in bank_rows
        if _bank_row_is_eligible(row, selection.case_no)
    )
    return tuple(sorted(facts, key=lambda item: item.identity))


def _incoming_bank_fact(row, payment_stage):
    amount = _integer_money(row.get("credit"))
    return IncomingBankFact(
        str(row["id"]),
        amount,
        payment_stage,
    )


def _obligation_facts(rows):
    facts = tuple(
        ClientObligation(
            str(row["obligation_identity"]),
            str(row["case_no"]),
            MoneyNTD(int(row["amount_due_ntd"])),
            PaymentStage(str(row["obligation_type"])),
        )
        for row in rows
        if str(row["obligation_type"]) in {
            stage.value for stage in _SUPPORTED_RECEIPT_STAGES
        }
    )
    return tuple(sorted(facts, key=lambda item: item.identity))


def _bank_row_is_eligible(row, case_no) -> bool:
    return (
        row.get("format_id") in {"legacy", "sinopac"}
        and row.get("direction") == "incoming"
        and _is_zero_or_none(row.get("debit"))
        and _is_positive_integer_money(row.get("credit"))
        and _classification_type(row) == "client_receipt"
        and row.get("reconciliation_status") == "pending"
        and row.get("transaction_date") is not None
        and row.get("ledger_entry_id") is None
        and _is_twd(row.get("currency"))
        and _bank_row_case_matches_selection(row, case_no)
    )


def _resolved_case_no(row) -> str | None:
    code = _cancellation_code(row)
    match = _VIRTUAL_ACCOUNT_PATTERN.fullmatch(code or "")
    if match is None:
        return None
    roc_year, sequence = match.groups()
    return f"{roc_year}{int(sequence):06d}"


def _bank_row_case_matches_selection(row, case_no) -> bool:
    if _resolved_case_no(row) == case_no:
        return True
    return _is_single_heuristic_client_candidate(row)


def _is_single_heuristic_client_candidate(row) -> bool:
    reason = row.get("authoritative_reason")
    client_id = row.get("selected_client_id")
    if not isinstance(reason, str) or not reason.startswith(
        "client_receipt_heuristic:"
    ):
        return False
    if isinstance(client_id, bool) or not isinstance(client_id, int) or client_id < 1:
        return False
    targets = _json_array(row.get("authoritative_target_identities"))
    return targets == [f"client:{client_id}"]


def _classification_type(row):
    return (
        row.get("authoritative_classification_type")
        or row.get("classification_type")
    )


def _cancellation_code(row) -> str | None:
    canonical = row.get("cancellation_code")
    if isinstance(canonical, str) and canonical.strip():
        return canonical.strip()
    references = _json_object(row.get("bank_references"))
    fallback = references.get("銷帳編號")
    return fallback.strip() if isinstance(fallback, str) else None


def _json_array(value) -> list[object]:
    decoded = json.loads(value) if isinstance(value, str) else value
    return decoded if isinstance(decoded, list) else []


def _integer_money(value) -> MoneyNTD:
    amount = Decimal(str(value))
    if amount <= 0 or amount != amount.to_integral_value():
        raise ValueError("bank_fact_not_eligible")
    return MoneyNTD(int(amount))


def _is_positive_integer_money(value) -> bool:
    try:
        _integer_money(value)
        return True
    except (InvalidOperation, ValueError, TypeError):
        return False


def _is_zero_or_none(value) -> bool:
    if value is None:
        return True
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def _is_twd(value) -> bool:
    return value is None or str(value).upper() in {"TWD", "NTD"}


def _allocated_amounts_by_bank(candidate):
    amounts: dict[str, int] = {}
    for allocation in candidate.allocations:
        identity = allocation.bank_fact_identity
        amounts[identity] = amounts.get(identity, 0) + allocation.amount.amount
    if sum(amounts.values()) != candidate.bank_total.amount:
        raise RuntimeError("Client Receipt bank allocations are incomplete")
    return amounts


# Kept cohesive so immutable entry insertion and source-row claiming cannot drift.
def _insert_ledger_entry(
    cursor,
    request,
    candidate,
    bank_identity,
    amount,
    metadata,
    ordinal,
):
    cursor.execute(
        _LEDGER_INSERT_SQL,
        (
            request.selection.case_no,
            metadata.row_id,
            amount,
            metadata.occurred_on,
            candidate.settlement_identity.value,
            _child_key(request, "ledger", ordinal),
            request.actor.actor_id,
            request.reason,
        ),
    )
    entry_id = int(cursor.lastrowid or 0)
    if entry_id <= 0:
        raise RuntimeError("Client Receipt ledger identity was not generated")
    return entry_id


def _mark_bank_row_reconciled(cursor, row_id, settlement_identity):
    cursor.execute(
        "UPDATE finance_import_rows SET reconciliation_status='reconciled',"
        "reconciliation_reference=%s,reconciled_at=CURRENT_TIMESTAMP "
        "WHERE id=%s AND reconciliation_status='pending'",
        (f"client-finance:{settlement_identity}", row_id),
    )
    if int(cursor.rowcount) != 1:
        raise RuntimeError("Client Receipt bank fact state changed during Apply")


def _insert_allocation(cursor, entry_ids, allocation, ordinal):
    entry_id = entry_ids.get(allocation.bank_fact_identity)
    if entry_id is None:
        raise RuntimeError("Client Receipt allocation ledger entry is missing")
    cursor.execute(
        _ALLOCATION_INSERT_SQL,
        (
            entry_id,
            allocation.obligation_identity,
            allocation.amount.amount,
            ordinal,
        ),
    )


# Kept cohesive because this aggregate is the exact-zero persistence guard.
def _load_persisted_allocation_totals(
    cursor,
    obligation_identities,
    settlement_identity,
):
    placeholders = _placeholders(obligation_identities)
    cursor.execute(
        "SELECT allocation.obligation_identity,"
        "SUM(allocation.amount_ntd) AS allocated_amount_ntd "
        "FROM client_ledger_obligation_allocations allocation "
        "JOIN client_ledger_entries ledger "
        "ON ledger.id=allocation.ledger_entry_id "
        f"WHERE allocation.obligation_identity IN ({placeholders}) "
        "AND ledger.reconciliation_reference=%s "
        "GROUP BY allocation.obligation_identity "
        "ORDER BY allocation.obligation_identity",
        (*obligation_identities, settlement_identity),
    )
    return {
        str(row["obligation_identity"]): int(row["allocated_amount_ntd"])
        for row in cursor.fetchall()
    }


def _validate_exact_zero(obligation_amounts, allocated_amounts) -> None:
    if obligation_amounts != allocated_amounts:
        raise RuntimeError("Client Receipt selected obligations are not exactly zero")


# Kept cohesive so every selected obligation enforces the same CAS invariant.
def _settle_selected_obligations(
    cursor,
    selection,
    obligation_amounts,
    resulting_version,
):
    for identity in selection.obligation_identities:
        cursor.execute(
            "UPDATE client_obligations SET amount_due_ntd=0,status='settled',"
            "projection_version=%s "
            "WHERE obligation_identity=%s AND case_no=%s "
            "AND status='open' AND amount_due_ntd=%s",
            (
                resulting_version,
                identity,
                selection.case_no,
                obligation_amounts[identity],
            ),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("Client Receipt obligation projection changed")


def _advance_account_version(cursor, request, resulting_version):
    cursor.execute(
        "UPDATE client_finance_accounts SET aggregate_version=%s "
        "WHERE case_no=%s AND aggregate_version=%s",
        (
            resulting_version,
            request.selection.case_no,
            request.expected_account_version.value,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise RuntimeError("client_finance_candidate_stale")


def _upsert_deposit_settlement_projection(
    cursor,
    selection,
    obligation_amounts,
    ledger_entry_ids,
    settlement_identity,
    resulting_version,
):
    if selection.payment_stage is not PaymentStage.DEPOSIT:
        return
    if len(selection.obligation_identities) != 1:
        raise RuntimeError("deposit receipt must settle exactly one obligation")
    obligation_identity = selection.obligation_identities[0]
    contracted_amount = obligation_amounts[obligation_identity]
    latest_ledger_entry_id = max(ledger_entry_ids.values())
    cursor.execute(
        _DEPOSIT_SETTLEMENT_UPSERT_SQL,
        (
            selection.case_no,
            obligation_identity,
            contracted_amount,
            contracted_amount,
            settlement_identity,
            settlement_identity,
            resulting_version,
            latest_ledger_entry_id,
        ),
    )


def _append_projection_outbox(
    cursor,
    request,
    settlement_identity,
    resulting_version,
):
    payload = {
        "case_no": request.selection.case_no,
        "settlement_identity": settlement_identity,
        "resulting_account_version": resulting_version,
    }
    cursor.execute(
        _OUTBOX_INSERT_SQL,
        (
            request.selection.case_no,
            "projection_refresh",
            _outbox_key(request, "projection"),
            _canonical_json(payload),
        ),
    )


def _query_obligations(cursor, case_no):
    cursor.execute(
        "SELECT obligation_identity,obligation_type,amount_due_ntd,due_date "
        "FROM client_obligations WHERE case_no=%s "
        "AND direction='receivable_from_client' AND status='open' "
        "AND amount_due_ntd>0 "
        "AND obligation_type IN ('deposit','first','second','adjustment') "
        "ORDER BY due_date,obligation_identity",
        (case_no,),
    )
    return tuple(
        {
            "obligation_identity": str(row["obligation_identity"]),
            "payment_stage": str(row["obligation_type"]),
            "amount_due_ntd": int(row["amount_due_ntd"]),
            "due_date": row.get("due_date"),
        }
        for row in cursor.fetchall()
    )


# Kept as one query so source eligibility filtering remains database-side.
def _query_candidate_bank_rows(cursor):
    cursor.execute(
        "SELECT fir.id,fir.dedup_fingerprint,fir.format_id,"
        "fir.transaction_date,fir.debit,fir.credit,fir.direction,fir.currency,"
        "fir.cancellation_code,fir.bank_references,"
        "fir.classification_type,"
        "classification.classification_type AS authoritative_classification_type,"
        "fir.reconciliation_status,"
        "ledger.id AS ledger_entry_id "
        "FROM finance_import_rows fir "
        "LEFT JOIN finance_import_classification_events classification "
        "ON classification.id=("
        "SELECT MAX(latest.id) FROM finance_import_classification_events latest "
        "WHERE latest.finance_import_row_id=fir.id) "
        "LEFT JOIN client_ledger_entries ledger "
        "ON ledger.finance_import_row_id=fir.id "
        "WHERE COALESCE(classification.classification_type,"
        "fir.classification_type)='client_receipt' "
        "AND fir.reconciliation_status='pending' "
        "AND fir.direction='incoming' "
        "AND fir.format_id IN ('legacy','sinopac') "
        "AND fir.credit>0 "
        "AND (fir.debit IS NULL OR fir.debit=0) "
        "AND (fir.currency IS NULL OR fir.currency IN ('TWD','NTD')) "
        "AND fir.transaction_date IS NOT NULL "
        "AND ledger.id IS NULL "
        "ORDER BY fir.transaction_date,fir.id",
    )
    return tuple(cursor.fetchall())


def _query_bank_facts(rows, case_no):
    return tuple(
        {
            "finance_import_row_id": int(row["id"]),
            "amount_ntd": _integer_money(row["credit"]).amount,
            "transaction_date": row["transaction_date"],
            "dedup_fingerprint": str(row["dedup_fingerprint"]),
        }
        for row in rows
        if _bank_row_is_eligible(row, case_no)
    )


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "account_version": receipt.account_version,
        "status": receipt.status.value,
        "settlement_identity": receipt.settlement_identity.value,
        "ledger_entry_count": receipt.ledger_entry_count,
        "allocation_count": receipt.allocation_count,
        "blockers": receipt.blockers,
    }


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = ClientReconciliationReceipt(
        str(payload["case_no"]),
        int(payload["account_version"]),
        ReconciliationStatus(str(payload["status"])),
        PreviewFingerprint(str(payload["settlement_identity"])),
        int(payload["ledger_entry_count"]),
        int(payload["allocation_count"]),
        tuple(str(item) for item in payload.get("blockers", ())),
    )
    return StoredClientReconciliationReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _child_key(request, purpose, ordinal):
    digest = hashlib.sha256(
        f"{request.idempotency_key.value}:{purpose}:{ordinal}".encode("utf-8")
    ).hexdigest()
    return f"client-receipt:{digest}"


def _outbox_key(request, purpose):
    digest = hashlib.sha256(
        f"{request.idempotency_key.value}:{purpose}".encode("utf-8")
    ).hexdigest()
    return f"client-finance:{digest}"


def _canonical_json(payload):
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _json_object(value) -> Mapping[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise ValueError("bank_references_must_be_json_object")
    return parsed


def _positive_row_id(value):
    try:
        row_id = int(value)
    except (TypeError, ValueError):
        return -1
    return row_id if row_id > 0 else -1


def _placeholders(values):
    return ",".join("%s" for _ in values) if values else "NULL"


_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,result_snapshot "
    "FROM client_finance_apply_receipts "
    "WHERE idempotency_key=%s FOR UPDATE"
)
_LEDGER_INSERT_SQL = (
    "INSERT INTO client_ledger_entries "
    "(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
    "reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) "
    "VALUES (%s,%s,'receipt',%s,%s,%s,NULL,%s,%s,%s)"
)
_ALLOCATION_INSERT_SQL = (
    "INSERT INTO client_ledger_obligation_allocations "
    "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) "
    "VALUES (%s,%s,%s,%s)"
)
_DEPOSIT_SETTLEMENT_UPSERT_SQL = (
    "INSERT INTO client_deposit_settlement_projection "
    "(case_no,deposit_obligation_identity,settlement_state,contracted_amount_ntd,"
    "allocated_net_amount_ntd,settlement_identity,source_fingerprint,"
    "projection_version,latest_ledger_entry_id) "
    "VALUES (%s,%s,'settled',%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE "
    "deposit_obligation_identity=VALUES(deposit_obligation_identity),"
    "settlement_state=VALUES(settlement_state),"
    "contracted_amount_ntd=VALUES(contracted_amount_ntd),"
    "allocated_net_amount_ntd=VALUES(allocated_net_amount_ntd),"
    "settlement_identity=VALUES(settlement_identity),"
    "source_fingerprint=VALUES(source_fingerprint),"
    "projection_version=VALUES(projection_version),"
    "latest_ledger_entry_id=VALUES(latest_ledger_entry_id)"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO client_finance_outbox "
    "(case_no,intent_type,intent_key,payload_snapshot) "
    "VALUES (%s,%s,%s,%s)"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO client_finance_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,case_no,"
    "resulting_account_version,result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s)"
)

__all__ = [
    "ClientReceiptMySqlUnitOfWork",
    "ClientReceiptRepositoryUnavailable",
    "MySqlClientReceiptReconciliationRepository",
]
