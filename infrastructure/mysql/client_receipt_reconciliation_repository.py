"""MySQL facts and atomic persistence for Client Receipt reconciliation."""

from __future__ import annotations

from infrastructure.mysql.beclass_refund_account import load_effective_refund_account

from contextlib import contextmanager
from dataclasses import dataclass, replace
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
    UnreceivedDepositConfirmation,
)
from domains.finance_import.cancellation_code import resolve_finance_cancellation_code
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationFacts,
    ClientReconciliationReceipt,
    StoredClientReconciliationReceipt,
)
from subsystems.client_finance.virtual_account_resolution import resolve_client_virtual_account

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
    amount_ntd: int


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
        self._obligation_stages: dict[str, PaymentStage] = {}
        self._settled_stages: set[PaymentStage] = set()
        self._settlement_identity: str | None = None

    def query_unreceived_deposit(self, case_no: str) -> UnreceivedDepositConfirmation:
        """Borrow the release UoW; lock Finance before reading complete formal payment history."""
        if not isinstance(case_no, str) or not case_no or case_no.strip() != case_no or len(case_no) > 50:
            raise ValueError("client_finance_case_no_invalid")
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute("SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE", (case_no,))
            account = cursor.fetchone()
            cursor.execute("SELECT obligation_identity FROM client_obligations WHERE case_no=%s ORDER BY obligation_identity FOR UPDATE", (case_no,))
            obligations = tuple(sorted(row['obligation_identity'] for row in cursor.fetchall()))
            cursor.execute("SELECT id FROM client_obligation_events WHERE case_no=%s ORDER BY id FOR UPDATE", (case_no,))
            events = tuple(row['id'] for row in cursor.fetchall())
            cursor.execute("SELECT id FROM client_ledger_entries WHERE case_no=%s ORDER BY id FOR UPDATE", (case_no,))
            entries = tuple(row['id'] for row in cursor.fetchall())
        return UnreceivedDepositConfirmation(
            case_no, None if account is None else account['aggregate_version'], obligations, events, entries,
        )

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
        self._obligation_stages.clear()
        self._settled_stages.clear()
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
        amounts = _bank_amounts(candidate, self._bank_metadata)
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
            partial = selection.allow_partial_receipt and sum(allocated.values()) < sum(self._obligation_amounts.values())
            if partial:
                if sum(allocated.values()) != sum(row.amount_ntd for row in self._bank_metadata.values()):
                    raise RuntimeError("client_receipt_partial_cash_not_conserved")
                _apply_partial_allocations(cursor, selection, self._obligation_amounts, allocated, resulting_version)
            else:
                _validate_exact_zero(self._obligation_amounts, allocated)
                _settle_selected_obligations(cursor, selection, self._obligation_amounts, resulting_version)
            _advance_account_version(cursor, request, resulting_version)
            cash_totals = _effective_receipt_allocations(cursor, selection.obligation_identities)
            self._settled_stages = {stage for stage in self._obligation_stages.values()
                if all(allocated.get(identity, 0) == self._obligation_amounts[identity]
                       for identity, value in self._obligation_stages.items() if value is stage)}
            deposit_ids = tuple(identity for identity, stage in self._obligation_stages.items() if stage is PaymentStage.DEPOSIT)
            if PaymentStage.DEPOSIT in self._settled_stages:
                _upsert_deposit_settlement_projection(
                    cursor, replace(selection, payment_stage=PaymentStage.DEPOSIT, obligation_identities=deposit_ids), self._obligation_amounts,
                    self._ledger_entry_ids, settlement_identity, resulting_version,
                    settled_amounts=cash_totals,
                )
            for stage in sorted(set(self._obligation_stages.values()), key=lambda value:value.value):
                identities = tuple(identity for identity, value in self._obligation_stages.items() if value is stage)
                stage_request = replace(request, selection=replace(selection, payment_stage=stage, obligation_identities=identities))
                _append_projection_outbox(cursor, stage_request, settlement_identity, resulting_version,
                    {identity:self._obligation_amounts[identity] for identity in identities},
                    fully_settled=stage in self._settled_stages,
                    receipt_amounts={identity:allocated.get(identity,0) for identity in identities},
                    purpose='projection' if selection.payment_stage is not None else 'projection:'+stage.value)
            from infrastructure.mysql.automatic_client_accounting import synchronize_terminal_subsidy_return
            synchronize_terminal_subsidy_return(cursor, selection.case_no, actor=request.actor,
                key=request.idempotency_key, correlation_id=request.correlation_id,
                source_family="client-receipt", source_id=resulting_version, advance_version=False)

    def establish_overage_refund(self, candidate, resulting_version) -> None:
        if candidate.status is not ReconciliationStatus.OVERAGE:
            return
        request = self._require_request()
        allocated = {}
        target = {}
        for allocation in candidate.allocations:
            allocated[allocation.bank_fact_identity] = allocated.get(allocation.bank_fact_identity, 0) + allocation.amount.amount
            target[allocation.bank_fact_identity] = allocation.obligation_identity
        for ordinal, identity in enumerate(sorted(self._bank_metadata), start=1):
            surplus = self._bank_metadata[identity].amount_ntd - allocated.get(identity, 0)
            if surplus <= 0:
                continue
            self._establish_source_overage(candidate, resulting_version, identity, surplus,
                target.get(identity, candidate.allocations[-1].obligation_identity), ordinal)

    def _establish_source_overage(self, candidate, resulting_version, bank_identity, surplus, obligation_identity, ordinal):
        request = self._require_request()
        receipt_ledger_entry_id = self._ledger_entry_ids[bank_identity]
        seed = candidate.settlement_identity.value
        if len(self._bank_metadata) > 1:
            seed = hashlib.sha256((seed + ':' + bank_identity).encode()).hexdigest()
        refund_identity = _overage_refund_identity(seed)
        source_identity = f"receipt-overage:{seed}"
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _OVERAGE_REFUND_EVENT_INSERT_SQL,
                (
                    refund_identity,
                    request.selection.case_no,
                    surplus,
                    source_identity,
                    obligation_identity,
                    request.expected_account_version.value,
                    _child_key(request, "overage-refund-event", ordinal),
                    request.actor.actor_id,
                    request.reason,
                ),
            )
            event_id = int(cursor.lastrowid or 0)
            if event_id <= 0:
                raise RuntimeError("client_receipt_overage_event_missing")
            cursor.execute(
                _OVERAGE_REFUND_PROJECTION_INSERT_SQL,
                (
                    refund_identity,
                    request.selection.case_no,
                    obligation_identity,
                    surplus,
                    event_id,
                    resulting_version,
                ),
            )
            _insert_refund_recipient_snapshot(
                cursor, refund_identity, request.selection.case_no, "receipt_overage"
            )
            cursor.execute(
                _OVERAGE_DISPOSITION_INSERT_SQL,
                (
                    request.selection.case_no,
                    self._bank_metadata[bank_identity].row_id,
                    receipt_ledger_entry_id,
                    obligation_identity,
                    refund_identity,
                    surplus,
                    candidate.settlement_identity.value,
                    _child_key(request, "overage-disposition", ordinal),
                    request.actor.actor_id,
                    request.reason,
                ),
            )

    def append_orders_deposit_intent(self, candidate) -> None:
        request = self._require_request()
        if request.selection.payment_stage is None and PaymentStage.DEPOSIT not in self._settled_stages:
            return
        if request.selection.payment_stage is not None and request.selection.payment_stage is not PaymentStage.DEPOSIT:
            raise RuntimeError("orders deposit intent requires deposit stage")
        payload = {
            "case_no": request.selection.case_no,
            "settlement_identity": candidate.settlement_identity.value,
            "line_deposit_notification": True,
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
            "payment_stage": request.selection.payment_stage.value if request.selection.payment_stage is not None else None,
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
            bank_rows = _query_candidate_bank_rows(cursor, case_no)
            for row in bank_rows:
                resolution = resolve_client_virtual_account(cursor, _cancellation_code(row))
                row['resolved_virtual_account_case_no'] = resolution['case_no'] if resolution['result']=='resolved' else None
                row['selected_case_obligation_identities'] = frozenset(item['obligation_identity'] for item in obligations)
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
                _integer_money(row["credit"]).amount,
            )
            for row in bank_rows
            if isinstance(row.get("transaction_date"), date)
        }
        self._obligation_amounts = {
            str(row["obligation_identity"]): int(row["amount_due_ntd"])
            for row in obligation_rows
        }
        self._obligation_stages = {str(row['obligation_identity']):PaymentStage(str(row['obligation_type'])) for row in obligation_rows}

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
        "classification.disposition AS authoritative_disposition,"
        "EXISTS(SELECT 1 FROM finance_import_integrity_events issue WHERE issue.finance_import_row_id=fir.id "
        "AND issue.active=1 AND issue.id=(SELECT MAX(latest.id) FROM finance_import_integrity_events latest "
        "WHERE latest.batch_id=issue.batch_id AND latest.finance_import_row_id=issue.finance_import_row_id "
        "AND latest.issue_code=issue.issue_code)) AS has_active_integrity,"
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
    rows = tuple(cursor.fetchall())
    for row in rows:
        resolution = resolve_client_virtual_account(cursor, _cancellation_code(row))
        row["resolved_virtual_account_case_no"] = (
            resolution["case_no"] if resolution["result"] == "resolved" else None
        )
    return rows


def _load_selected_obligations(cursor, selection, *, lock):
    placeholders = _placeholders(selection.obligation_identities)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT obligation_identity,case_no,obligation_type,direction,due_date,"
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
        if _bank_row_is_eligible(row, selection)
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
            row.get('due_date'),
        )
        for row in rows
        if str(row["obligation_type"]) in {
            stage.value for stage in _SUPPORTED_RECEIPT_STAGES
        }
    )
    return tuple(sorted(facts, key=lambda item: item.identity))


def _bank_row_is_eligible(row, selection) -> bool:
    return (
        row.get("format_id") in {"legacy", "sinopac", "taishin"}
        and row.get("direction") == "incoming"
        and _is_zero_or_none(row.get("debit"))
        and _is_positive_integer_money(row.get("credit"))
        and _classification_type(row) == "client_receipt"
        and row.get("authoritative_disposition") != "blocked"
        and not row.get("has_active_integrity", False)
        and row.get("reconciliation_status") == "pending"
        and row.get("transaction_date") is not None
        and row.get("ledger_entry_id") is None
        and _is_twd(row.get("currency"))
        and _bank_row_matches_selection(row, selection)
    )


def _resolved_case_no(row) -> str | None:
    if "resolved_virtual_account_case_no" in row:
        value = row.get("resolved_virtual_account_case_no")
        return str(value) if value is not None else None
    code = _cancellation_code(row)
    match = _VIRTUAL_ACCOUNT_PATTERN.fullmatch(code or "")
    if match is None:
        return None
    roc_year, sequence = match.groups()
    return f"{roc_year}{int(sequence):06d}"


def _bank_row_matches_selection(row, selection) -> bool:
    if isinstance(selection, str):
        return _matches_legacy_case_selection(row, selection)
    if _resolved_case_no(row) == selection.case_no:
        return True
    if _is_single_heuristic_client_candidate(row):
        return True
    return _has_exact_authoritative_targets(row, selection)


def _matches_legacy_case_selection(row, case_no: str) -> bool:
    if _resolved_case_no(row) == case_no:
        return True
    targets = _json_array(row.get('authoritative_target_identities'))
    exact_case_targets = bool(targets) and set(targets) <= row.get('selected_case_obligation_identities', frozenset())
    return _is_single_heuristic_client_candidate(row) or exact_case_targets


def _has_exact_authoritative_targets(row, selection) -> bool:
    if _classification_type(row) != "client_receipt":
        return False
    targets = _json_array(row.get("authoritative_target_identities"))
    if selection.payment_stage is None:
        return bool(targets) and set(targets) <= set(selection.obligation_identities)
    return tuple(sorted(targets)) == selection.obligation_identities


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
    return resolve_finance_cancellation_code({
        "format_id": row.get("format_id"),
        "cancellation_code": row.get("cancellation_code"),
        "bank_references": _json_object(row.get("bank_references")),
    })["cancellation_code"]


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


def _bank_amounts(candidate, metadata):
    amounts = {identity: item.amount_ntd for identity, item in metadata.items()}
    if sum(amounts.values()) != candidate.bank_total.amount:
        raise RuntimeError("Client Receipt bank facts do not match preview")
    return amounts


def _overage_refund_identity(settlement_identity: str) -> str:
    return f"refund:overage:{settlement_identity[:48]}"


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


def _effective_receipt_allocations(cursor, identities):
    cursor.execute(
        "SELECT allocation.obligation_identity,SUM(CASE WHEN ledger.entry_type='receipt' THEN allocation.amount_ntd "
        "WHEN ledger.entry_type='reversal' AND original.entry_type='receipt' THEN -allocation.amount_ntd ELSE 0 END) AS amount_ntd "
        "FROM client_ledger_obligation_allocations allocation JOIN client_ledger_entries ledger ON ledger.id=allocation.ledger_entry_id "
        "LEFT JOIN client_ledger_entries original ON original.id=ledger.reversal_of_entry_id "
        f"WHERE allocation.obligation_identity IN ({_placeholders(identities)}) GROUP BY allocation.obligation_identity", tuple(identities))
    return {str(row['obligation_identity']):int(row['amount_ntd']) for row in cursor.fetchall()}


def _apply_partial_allocations(cursor, selection, obligation_amounts, allocated_amounts, resulting_version):
    if set(allocated_amounts) - set(obligation_amounts) or not 0 < sum(allocated_amounts.values()) < sum(obligation_amounts.values()):
        raise RuntimeError("client_receipt_partial_allocation_invalid")
    for identity in selection.obligation_identities:
        allocated = allocated_amounts.get(identity, 0)
        before = obligation_amounts[identity]
        if not 0 <= allocated <= before:
            raise RuntimeError("client_receipt_partial_allocation_invalid")
        remaining = before - allocated
        cursor.execute(
            "UPDATE client_obligations SET amount_due_ntd=%s,status=%s,projection_version=%s "
            "WHERE obligation_identity=%s AND case_no=%s AND status='open' AND amount_due_ntd=%s",
            (remaining, 'open' if remaining else 'settled', resulting_version, identity, selection.case_no, before))
        if cursor.rowcount != 1:
            raise RuntimeError("client_finance_candidate_stale")

        cursor.execute("INSERT IGNORE INTO client_finance_amount_controls(obligation_identity,case_no,amount_mode,computed_ntd,effective_ntd) "
            "SELECT o.obligation_identity,o.case_no,'automatic',e.after_amount_ntd,e.after_amount_ntd "
            "FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id "
            "WHERE o.obligation_identity=%s AND o.obligation_type IN ('deposit','first','second')",(identity,))


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
    *, settled_amounts=None,
):
    if selection.payment_stage is not PaymentStage.DEPOSIT:
        return
    if len(selection.obligation_identities) != 1:
        raise RuntimeError("deposit receipt must settle exactly one obligation")
    obligation_identity = selection.obligation_identities[0]
    contracted_amount = (settled_amounts if settled_amounts is not None else obligation_amounts)[obligation_identity]
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
    obligation_amounts,
    *, fully_settled=True, receipt_amounts=None, purpose='projection',
):
    payload = {
        "case_no": request.selection.case_no,
        "settlement_identity": settlement_identity,
        "resulting_account_version": resulting_version,
    }
    if fully_settled and request.selection.payment_stage in (PaymentStage.FIRST,PaymentStage.SECOND):
        stage=request.selection.payment_stage.value
        payload.update({f'line_{stage}_payment_notification':True}, payment_stage=stage,
                       obligation_identities=list(request.selection.obligation_identities),
                       amount_ntd=sum((receipt_amounts if receipt_amounts is not None else obligation_amounts).values()))
    cursor.execute(
        _OUTBOX_INSERT_SQL,
        (
            request.selection.case_no,
            "projection_refresh",
            _outbox_key(request, purpose),
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
def _query_candidate_bank_rows(cursor, case_no):
    cursor.execute(
        "SELECT fir.id,fir.dedup_fingerprint,fir.format_id,"
        "fir.transaction_date,fir.debit,fir.credit,fir.direction,fir.currency,"
        "fir.cancellation_code,fir.bank_references,"
        "fir.classification_type,"
        "classification.classification_type AS authoritative_classification_type,"
        "classification.disposition AS authoritative_disposition,"
        "EXISTS(SELECT 1 FROM finance_import_integrity_events issue WHERE issue.finance_import_row_id=fir.id "
        "AND issue.active=1 AND issue.id=(SELECT MAX(latest.id) FROM finance_import_integrity_events latest "
        "WHERE latest.batch_id=issue.batch_id AND latest.finance_import_row_id=issue.finance_import_row_id "
        "AND latest.issue_code=issue.issue_code)) AS has_active_integrity,"
        "classification.target_identities AS authoritative_target_identities,"
        "classification.reason AS authoritative_reason,selected_order.client_id AS selected_client_id,"
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
        "ORDER BY fir.transaction_date,fir.id", (case_no,),
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
_OVERAGE_REFUND_EVENT_INSERT_SQL = (
    "INSERT INTO client_obligation_events "
    "(obligation_identity,case_no,obligation_type,direction,event_type,"
    "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,"
    "source_event_identity,source_obligation_identity,expected_account_version,"
    "idempotency_key,actor,reason) "
    "VALUES (%s,%s,'refund','payable_to_client','established',0,%s,NULL,NULL,"
    "%s,%s,%s,%s,%s,%s)"
)
_OVERAGE_REFUND_PROJECTION_INSERT_SQL = (
    "INSERT INTO client_obligations "
    "(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,"
    "amount_due_ntd,due_date,status,current_event_id,projection_version) "
    "VALUES (%s,%s,'refund','payable_to_client',%s,%s,NULL,'open',%s,%s)"
)
_OVERAGE_DISPOSITION_INSERT_SQL = (
    "INSERT INTO client_receipt_overage_dispositions "
    "(case_no,finance_import_row_id,receipt_ledger_entry_id,receivable_obligation_identity,"
    "refund_obligation_identity,overage_amount_ntd,settlement_identity,idempotency_key,actor,reason) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)


def _insert_refund_recipient_snapshot(cursor, refund_identity, case_no, source_kind, *, require_complete=True) -> bool:
    cursor.execute('SELECT refund_obligation_identity FROM client_refund_recipient_snapshots WHERE refund_obligation_identity=%s', (refund_identity,))
    if cursor.fetchone() is not None:
        return False
    account = load_effective_refund_account(cursor, case_no)
    if account is None:
        if require_complete:
            raise ValueError("client_refund_recipient_snapshot_missing")
        return False
    cursor.execute(
        'INSERT INTO client_refund_recipient_snapshots '
        '(refund_obligation_identity,case_no,bank_code,bank_account,source_kind) VALUES (%s,%s,%s,%s,%s)',
        (refund_identity, case_no, account.bank_code,
         account.account_no, source_kind),
    )
    if cursor.rowcount != 1:
        raise ValueError("client_refund_recipient_snapshot_missing")
    return True


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
