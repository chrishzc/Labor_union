"""MySQL facts and atomic persistence for client refund and reversal."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Iterator, Mapping

from pymysql.err import IntegrityError, OperationalError

from domains.client_finance.client_refund_reversal import (
    ClientFinanceCorrectionType,
    ClientLedgerAllocationFact,
    ClientRefundBankFact,
    ClientRefundObligation,
    ClientRefundPurpose,
    ClientRefundReturnBankFact,
    ClientReversalTarget,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalApplyRequest,
    ClientRefundReversalFacts,
    ClientRefundReversalReceipt,
    ClientRefundReversalStorageError,
    StoredClientRefundReversalReceipt,
)

_RETRYABLE_MYSQL_CODES = frozenset({1062, 1205, 1213})


class ClientRefundReversalMySqlUnitOfWork(MySqlUnitOfWork):
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


class MySqlClientRefundReversalRepository:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._request: ClientRefundReversalApplyRequest | None = None
        self._entry_ids: dict[str, int] = {}
        self._refund_row_metadata: dict[str, tuple[int, date]] = {}

    def bind_apply_request(self, request) -> None:
        self._request = request

    def clear_apply_request(self) -> None:
        self._request = None
        self._entry_ids.clear()
        self._refund_row_metadata.clear()

    def load(self, selection, *, for_update):
        with _mysql_cursor(self._connection) as cursor:
            if not _case_exists(cursor, selection.case_no):
                raise ValueError("client_finance_case_not_found")
            version = _load_account_version(
                cursor,
                selection.case_no,
                lock=for_update,
            )
            if selection.correction_type in {
                ClientFinanceCorrectionType.REFUND,
                ClientFinanceCorrectionType.REFUND_OVERAGE,
            }:
                facts = self._load_refund(cursor, selection, for_update)
            elif selection.correction_type is ClientFinanceCorrectionType.REFUND_RETURN:
                facts = self._load_refund_return(cursor, selection, for_update)
            else:
                facts = self._load_reversal(cursor, selection, for_update)
        return ClientRefundReversalFacts(version, **facts)

    def find_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def append_ledger_entries(self, candidate) -> None:
        request = self._require_request()
        with _mysql_cursor(self._connection) as cursor:
            for ordinal, entry in enumerate(candidate.entries, start=1):
                entry_id = _insert_ledger_entry(cursor, request, candidate, entry, ordinal)
                self._entry_ids[entry.identity] = entry_id
                self._claim_refund_row(cursor, candidate, entry)

    def append_allocations(self, candidate) -> None:
        ordinals: dict[str, int] = {}
        with _mysql_cursor(self._connection) as cursor:
            for allocation in candidate.allocations:
                ordinal = ordinals.get(allocation.entry_identity, 0) + 1
                ordinals[allocation.entry_identity] = ordinal
                _insert_allocation(cursor, self._entry_ids, allocation, ordinal)

    def update_projection(self, candidate, resulting_version) -> None:
        request = self._require_request()
        with _mysql_cursor(self._connection) as cursor:
            totals = _persisted_allocation_totals(cursor, candidate)
            if candidate.correction_type in {
                ClientFinanceCorrectionType.REFUND,
                ClientFinanceCorrectionType.REFUND_OVERAGE,
            }:
                _settle_refund_obligations(cursor, candidate, totals, resulting_version)
                _persist_underpayment_source(
                    cursor, request, candidate, resulting_version, self._refund_row_metadata
                )
            elif candidate.reversal_entry_type in {"refund", "subsidy_return"}:
                _reopen_payable_obligations(cursor, candidate, totals, resulting_version)
            else:
                _reopen_receivable_obligations(cursor, candidate, totals, resulting_version)
            _advance_account_version(cursor, request, resulting_version)

    def establish_over_refund_recovery(self, candidate, resulting_version) -> None:
        if candidate.correction_type is not ClientFinanceCorrectionType.REFUND_OVERAGE:
            return
        if len(candidate.entries) != 1 or len(candidate.affected_obligations) != 1:
            raise RuntimeError("client_refund_overage_requires_one_bank_and_obligation")
        request = self._require_request()
        entry_identity = candidate.entries[0].identity
        ledger_entry_id = self._entry_ids.get(entry_identity)
        if ledger_entry_id is None:
            raise RuntimeError("client_refund_overage_ledger_missing")
        recovery_identity = _over_refund_recovery_identity(candidate.fingerprint.value)
        refund_identity = candidate.affected_obligations[0]
        bank_row_id, _ = self._refund_row_metadata[
            candidate.entries[0].finance_import_row_identity
        ]
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _OVER_REFUND_RECOVERY_INSERT_SQL,
                (
                    recovery_identity,
                    candidate.case_no,
                    bank_row_id,
                    ledger_entry_id,
                    refund_identity,
                    candidate.recovery_amount.amount,
                    _child_key(request, "over-refund-recovery", 1),
                    request.actor.actor_id,
                    request.reason,
                    resulting_version,
                ),
            )
            cursor.execute(
                _OVER_REFUND_RECOVERY_EVENT_INSERT_SQL,
                (
                    recovery_identity,
                    candidate.recovery_amount.amount,
                    _child_key(request, "over-refund-recovery-event", 1),
                    request.actor.actor_id,
                    request.reason,
                ),
            )

    def append_outbox(self, candidate, resulting_version) -> None:
        request = self._require_request()
        payload = {
            "case_no": candidate.case_no,
            "correction_type": candidate.correction_type.value,
            "correction_identity": candidate.fingerprint.value,
            "affected_obligations": candidate.affected_obligations,
            "resulting_account_version": resulting_version,
        }
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                (
                    candidate.case_no,
                    _child_key(request, "projection", 0),
                    _canonical_json(payload),
                ),
            )
            if request.selection.allow_partial_refund_recovery:
                cursor.execute(
                    _UNDERPAYMENT_OUTBOX_INSERT_SQL,
                    (candidate.case_no, _child_key(request, "refund-underpayment-outbox", 1), _canonical_json({"underpayment_identity": f"client-refund-underpayment:{candidate.fingerprint.value}"})),
                )

    def save_receipt(self, key, stored_receipt) -> None:
        request = self._require_request()
        receipt = stored_receipt.receipt
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (
                    key.value,
                    receipt.correction_type.value,
                    stored_receipt.command_fingerprint.value,
                    request.preview_fingerprint.value,
                    receipt.case_no,
                    receipt.account_version,
                    _canonical_json(_receipt_payload(receipt)),
                ),
            )

    def query(self, case_no: str):
        with _mysql_cursor(self._connection) as cursor:
            if not _case_exists(cursor, case_no):
                raise ValueError("client_finance_case_not_found")
            version = _read_account_version(cursor, case_no, lock=False)
            refunds = _query_payable_obligations(
                cursor,
                case_no,
                ClientRefundPurpose.CUSTOMER_REFUND,
            )
            subsidy_returns = _query_payable_obligations(
                cursor,
                case_no,
                ClientRefundPurpose.SUBSIDY_RETURN,
            )
            targets = _query_reversal_targets(cursor, case_no, "receipt")
            refund_return_targets = _query_reversal_targets(cursor, case_no, "refund")
        return {
            "case_no": case_no,
            "account_version": version,
            "refund_obligations": refunds,
            "subsidy_return_obligations": subsidy_returns,
            "reversal_targets": targets,
            "refund_return_targets": refund_return_targets,
        }

    def _load_refund(self, cursor, selection, lock):
        bank_rows = _load_refund_bank_rows(
            cursor,
            selection.bank_fact_identities,
            lock,
        )
        obligation_rows = _load_refund_obligation_rows(cursor, selection, lock)
        recipient_account = _single_refund_recipient_account(obligation_rows)
        self._refund_row_metadata = _refund_metadata(bank_rows)
        return {
            "bank_facts": _refund_bank_facts(
                bank_rows,
                selection.case_no,
                selection.refund_purpose,
                recipient_account,
            ),
            "obligations": _refund_obligations(obligation_rows),
        }

    def _load_reversal(self, cursor, selection, lock):
        targets = _load_reversal_target_rows(cursor, selection, lock)
        return {"reversal_targets": targets}

    def _load_refund_return(self, cursor, selection, lock):
        bank_rows = _load_refund_return_bank_rows(
            cursor,
            selection.bank_fact_identities,
            lock,
        )
        self._refund_row_metadata = _refund_metadata(bank_rows)
        return {
            "refund_return_bank_facts": _refund_return_bank_facts(
                bank_rows,
                selection.case_no,
            ),
            "reversal_targets": _load_reversal_target_rows(cursor, selection, lock),
        }

    def _claim_refund_row(self, cursor, candidate, entry) -> None:
        if candidate.correction_type not in {
            ClientFinanceCorrectionType.REFUND,
            ClientFinanceCorrectionType.REFUND_OVERAGE,
            ClientFinanceCorrectionType.REFUND_RETURN,
        }:
            return
        request = self._require_request()
        row_id, _ = self._refund_row_metadata[entry.finance_import_row_identity]
        reference_prefix = (
            "client-refund-return"
            if candidate.correction_type is ClientFinanceCorrectionType.REFUND_RETURN
            else _reconciliation_prefix(request.selection.refund_purpose)
        )
        cursor.execute(
            "UPDATE finance_import_rows SET reconciliation_status='reconciled',"
            "reconciliation_reference=%s,reconciled_at=CURRENT_TIMESTAMP "
            "WHERE id=%s AND reconciliation_status='pending'",
            (f"{reference_prefix}:{candidate.fingerprint.value}", row_id),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("bank_fact_not_eligible")

    def _require_request(self):
        if self._request is None:
            raise RuntimeError("Client refund reversal request is not bound")
        return self._request


@contextmanager
def _mysql_cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except (OperationalError, IntegrityError) as error:
        _raise_storage_error(error)


def _raise_storage_error(error):
    code = int(error.args[0]) if error.args else 0
    raise ClientRefundReversalStorageError(
        "Client refund reversal MySQL write failed.",
        retryable=code in _RETRYABLE_MYSQL_CODES,
    ) from error


def _load_account_version(cursor, case_no, *, lock):
    if lock:
        cursor.execute(
            "INSERT IGNORE INTO client_finance_accounts "
            "(case_no,aggregate_version) VALUES (%s,0)",
            (case_no,),
        )
    return _read_account_version(cursor, case_no, lock=lock)


def _case_exists(cursor, case_no):
    cursor.execute("SELECT 1 AS present FROM orders WHERE case_no=%s", (case_no,))
    return cursor.fetchone() is not None


def _read_account_version(cursor, case_no, *, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT aggregate_version FROM client_finance_accounts "
        f"WHERE case_no=%s{suffix}",
        (case_no,),
    )
    row = cursor.fetchone()
    return 0 if row is None else int(row["aggregate_version"])


def _load_refund_bank_rows(cursor, identities, lock):
    row_ids = tuple(_positive_row_id(item) for item in identities)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT fir.id,fir.transaction_date,fir.debit,fir.credit,fir.direction,"
        "fir.currency,COALESCE(classification.classification_type,"
        "fir.classification_type) AS effective_classification_type,"
        "fir.reconciliation_status,fir.resolved_counterparty_account,"
        "fir.bank_references,ledger.id AS ledger_entry_id "
        "FROM finance_import_rows fir LEFT JOIN client_ledger_entries ledger "
        "ON ledger.finance_import_row_id=fir.id "
        "LEFT JOIN finance_import_classification_events classification "
        "ON classification.id=("
        "SELECT MAX(latest.id) FROM finance_import_classification_events latest "
        "WHERE latest.finance_import_row_id=fir.id) "
        f"WHERE fir.id IN ({_placeholders(row_ids)}) ORDER BY fir.id{suffix}",
        row_ids,
    )
    return tuple(cursor.fetchall())


def _load_refund_return_bank_rows(cursor, identities, lock):
    row_ids = tuple(_positive_row_id(item) for item in identities)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT fir.id,fir.transaction_date,fir.debit,fir.credit,fir.direction,"
        "fir.currency,COALESCE(classification.classification_type,"
        "fir.classification_type) AS effective_classification_type,"
        "fir.reconciliation_status,fir.bank_references,ledger.id AS ledger_entry_id "
        "FROM finance_import_rows fir LEFT JOIN client_ledger_entries ledger "
        "ON ledger.finance_import_row_id=fir.id "
        "LEFT JOIN finance_import_classification_events classification "
        "ON classification.id=(SELECT MAX(latest.id) "
        "FROM finance_import_classification_events latest "
        "WHERE latest.finance_import_row_id=fir.id) "
        f"WHERE fir.id IN ({_placeholders(row_ids)}) ORDER BY fir.id{suffix}",
        row_ids,
    )
    return tuple(cursor.fetchall())


def _load_refund_obligation_rows(cursor, selection, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT obligation.obligation_identity,obligation.case_no,obligation.obligation_type,"
        "obligation.amount_due_ntd,snapshot.bank_account "
        "FROM client_obligations obligation "
        "JOIN client_refund_recipient_snapshots snapshot "
        "ON snapshot.refund_obligation_identity=obligation.obligation_identity "
        f"WHERE obligation.obligation_identity IN ({_placeholders(selection.obligation_identities)}) "
        "AND obligation.case_no=%s AND obligation.direction='payable_to_client' AND obligation.status='open' "
        "AND obligation.amount_due_ntd>0 AND obligation.obligation_type IN ('refund','subsidy_return') "
        f"ORDER BY obligation.obligation_identity{suffix}",
        (*selection.obligation_identities, selection.case_no),
    )
    return tuple(cursor.fetchall())


def _refund_metadata(rows):
    return {
        str(row["id"]): (int(row["id"]), row["transaction_date"])
        for row in rows
        if isinstance(row.get("transaction_date"), date)
    }


def _refund_bank_facts(rows, case_no, refund_purpose, recipient_account):
    expected_classification = _classification_for_purpose(refund_purpose)
    return tuple(
        ClientRefundBankFact(
            str(row["id"]),
            case_no,
            _integer_money(row.get("debit")),
            _date_text(row.get("transaction_date")),
            _refund_row_is_eligible(row, case_no, expected_classification, recipient_account),
        )
        for row in rows
        if _is_positive_integer_money(row.get("debit"))
    )


def _refund_return_bank_facts(rows, case_no):
    return tuple(
        ClientRefundReturnBankFact(
            str(row["id"]),
            case_no,
            _integer_money(row.get("credit")),
            _date_text(row.get("transaction_date")),
            _refund_return_row_is_eligible(row),
        )
        for row in rows
        if _is_positive_integer_money(row.get("credit"))
    )


def _refund_row_is_eligible(row, case_no, expected_classification, recipient_account):
    del case_no
    return (
        row.get("direction") == "outgoing"
        and _is_zero_or_none(row.get("credit"))
        and row.get("effective_classification_type") == expected_classification
        and row.get("reconciliation_status") == "pending"
        and row.get("transaction_date") is not None
        and row.get("resolved_counterparty_account") == recipient_account
        and row.get("ledger_entry_id") is None
        and _is_twd(row.get("currency"))
    )


def _refund_return_row_is_eligible(row):
    return (
        row.get("direction") == "incoming"
        and _is_zero_or_none(row.get("debit"))
        and row.get("effective_classification_type") == "client_refund_return"
        and row.get("reconciliation_status") == "pending"
        and row.get("transaction_date") is not None
        and row.get("ledger_entry_id") is None
        and _is_twd(row.get("currency"))
    )


def _refund_obligations(rows):
    return tuple(
        ClientRefundObligation(
            str(row["obligation_identity"]),
            str(row["case_no"]),
            MoneyNTD(int(row["amount_due_ntd"])),
            str(row["obligation_type"]),
        )
        for row in rows
    )


def _single_refund_recipient_account(rows):
    accounts = {str(row["bank_account"]).strip() for row in rows if row.get("bank_account")}
    if len(accounts) != 1:
        raise ValueError("client_refund_recipient_account_ambiguous")
    return accounts.pop()


def _load_reversal_target_rows(cursor, selection, lock):
    target_ids = tuple(_positive_row_id(item) for item in selection.reversal_target_identities)
    rows = _source_ledger_rows(cursor, target_ids, selection.case_no, lock)
    allocations = _source_allocations(cursor, target_ids, lock)
    reversed_amounts = _reversed_amounts(cursor, target_ids, lock)
    return tuple(
        _reversal_target(row, allocations, reversed_amounts, selection)
        for row in rows
    )


def _source_ledger_rows(cursor, target_ids, case_no, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT id,case_no,entry_type,amount_ntd,occurred_on FROM client_ledger_entries "
        f"WHERE id IN ({_placeholders(target_ids)}) AND case_no=%s "
        f"ORDER BY id{suffix}",
        (*target_ids, case_no),
    )
    return tuple(cursor.fetchall())


# Kept cohesive so target ownership and immutable allocation order share one read.
def _source_allocations(cursor, target_ids, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT allocation.ledger_entry_id,allocation.obligation_identity,"
        "allocation.amount_ntd FROM client_ledger_obligation_allocations allocation "
        "JOIN client_obligations obligation "
        "ON obligation.obligation_identity=allocation.obligation_identity "
        f"WHERE allocation.ledger_entry_id IN ({_placeholders(target_ids)}) "
        f"ORDER BY allocation.ledger_entry_id,allocation.allocation_ordinal{suffix}",
        target_ids,
    )
    grouped: dict[int, list[ClientLedgerAllocationFact]] = {}
    for row in cursor.fetchall():
        grouped.setdefault(int(row["ledger_entry_id"]), []).append(
            ClientLedgerAllocationFact(
                str(row["obligation_identity"]),
                MoneyNTD(int(row["amount_ntd"])),
            )
        )
    return grouped


def _reversed_amounts(cursor, target_ids, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT reversal_of_entry_id,SUM(amount_ntd) AS reversed_ntd "
        "FROM client_ledger_entries "
        f"WHERE reversal_of_entry_id IN ({_placeholders(target_ids)}) "
        f"GROUP BY reversal_of_entry_id{suffix}",
        target_ids,
    )
    return {
        int(row["reversal_of_entry_id"]): int(row["reversed_ntd"])
        for row in cursor.fetchall()
    }


def _reversal_target(row, allocations, reversed_amounts, selection):
    row_id = int(row["id"])
    return ClientReversalTarget(
        str(row_id),
        str(row["case_no"]),
        str(row["entry_type"]),
        MoneyNTD(int(row["amount_ntd"])),
        MoneyNTD(reversed_amounts.get(row_id, 0)),
        selection.reversal_occurred_on or _date_text(row["occurred_on"]),
        tuple(allocations.get(row_id, ())),
    )


# Kept cohesive so source identity, reversal lineage, and audit fields cannot drift.
def _insert_ledger_entry(cursor, request, candidate, entry, ordinal):
    bank_row_id = (
        None
        if entry.finance_import_row_identity is None
        else _positive_row_id(entry.finance_import_row_identity)
    )
    reversal_id = (
        None
        if entry.reversal_of_entry_identity is None
        else _positive_row_id(entry.reversal_of_entry_identity)
    )
    cursor.execute(
        _LEDGER_INSERT_SQL,
        (
            candidate.case_no,
            bank_row_id,
            entry.entry_type,
            entry.amount.amount,
            entry.occurred_on,
            candidate.fingerprint.value,
            reversal_id,
            _child_key(request, "ledger", ordinal),
            request.actor.actor_id,
            request.reason,
        ),
    )
    entry_id = int(cursor.lastrowid or 0)
    if entry_id <= 0:
        raise RuntimeError("Client correction ledger identity was not generated")
    return entry_id


def _insert_allocation(cursor, entry_ids, allocation, ordinal):
    entry_id = entry_ids.get(allocation.entry_identity)
    if entry_id is None:
        raise RuntimeError("Client correction allocation target is missing")
    cursor.execute(
        _ALLOCATION_INSERT_SQL,
        (
            entry_id,
            allocation.obligation_identity,
            allocation.amount.amount,
            ordinal,
        ),
    )


def _persisted_allocation_totals(cursor, candidate):
    identities = tuple(sorted(candidate.affected_obligations))
    cursor.execute(
        "SELECT allocation.obligation_identity,SUM(allocation.amount_ntd) total_ntd "
        "FROM client_ledger_obligation_allocations allocation "
        "JOIN client_ledger_entries ledger ON ledger.id=allocation.ledger_entry_id "
        f"WHERE allocation.obligation_identity IN ({_placeholders(identities)}) "
        "AND ledger.reconciliation_reference=%s "
        "GROUP BY allocation.obligation_identity",
        (*identities, candidate.fingerprint.value),
    )
    return {
        str(row["obligation_identity"]): int(row["total_ntd"])
        for row in cursor.fetchall()
    }


def _settle_refund_obligations(cursor, candidate, totals, version):
    for identity in candidate.affected_obligations:
        amount = totals.get(identity, 0)
        cursor.execute(
            "UPDATE client_obligations SET "
            "status=CASE WHEN amount_due_ntd-%s=0 THEN 'settled' ELSE 'open' END,"
            "amount_due_ntd=amount_due_ntd-%s,"
            "projection_version=%s WHERE obligation_identity=%s AND case_no=%s "
            "AND direction='payable_to_client' AND status='open' "
            "AND amount_due_ntd>=%s",
            (amount, amount, version, identity, candidate.case_no, amount),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("allocation_exceeds_obligation")


def _persist_underpayment_source(cursor, request, candidate, resulting_version, row_metadata):
    if not request.selection.allow_partial_refund_recovery:
        return
    remaining = _refund_remaining_total(cursor, candidate)
    if remaining <= 0:
        return
    identity = f"client-refund-underpayment:{candidate.fingerprint.value}"
    bank_total = sum(entry.amount.amount for entry in candidate.entries)
    cursor.execute(_UNDERPAYMENT_SOURCE_INSERT_SQL, (identity, candidate.case_no, bank_total, remaining, resulting_version, _child_key(request, "refund-underpayment", 1), request.actor.actor_id, request.reason))
    for ordinal, entry in enumerate(candidate.entries, start=1):
        row_id, _ = row_metadata[entry.finance_import_row_identity]
        cursor.execute(_UNDERPAYMENT_SOURCE_ROW_INSERT_SQL, (identity, row_id, ordinal))
    for obligation_identity, amount in _refund_remaining_amounts(cursor, candidate).items():
        cursor.execute(_UNDERPAYMENT_SOURCE_OBLIGATION_INSERT_SQL, (identity, obligation_identity, amount))


def _refund_remaining_amounts(cursor, candidate):
    identities = tuple(candidate.affected_obligations)
    cursor.execute(
        f"SELECT obligation_identity,amount_due_ntd FROM client_obligations WHERE obligation_identity IN ({_placeholders(identities)})",
        identities,
    )
    return {str(row["obligation_identity"]): int(row["amount_due_ntd"]) for row in cursor.fetchall() if int(row["amount_due_ntd"]) > 0}


def _refund_remaining_total(cursor, candidate):
    return sum(_refund_remaining_amounts(cursor, candidate).values())


def _reopen_receivable_obligations(cursor, candidate, totals, version):
    for identity in candidate.affected_obligations:
        amount = totals.get(identity, 0)
        cursor.execute(
            "UPDATE client_obligations SET amount_due_ntd=%s,status='open',"
            "projection_version=%s WHERE obligation_identity=%s AND case_no=%s "
            "AND direction='receivable_from_client' AND status='settled' "
            "AND amount_due_ntd=0",
            (amount, version, identity, candidate.case_no),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("reversal_target_invalid")


def _reopen_payable_obligations(cursor, candidate, totals, version):
    for identity in candidate.affected_obligations:
        amount = totals.get(identity, 0)
        cursor.execute(
            "UPDATE client_obligations SET amount_due_ntd=amount_due_ntd+%s,"
            "status='open',projection_version=%s WHERE obligation_identity=%s "
            "AND case_no=%s AND direction='payable_to_client' "
            "AND status IN ('open','settled')",
            (amount, version, identity, candidate.case_no),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("reversal_target_invalid")


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


def _query_payable_obligations(cursor, case_no, refund_purpose):
    obligation_types = _obligation_types_for_purpose(refund_purpose)
    cursor.execute(
        "SELECT obligation_identity,obligation_type,amount_due_ntd,due_date "
        "FROM client_obligations WHERE case_no=%s "
        "AND direction='payable_to_client' AND status='open' "
        f"AND obligation_type IN ({_placeholders(obligation_types)}) "
        "ORDER BY due_date,obligation_identity",
        (case_no, *obligation_types),
    )
    return tuple(dict(row) for row in cursor.fetchall())


def _classification_for_purpose(refund_purpose):
    if refund_purpose in {
        ClientRefundPurpose.SUBSIDY_RETURN,
        ClientRefundPurpose.SUBSIDY_ADVANCE,
    }:
        return "client_subsidy_return"
    return "client_refund"


def _obligation_types_for_purpose(refund_purpose):
    if refund_purpose in {
        ClientRefundPurpose.SUBSIDY_RETURN,
        ClientRefundPurpose.SUBSIDY_ADVANCE,
    }:
        return ("subsidy_return",)
    return ("adjustment", "refund")


def _reconciliation_prefix(refund_purpose):
    if refund_purpose is ClientRefundPurpose.SUBSIDY_ADVANCE:
        return "client-subsidy-advance"
    if refund_purpose is ClientRefundPurpose.SUBSIDY_RETURN:
        return "client-subsidy-return"
    return "client-refund"


def _query_reversal_targets(cursor, case_no, entry_type):
    cursor.execute(
        "SELECT ledger.id,ledger.amount_ntd,ledger.occurred_on,"
        "COALESCE(SUM(reversal.amount_ntd),0) AS reversed_ntd "
        "FROM client_ledger_entries ledger "
        "LEFT JOIN client_ledger_entries reversal "
        "ON reversal.reversal_of_entry_id=ledger.id "
        "WHERE ledger.case_no=%s AND ledger.entry_type=%s "
        "GROUP BY ledger.id,ledger.amount_ntd,ledger.occurred_on "
        "HAVING reversed_ntd=0 ORDER BY ledger.occurred_on,ledger.id",
        (case_no, entry_type),
    )
    return tuple(dict(row) for row in cursor.fetchall())


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "correction_type": receipt.correction_type.value,
        "account_version": receipt.account_version,
        "correction_identity": receipt.correction_identity.value,
        "ledger_entry_count": receipt.ledger_entry_count,
        "allocation_count": receipt.allocation_count,
        "affected_obligations": receipt.affected_obligations,
    }


def _over_refund_recovery_identity(correction_identity: str) -> str:
    return f"client-over-refund-recovery:{correction_identity[:48]}"


def _stored_receipt(row):
    payload = _json_object(row["result_snapshot"])
    receipt = ClientRefundReversalReceipt(
        str(payload["case_no"]),
        ClientFinanceCorrectionType(str(payload["correction_type"])),
        int(payload["account_version"]),
        PreviewFingerprint(str(payload["correction_identity"])),
        int(payload["ledger_entry_count"]),
        int(payload["allocation_count"]),
        tuple(str(item) for item in payload["affected_obligations"]),
    )
    return StoredClientRefundReversalReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _child_key(request, purpose, ordinal):
    value = f"{request.idempotency_key.value}:{purpose}:{ordinal}"
    return f"client-correction:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _integer_money(value):
    amount = Decimal(str(value))
    if amount <= 0 or amount != amount.to_integral_value():
        raise ValueError("bank_fact_not_eligible")
    return MoneyNTD(int(amount))


def _is_positive_integer_money(value):
    try:
        _integer_money(value)
        return True
    except (InvalidOperation, ValueError, TypeError):
        return False


def _is_zero_or_none(value):
    try:
        return value is None or Decimal(str(value)) == 0
    except (InvalidOperation, ValueError, TypeError):
        return False


def _is_twd(value):
    return value is None or str(value).upper() in {"TWD", "NTD"}


def _json_object(value) -> Mapping[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, Mapping) else {}


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _positive_row_id(value):
    try:
        row_id = int(value)
    except (TypeError, ValueError):
        return -1
    return row_id if row_id > 0 else -1


def _date_text(value):
    return value.isoformat() if isinstance(value, date) else "0001-01-01"


def _placeholders(values):
    return ",".join("%s" for _ in values) if values else "NULL"


_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,result_snapshot "
    "FROM client_refund_reversal_apply_receipts "
    "WHERE idempotency_key=%s FOR UPDATE"
)
_LEDGER_INSERT_SQL = (
    "INSERT INTO client_ledger_entries "
    "(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
    "reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_OVER_REFUND_RECOVERY_INSERT_SQL = (
    "INSERT INTO client_over_refund_recoveries "
    "(recovery_identity,case_no,finance_import_row_id,refund_ledger_entry_id,"
    "refund_obligation_identity,amount_due_ntd,status,idempotency_key,actor,reason,projection_version) "
    "VALUES (%s,%s,%s,%s,%s,%s,'open',%s,%s,%s,%s)"
)
_OVER_REFUND_RECOVERY_EVENT_INSERT_SQL = (
    "INSERT INTO client_over_refund_recovery_events "
    "(recovery_identity,event_type,finance_import_row_id,receipt_ledger_entry_id,"
    "before_amount_ntd,after_amount_ntd,idempotency_key,actor,reason) "
    "VALUES (%s,'established',NULL,NULL,0,%s,%s,%s,%s)"
)
_ALLOCATION_INSERT_SQL = (
    "INSERT INTO client_ledger_obligation_allocations "
    "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) "
    "VALUES (%s,%s,%s,%s)"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO client_finance_outbox "
    "(case_no,intent_type,intent_key,payload_snapshot) "
    "VALUES (%s,'projection_refresh',%s,%s)"
)
_UNDERPAYMENT_SOURCE_INSERT_SQL = "INSERT INTO client_refund_underpayment_sources (underpayment_identity,case_no,bank_total_ntd,remaining_after_ntd,resulting_account_version,idempotency_key,actor,reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
_UNDERPAYMENT_SOURCE_ROW_INSERT_SQL = "INSERT INTO client_refund_underpayment_source_bank_rows (underpayment_identity,finance_import_row_id,ordinal) VALUES (%s,%s,%s)"
_UNDERPAYMENT_SOURCE_OBLIGATION_INSERT_SQL = "INSERT INTO client_refund_underpayment_source_obligations (underpayment_identity,refund_obligation_identity,remaining_after_ntd) VALUES (%s,%s,%s)"
_UNDERPAYMENT_OUTBOX_INSERT_SQL = "INSERT INTO client_finance_outbox (case_no,intent_type,intent_key,payload_snapshot) VALUES (%s,'client_refund_underpayment_required',%s,%s)"
_RECEIPT_INSERT_SQL = (
    "INSERT INTO client_refund_reversal_apply_receipts "
    "(idempotency_key,correction_type,command_fingerprint,preview_fingerprint,"
    "case_no,resulting_account_version,result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s)"
)

__all__ = [
    "ClientRefundReversalMySqlUnitOfWork",
    "MySqlClientRefundReversalRepository",
]
