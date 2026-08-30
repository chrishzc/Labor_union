"""
File: staff_payout_repository.py
Description: 讀取 MySQL Staff Payables 根事實並原子保存 payout、recovery、receipt 與 outbox。
"""

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

from domains.staff_payables.reconciliation import (
    BankTransactionDirection,
    OutgoingBankFact,
    StaffPayableFacts,
    StaffPayableStatus,
    StaffPayoutCandidate,
    StaffPayoutDifferenceMode,
    StaffPayoutEvent,
    StaffPayoutEventType,
    StaffPayoutReopenFact,
    StaffPrimaryBankAccount,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutApplyRequest,
    StaffPayoutReceipt,
    StaffPayoutReconciliationFacts,
    StaffPayoutRepositoryUnavailable,
    StaffPayoutSelection,
    StoredStaffPayoutReceipt,
)

_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213})
_PAYOUT_CLASSIFICATIONS = frozenset(
    {"staff_payout", "staff_salary", "staff_legacy_subsidy"}
)
_RETURN_CLASSIFICATIONS = frozenset({"staff_payout_return", "staff_salary_return"})
_RETURN_IDENTITY = re.compile(r"^return:row:(\d+):source:(\d+)$")
_REVERSAL_IDENTITY = re.compile(
    r"^reversal:source:(\d+):on:(\d{4}-\d{2}-\d{2})$"
)
_JAVASCRIPT_SAFE_VERSION_HEX_DIGITS = 13


@dataclass(frozen=True, slots=True)
class _EventPersistenceMetadata:
    occurred_on: date
    bank_account_identity_hash: str
    finance_import_row_id: int | None
    reversal_of_event_id: int | None


@dataclass(frozen=True, slots=True)
class _ReopenReference:
    event_type: StaffPayoutEventType
    source_event_id: int
    finance_import_row_id: int | None
    occurred_on: date | None


class StaffPayoutMySqlUnitOfWork(MySqlUnitOfWork):
    def __enter__(self):
        try:
            return super().__enter__()
        except OperationalError as error:
            _raise_if_transient(error)
            raise

    def commit(self) -> None:
        try:
            super().commit()
        except OperationalError as error:
            _raise_if_transient(error)
            raise


class MySqlStaffPayoutRepository:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._request: StaffPayoutApplyRequest | None = None
        self._event_metadata: dict[str, _EventPersistenceMetadata] = {}
        self._event_ids: dict[str, int] = {}

    def bind_apply_request(self, request: StaffPayoutApplyRequest) -> None:
        self._request = request

    def clear_apply_request(self) -> None:
        self._request = None
        self._event_metadata.clear()
        self._event_ids.clear()

    def load(self, selection, *, for_update):
        with _mysql_cursor(self._connection) as cursor:
            return self._load_facts(cursor, selection, for_update)

    def find_receipt(self, key):
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (key.value,))
            row = cursor.fetchone()
        return None if row is None else _stored_receipt(row)

    def append_events(self, candidate) -> None:
        request = self._require_request()
        with _mysql_cursor(self._connection) as cursor:
            for ordinal, event in enumerate(_candidate_events(candidate), start=1):
                metadata = self._metadata_for_event(event)
                event_id = _insert_event(cursor, request, event, metadata, ordinal)
                self._event_ids[event.identity] = event_id

    def append_obligation_links(self, candidate) -> None:
        with _mysql_cursor(self._connection) as cursor:
            ordinals: dict[str, int] = {}
            for link in candidate.obligation_links:
                ordinal = ordinals.get(link.event_identity, 0) + 1
                ordinals[link.event_identity] = ordinal
                _insert_link(cursor, self._event_ids, link, ordinal)

    def append_overpayment_recovery(self, candidate) -> None:
        if not isinstance(candidate, StaffPayoutCandidate) or candidate.recovery is None:
            return
        recovery = candidate.recovery
        source_bank_fact_identities = _canonical_recovery_source_bank_fact_identities(
            recovery.source_bank_fact_identities
        )
        source_event_ids = tuple(
            self._event_ids[event.identity]
            for event in candidate.events
        )
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _RECOVERY_INSERT_SQL,
                (
                    recovery.identity,
                    recovery.staff_id,
                    recovery.original_amount.amount,
                    recovery.original_amount.amount,
                    _canonical_json(source_bank_fact_identities),
                    _canonical_json(source_event_ids),
                    _canonical_json(recovery.source_obligation_identities),
                    self._require_request().actor.actor_id,
                    self._require_request().reason,
                ),
            )

    def update_payable_projection(
        self,
        selection,
        resulting_version,
        resulting_status,
    ) -> None:
        request = self._require_request()
        with _mysql_cursor(self._connection) as cursor:
            rows = _projection_rows(cursor, selection.obligation_identities)
            _validate_projection_rows(rows, resulting_status, request.selection.difference_mode)
            for row in rows:
                _upsert_projection(cursor, row, resulting_version)
            _advance_account_version(cursor, request, resulting_version)

    def append_outbox(self, candidate) -> None:
        request = self._require_request()
        difference_identity = self._persist_difference_source(candidate, request)
        if difference_identity is not None:
            return
        payload = _outbox_payload(candidate, request, difference_identity)
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _OUTBOX_INSERT_SQL,
                (
                    candidate.staff_id,
                    _outbox_intent_key(request.idempotency_key),
                    "payable_projection_refresh",
                    _canonical_json(payload),
                ),
            )

    def _persist_difference_source(self, candidate, request) -> str | None:
        if request.selection.difference_mode is None:
            return None
        if not isinstance(candidate, StaffPayoutCandidate):
            raise RuntimeError("staff_payout_difference_candidate_missing")
        identity = _payout_difference_identity(request.idempotency_key)
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO staff_payout_difference_sources (payout_difference_identity,staff_id,difference_mode,bank_total_ntd,obligation_total_ntd,recovery_identity,resulting_staff_payables_version,source_bank_facts_version,idempotency_key,actor,reason,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (identity, candidate.staff_id, request.selection.difference_mode.value,
                 candidate.bank_total.amount, candidate.obligation_total.amount,
                 None if candidate.recovery is None else candidate.recovery.identity,
                 request.expected_staff_payables_version.value + 1,
                 request.expected_bank_facts_version.value, request.idempotency_key.value,
                 request.actor.actor_id, request.reason, request.correlation_id.value),
            )
            for ordinal, identity_value in enumerate(request.selection.bank_fact_identities, start=1):
                cursor.execute("INSERT INTO staff_payout_difference_source_bank_rows (payout_difference_identity,finance_import_row_id,ordinal) VALUES (%s,%s,%s)", (identity, int(identity_value), ordinal))
            for ordinal, obligation_identity in enumerate(request.selection.obligation_identities, start=1):
                cursor.execute("INSERT INTO staff_payout_difference_source_obligations (payout_difference_identity,obligation_identity,ordinal) VALUES (%s,%s,%s)", (identity, obligation_identity, ordinal))
        return identity

    def save_receipt(self, key, stored_receipt) -> None:
        receipt = stored_receipt.receipt
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (
                    key.value,
                    stored_receipt.command_fingerprint.value,
                    receipt.preview_fingerprint.value,
                    receipt.staff_id,
                    _canonical_json(_receipt_payload(receipt)),
                ),
            )

    def query_staff_payables(self, staff_id: int) -> dict[str, object]:
        with _mysql_cursor(self._connection) as cursor:
            account_version = _read_account_version(cursor, staff_id, lock=False)
            obligations = _query_obligation_rows(cursor, staff_id)
            events = _query_event_rows(cursor, staff_id)
        return {
            "staff_id": staff_id,
            "staff_payables_version": account_version,
            "obligations": obligations,
            "events": events,
        }

    def query_payout_difference_source(self, identity: str) -> dict[str, object]:
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute("SELECT payout_difference_identity,staff_id,difference_mode,bank_total_ntd,obligation_total_ntd,recovery_identity,resulting_staff_payables_version,source_bank_facts_version FROM staff_payout_difference_sources WHERE payout_difference_identity=%s", (identity,))
            source = cursor.fetchone()
            if source is None:
                raise ValueError("staff_payout_difference_source_not_found")
            cursor.execute("SELECT finance_import_row_id FROM staff_payout_difference_source_bank_rows WHERE payout_difference_identity=%s ORDER BY ordinal", (identity,))
            bank_rows = [int(row["finance_import_row_id"]) for row in cursor.fetchall()]
            cursor.execute("SELECT obligation_identity FROM staff_payout_difference_source_obligations WHERE payout_difference_identity=%s ORDER BY ordinal", (identity,))
            obligations = [str(row["obligation_identity"]) for row in cursor.fetchall()]
        return {**source, "finance_import_row_ids": bank_rows, "obligation_identities": obligations}

    # Kept cohesive so every Apply follows one visible, stable MySQL lock order.
    def _load_facts(self, cursor, selection, for_update):
        obligation_rows = _load_obligation_rows(
            cursor,
            selection.obligation_identities,
            lock=False,
        )
        staff_id = _intended_staff_id(obligation_rows)
        account_version = (
            _load_account_version(cursor, staff_id, lock=for_update)
            if obligation_rows
            else 0
        )
        bank_rows = _load_selected_bank_rows(cursor, selection, for_update)
        if for_update:
            obligation_rows = _load_obligation_rows(
                cursor,
                selection.obligation_identities,
                lock=True,
            )
        return self._assemble_facts(
            cursor,
            selection,
            staff_id,
            account_version,
            bank_rows,
            obligation_rows,
            for_update,
        )

    # Kept cohesive so versions and typed facts come from the same locked snapshot.
    def _assemble_facts(
        self,
        cursor,
        selection,
        staff_id,
        account_version,
        bank_rows,
        obligation_rows,
        lock,
    ):
        bank_accounts = _load_bank_accounts(cursor, bank_rows, lock)
        events = _load_obligation_events(
            cursor,
            selection.obligation_identities,
            lock,
        )
        obligations = _obligation_facts(obligation_rows, events)
        blockers = _load_blocking_anomalies(cursor, bank_rows)
        bank_facts = (
            self._outgoing_bank_facts(bank_rows, staff_id, blockers)
            if selection.event_type is StaffPayoutEventType.PAYOUT
            else ()
        )
        reopen_fact = self._reopen_fact(
            cursor,
            selection,
            bank_rows,
            obligations,
            bank_accounts,
            _global_blockers(blockers),
            lock,
        )
        return StaffPayoutReconciliationFacts(
            account_version,
            _bank_facts_version(bank_rows, reopen_fact),
            bank_facts,
            bank_accounts,
            obligations,
            reopen_fact,
            _global_blockers(blockers),
        )

    def _outgoing_bank_facts(self, bank_rows, staff_id, blockers):
        facts = tuple(
            _outgoing_bank_fact(row, staff_id, blockers.get(int(row["id"]), ()))
            for row in bank_rows
        )
        for fact, row in zip(facts, bank_rows, strict=True):
            self._event_metadata[fact.identity] = _bank_event_metadata(row)
        return facts

    # Kept cohesive so source validation and persisted event metadata cannot drift.
    def _reopen_fact(
        self,
        cursor,
        selection,
        bank_rows,
        obligations,
        bank_accounts,
        blockers,
        lock,
    ):
        if selection.event_type is StaffPayoutEventType.PAYOUT:
            return None
        reference = _parse_reopen_reference(selection)
        source, links = _load_source_payout(cursor, reference, lock)
        reopen = _build_reopen_fact(
            selection,
            reference,
            source,
            links,
            bank_rows,
            obligations,
            bank_accounts,
            blockers,
        )
        self._event_metadata[reopen.identity] = _reopen_event_metadata(
            reference,
            source,
            bank_rows,
        )
        return reopen

    def _metadata_for_event(self, event):
        identity = event.finance_import_fact_identity or event.identity
        metadata = self._event_metadata.get(identity)
        if metadata is None:
            raise RuntimeError("staff payout event metadata is missing")
        return metadata

    def _require_request(self) -> StaffPayoutApplyRequest:
        if self._request is None:
            raise RuntimeError("staff payout Apply request is not bound")
        return self._request


def build_return_reopen_identity(
    finance_import_row_id: int,
    source_payout_event_id: int,
) -> str:
    return f"return:row:{finance_import_row_id}:source:{source_payout_event_id}"


def build_reversal_reopen_identity(
    source_payout_event_id: int,
    occurred_on: date,
) -> str:
    return f"reversal:source:{source_payout_event_id}:on:{occurred_on.isoformat()}"


@contextmanager
def _mysql_cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except OperationalError as error:
        _raise_if_transient(error)
        raise
    except IntegrityError as error:
        if int(error.args[0]) == 1062:
            raise StaffPayoutRepositoryUnavailable(
                "concurrent staff payout write requires exact retry"
            ) from error
        raise


def _raise_if_transient(error: OperationalError) -> None:
    mysql_code = int(error.args[0]) if error.args else 0
    if mysql_code in _RETRYABLE_MYSQL_CODES:
        raise StaffPayoutRepositoryUnavailable(
            "staff payout MySQL transaction is temporarily unavailable"
        ) from error


def _load_account_version(cursor, staff_id, *, lock):
    if not lock:
        return _read_account_version(cursor, staff_id, lock=False)
    cursor.execute(
        "INSERT IGNORE INTO staff_payable_accounts "
        "(staff_id,aggregate_version) VALUES (%s,0)",
        (staff_id,),
    )
    return _read_account_version(cursor, staff_id, lock=True)


def _read_account_version(cursor, staff_id, *, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT aggregate_version FROM staff_payable_accounts "
        f"WHERE staff_id=%s{suffix}",
        (staff_id,),
    )
    row = cursor.fetchone()
    return 0 if row is None else int(row["aggregate_version"])


def _load_obligation_rows(cursor, identities, *, lock):
    placeholders = _placeholders(identities)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT obligation_identity,staff_id,amount_due_ntd "
        "FROM staff_obligations "
        f"WHERE obligation_identity IN ({placeholders}) "
        "AND direction='payable_to_staff' AND status='open' "
        f"ORDER BY staff_id,obligation_identity{suffix}",
        identities,
    )
    return tuple(cursor.fetchall())


def _intended_staff_id(obligation_rows) -> int:
    if not obligation_rows:
        return 1
    return int(obligation_rows[0]["staff_id"])


# Kept as one query so authoritative classification and payout claim cannot drift.
def _load_selected_bank_rows(cursor, selection, lock):
    row_ids = _selected_finance_row_ids(selection)
    if not row_ids:
        return ()
    placeholders = _placeholders(row_ids)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT fir.id,fir.dedup_fingerprint,fir.transaction_date,"
        "fir.debit,fir.credit,fir.direction,fir.currency,"
        "fir.resolved_counterparty_account,fir.classification_type,"
        "classification.classification_type AS authoritative_classification_type,"
        "fir.reconciliation_status,fir.warnings,spe.id AS payout_event_id "
        "FROM finance_import_rows fir "
        "LEFT JOIN finance_import_classification_events classification "
        "ON classification.id=("
        "SELECT MAX(latest.id) FROM finance_import_classification_events latest "
        "WHERE latest.finance_import_row_id=fir.id) "
        "LEFT JOIN staff_payout_events spe ON spe.finance_import_row_id=fir.id "
        f"WHERE fir.id IN ({placeholders}) ORDER BY fir.id{suffix}",
        row_ids,
    )
    return tuple(cursor.fetchall())


def _selected_finance_row_ids(selection) -> tuple[int, ...]:
    if selection.event_type is StaffPayoutEventType.PAYOUT:
        return tuple(_positive_row_id(value) for value in selection.bank_fact_identities)
    reference = _parse_reopen_reference(selection)
    if reference.finance_import_row_id is None:
        return ()
    return (reference.finance_import_row_id,)


def _positive_row_id(value: str) -> int:
    try:
        row_id = int(value)
    except ValueError:
        return -1
    return row_id if row_id > 0 else -1


def _canonical_recovery_source_bank_fact_identities(
    identities: tuple[str, ...],
) -> tuple[str, ...]:
    """Translate legacy payout row ids to the persisted Finance Import identity."""
    canonical: list[str] = []
    for identity in identities:
        if not isinstance(identity, str):
            raise ValueError("staff_overpayment_recovery_source_bank_fact_invalid")
        raw_id = identity.removeprefix("finance-import-row:")
        if not re.fullmatch(r"[0-9]+", raw_id):
            raise ValueError("staff_overpayment_recovery_source_bank_fact_invalid")
        row_id = int(raw_id)
        if row_id <= 0:
            raise ValueError("staff_overpayment_recovery_source_bank_fact_invalid")
        canonical.append(f"finance-import-row:{row_id}")
    if not canonical or len(canonical) != len(set(canonical)):
        raise ValueError("staff_overpayment_recovery_source_bank_fact_invalid")
    return tuple(canonical)


# Kept cohesive because the ordered SQL result is the bank-ownership fact boundary.
def _load_bank_accounts(cursor, bank_rows, lock):
    identities = tuple(
        sorted(
            {
                str(row["resolved_counterparty_account"])
                for row in bank_rows
                if row.get("resolved_counterparty_account")
            }
        )
    )
    if not identities:
        return ()
    placeholders = _placeholders(identities)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT account_no,staff_id,is_primary FROM staff_bank_accounts "
        f"WHERE account_no IN ({placeholders}) "
        f"ORDER BY account_no,staff_id,id{suffix}",
        identities,
    )
    return tuple(
        StaffPrimaryBankAccount(
            str(row["account_no"]),
            int(row["staff_id"]),
            primary=bool(row["is_primary"]),
        )
        for row in cursor.fetchall()
    )


def _load_obligation_events(cursor, identities, lock):
    placeholders = _placeholders(identities)
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT links.obligation_identity,events.id,events.event_type,"
        "links.allocated_amount_ntd,events.reversal_of_event_id "
        "FROM staff_payout_obligation_links links "
        "JOIN staff_payout_events events ON events.id=links.payout_event_id "
        f"WHERE links.obligation_identity IN ({placeholders}) "
        f"ORDER BY links.obligation_identity,events.id{suffix}",
        identities,
    )
    grouped: dict[str, list[StaffPayoutEvent]] = {}
    for row in cursor.fetchall():
        grouped.setdefault(str(row["obligation_identity"]), []).append(
            _existing_event(row)
        )
    return grouped


def _existing_event(row) -> StaffPayoutEvent:
    source = row.get("reversal_of_event_id")
    return StaffPayoutEvent(
        str(row["id"]),
        StaffPayoutEventType(str(row["event_type"])),
        MoneyNTD(int(row["allocated_amount_ntd"])),
        None if source is None else str(source),
    )


def _obligation_facts(obligation_rows, events):
    return tuple(
        StaffPayableFacts(
            str(row["obligation_identity"]),
            int(row["staff_id"]),
            MoneyNTD(int(row["amount_due_ntd"])),
            tuple(events.get(str(row["obligation_identity"]), ())),
        )
        for row in obligation_rows
    )


# Kept cohesive because alert joins and blocker canonicalization form one fact loader.
def _load_blocking_anomalies(cursor, bank_rows):
    row_ids = tuple(int(row["id"]) for row in bank_rows)
    if not row_ids:
        return {}
    placeholders = _placeholders(row_ids)
    cursor.execute(
        "SELECT occurrence.finance_import_row_id,current_alert.definition_code "
        "FROM finance_anomaly_occurrences occurrence "
        "JOIN anomaly_current_alerts current_alert "
        "ON current_alert.definition_code=occurrence.definition_code "
        "AND current_alert.source_identity=occurrence.source_event_identity "
        f"WHERE occurrence.finance_import_row_id IN ({placeholders}) "
        "AND current_alert.predicate_active=1 "
        "AND current_alert.workflow_status<>'resolved' "
        "ORDER BY occurrence.finance_import_row_id,current_alert.definition_code",
        row_ids,
    )
    blockers: dict[int, list[str]] = {}
    for row in cursor.fetchall():
        blockers.setdefault(int(row["finance_import_row_id"]), []).append(
            str(row["definition_code"])
        )
    return {key: tuple(sorted(set(values))) for key, values in blockers.items()}


def _global_blockers(blockers) -> tuple[str, ...]:
    return tuple(sorted({code for values in blockers.values() for code in values}))


def _outgoing_bank_fact(row, staff_id, anomaly_codes):
    amount, amount_valid = _integer_money(row.get("debit"))
    eligible = _payout_row_is_eligible(row, amount_valid)
    direction = _bank_direction(row.get("direction"))
    return OutgoingBankFact(
        str(row["id"]),
        staff_id,
        amount,
        _optional_text(row.get("resolved_counterparty_account")),
        direction,
        str(row["dedup_fingerprint"]),
        eligible,
        anomaly_codes,
    )


def _payout_row_is_eligible(row, amount_valid) -> bool:
    return (
        amount_valid
        and row.get("direction") == "outgoing"
        and _is_zero_or_none(row.get("credit"))
        and _classification_type(row) in _PAYOUT_CLASSIFICATIONS
        and row.get("reconciliation_status") == "pending"
        and row.get("transaction_date") is not None
        and row.get("payout_event_id") is None
        and _is_twd(row.get("currency"))
    )


def _bank_direction(value) -> BankTransactionDirection:
    if value == "outgoing":
        return BankTransactionDirection.OUTGOING
    return BankTransactionDirection.INCOMING


def _classification_type(row):
    return (
        row.get("authoritative_classification_type")
        or row.get("classification_type")
    )


def _integer_money(value) -> tuple[MoneyNTD, bool]:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return MoneyNTD(1), False
    integral = amount == amount.to_integral_value()
    if not integral or amount <= 0:
        return MoneyNTD(1), False
    return MoneyNTD(int(amount)), True


def _is_zero_or_none(value) -> bool:
    if value is None:
        return True
    try:
        return Decimal(str(value)) == 0
    except (InvalidOperation, ValueError):
        return False


def _is_twd(value) -> bool:
    return value is None or str(value).upper() in {"TWD", "NTD"}


def _parse_reopen_reference(selection) -> _ReopenReference:
    identity = selection.reopen_fact_identity or ""
    if selection.event_type is StaffPayoutEventType.RETURN:
        return _parse_return_reference(identity)
    return _parse_reversal_reference(identity)


def _parse_return_reference(identity) -> _ReopenReference:
    match = _RETURN_IDENTITY.fullmatch(identity)
    if match is None:
        return _ReopenReference(StaffPayoutEventType.RETURN, -1, -1, None)
    return _ReopenReference(
        StaffPayoutEventType.RETURN,
        int(match.group(2)),
        int(match.group(1)),
        None,
    )


def _parse_reversal_reference(identity) -> _ReopenReference:
    match = _REVERSAL_IDENTITY.fullmatch(identity)
    if match is None:
        return _ReopenReference(StaffPayoutEventType.REVERSAL, -1, None, None)
    try:
        occurred_on = date.fromisoformat(match.group(2))
    except ValueError:
        occurred_on = None
    return _ReopenReference(
        StaffPayoutEventType.REVERSAL,
        int(match.group(1)),
        None,
        occurred_on,
    )


def _load_source_payout(cursor, reference, lock):
    suffix = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT id,staff_id,event_type,amount_ntd,occurred_on,"
        "bank_account_identity_hash,reversal_of_event_id "
        f"FROM staff_payout_events WHERE id=%s{suffix}",
        (reference.source_event_id,),
    )
    source = cursor.fetchone()
    cursor.execute(
        "SELECT obligation_identity,allocated_amount_ntd "
        "FROM staff_payout_obligation_links WHERE payout_event_id=%s "
        f"ORDER BY obligation_identity{suffix}",
        (reference.source_event_id,),
    )
    return source, tuple(cursor.fetchall())


# Kept cohesive so all return and reversal validity contributes to one success flag.
def _build_reopen_fact(
    selection,
    reference,
    source,
    links,
    bank_rows,
    obligations,
    bank_accounts,
    blockers,
):
    staff_id = _source_staff_id(source, obligations)
    source_amount = _source_link_total(links, obligations)
    amount, bank_valid = _reopen_amount(reference, bank_rows, source_amount)
    source_valid = _source_payout_is_valid(source, links, selection)
    account_valid = _return_account_is_valid(
        reference,
        bank_rows,
        bank_accounts,
        staff_id,
    )
    return StaffPayoutReopenFact(
        selection.reopen_fact_identity or "invalid-reopen-reference",
        selection.event_type,
        staff_id,
        amount,
        str(reference.source_event_id),
        succeeded=source_valid and bank_valid and account_valid and not blockers,
        blocking_anomalies=blockers,
    )


def _source_staff_id(source, obligations) -> int:
    if source is not None:
        return int(source["staff_id"])
    if obligations:
        return obligations[0].staff_id
    return 1


def _source_link_total(links, obligations) -> MoneyNTD:
    if links:
        return MoneyNTD(sum(int(row["allocated_amount_ntd"]) for row in links))
    if obligations:
        return MoneyNTD(sum(item.amount_due.amount for item in obligations))
    return MoneyNTD(1)


def _reopen_amount(reference, bank_rows, source_amount):
    if reference.event_type is StaffPayoutEventType.REVERSAL:
        return source_amount, reference.occurred_on is not None
    if len(bank_rows) != 1:
        return MoneyNTD(1), False
    amount, amount_valid = _integer_money(bank_rows[0].get("credit"))
    return amount, amount_valid and _return_row_is_eligible(bank_rows[0])


def _return_row_is_eligible(row) -> bool:
    return (
        row.get("direction") == "incoming"
        and _is_zero_or_none(row.get("debit"))
        and row.get("classification_type") in _RETURN_CLASSIFICATIONS
        and row.get("reconciliation_status") == "pending"
        and row.get("transaction_date") is not None
        and row.get("payout_event_id") is None
        and _is_twd(row.get("currency"))
    )


def _source_payout_is_valid(source, links, selection) -> bool:
    if source is None or source.get("event_type") != "payout":
        return False
    if source.get("reversal_of_event_id") is not None:
        return False
    linked = tuple(sorted(str(row["obligation_identity"]) for row in links))
    return linked == selection.obligation_identities


def _return_account_is_valid(
    reference,
    bank_rows,
    bank_accounts,
    staff_id,
) -> bool:
    if reference.event_type is StaffPayoutEventType.REVERSAL:
        return True
    if len(bank_rows) != 1:
        return False
    identity = _optional_text(bank_rows[0].get("resolved_counterparty_account"))
    owners = tuple(
        account.owner_staff_id
        for account in bank_accounts
        if account.identity == identity and account.primary and account.active
    )
    return len(owners) == 1 and owners[0] == staff_id


def _bank_event_metadata(row) -> _EventPersistenceMetadata:
    identity = _optional_text(row.get("resolved_counterparty_account")) or ""
    occurred_on = row.get("transaction_date")
    if not isinstance(occurred_on, date):
        occurred_on = date.min
    return _EventPersistenceMetadata(
        occurred_on,
        _account_identity_hash(identity),
        int(row["id"]),
        None,
    )


def _reopen_event_metadata(reference, source, bank_rows):
    if reference.event_type is StaffPayoutEventType.RETURN and bank_rows:
        row = bank_rows[0]
        identity = _optional_text(row.get("resolved_counterparty_account")) or ""
        return _EventPersistenceMetadata(
            row.get("transaction_date") or date.min,
            _account_identity_hash(identity),
            int(row["id"]),
            reference.source_event_id,
        )
    source_hash = "" if source is None else str(source["bank_account_identity_hash"])
    return _EventPersistenceMetadata(
        reference.occurred_on or date.min,
        source_hash or _account_identity_hash("missing"),
        None,
        reference.source_event_id,
    )


def _account_identity_hash(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _bank_facts_version(bank_rows, reopen_fact) -> int:
    payload = {
        "rows": tuple(_bank_version_row(row) for row in bank_rows),
        "reopen": None if reopen_fact is None else _reopen_version_row(reopen_fact),
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return int(digest[:_JAVASCRIPT_SAFE_VERSION_HEX_DIGITS], 16)


def _bank_version_row(row) -> dict[str, object]:
    return {
        "id": int(row["id"]),
        "dedup_fingerprint": str(row["dedup_fingerprint"]),
        "transaction_date": _date_text(row.get("transaction_date")),
        "debit": _decimal_text(row.get("debit")),
        "credit": _decimal_text(row.get("credit")),
        "direction": str(row.get("direction")),
        "currency": _optional_text(row.get("currency")),
        "account": _optional_text(row.get("resolved_counterparty_account")),
        "classification_type": str(row.get("classification_type")),
        "reconciliation_status": str(row.get("reconciliation_status")),
        "payout_event_id": _optional_int(row.get("payout_event_id")),
    }


def _reopen_version_row(reopen_fact) -> dict[str, object]:
    return {
        "identity": reopen_fact.identity,
        "event_type": reopen_fact.event_type.value,
        "staff_id": reopen_fact.staff_id,
        "amount_ntd": reopen_fact.amount.amount,
        "source": reopen_fact.source_payout_event_identity,
        "succeeded": reopen_fact.succeeded,
    }


def _candidate_events(candidate):
    if isinstance(candidate, StaffPayoutCandidate):
        return candidate.events
    return (candidate.event,)


# Kept cohesive so event insertion and generated-identity validation stay atomic.
def _insert_event(cursor, request, event, metadata, ordinal) -> int:
    cursor.execute(
        _EVENT_INSERT_SQL,
        (
            event.staff_id,
            metadata.finance_import_row_id,
            event.event_type.value,
            event.amount.amount,
            metadata.occurred_on,
            metadata.bank_account_identity_hash,
            metadata.reversal_of_event_id,
            event.identity,
            _event_idempotency_key(request.idempotency_key, ordinal),
            request.actor.actor_id,
            request.reason,
        ),
    )
    event_id = int(cursor.lastrowid or 0)
    if event_id <= 0:
        raise RuntimeError("staff payout event identity was not generated")
    return event_id


def _insert_link(cursor, event_ids, link, ordinal) -> None:
    event_id = event_ids.get(link.event_identity)
    if event_id is None:
        raise RuntimeError("staff payout event link target is missing")
    cursor.execute(
        _LINK_INSERT_SQL,
        (
            event_id,
            link.obligation_identity,
            link.allocated_amount.amount,
            ordinal,
        ),
    )


def _projection_rows(cursor, obligation_identities):
    placeholders = _placeholders(obligation_identities)
    cursor.execute(
        "SELECT obligations.obligation_identity,obligations.staff_id,"
        "obligations.amount_due_ntd AS obligation_amount_ntd,"
        "SUM(CASE WHEN events.event_type='payout' "
        "THEN links.allocated_amount_ntd "
        "ELSE -links.allocated_amount_ntd END) AS net_paid_ntd,"
        "MAX(events.id) AS current_event_id "
        "FROM staff_obligations obligations "
        "JOIN staff_payout_obligation_links links "
        "ON links.obligation_identity=obligations.obligation_identity "
        "JOIN staff_payout_events events ON events.id=links.payout_event_id "
        f"WHERE obligations.obligation_identity IN ({placeholders}) "
        "GROUP BY obligations.obligation_identity,obligations.staff_id,"
        "obligations.amount_due_ntd ORDER BY obligations.obligation_identity",
        obligation_identities,
    )
    return tuple(cursor.fetchall())


def _validate_projection_rows(rows, expected_status, difference_mode) -> None:
    if not rows:
        raise RuntimeError("staff payable projection rows are missing")
    statuses = tuple(_projection_status(row) for row in rows)
    if difference_mode is StaffPayoutDifferenceMode.UNDERPAYMENT:
        if StaffPayableStatus.PARTIALLY_PAID in statuses and all(
            status in (StaffPayableStatus.PARTIALLY_PAID, StaffPayableStatus.COMPLETED)
            for status in statuses
        ):
            return
        raise RuntimeError("staff payable underpayment projection invariant failed")
    if difference_mode is StaffPayoutDifferenceMode.OVERPAYMENT:
        if all(status is StaffPayableStatus.COMPLETED for status in statuses):
            return
        raise RuntimeError("staff payable overpayment projection invariant failed")
    if any(status is not expected_status for status in statuses):
        raise RuntimeError("staff payable exact-zero projection invariant failed")


def _projection_status(row) -> StaffPayableStatus:
    obligation = int(row["obligation_amount_ntd"])
    net_paid = int(row["net_paid_ntd"])
    if net_paid == 0:
        return StaffPayableStatus.PAYABLE
    if net_paid == obligation:
        return StaffPayableStatus.COMPLETED
    return StaffPayableStatus.PARTIALLY_PAID


def _upsert_projection(cursor, row, version) -> None:
    obligation = int(row["obligation_amount_ntd"])
    net_paid = int(row["net_paid_ntd"])
    status = _projection_status(row)
    cursor.execute(
        _PROJECTION_UPSERT_SQL,
        (
            str(row["obligation_identity"]),
            int(row["staff_id"]),
            obligation,
            net_paid,
            obligation - net_paid,
            status.value,
            version,
            int(row["current_event_id"]),
        ),
    )


def _advance_account_version(cursor, request, resulting_version) -> None:
    cursor.execute(
        "UPDATE staff_payable_accounts SET aggregate_version=%s "
        "WHERE staff_id=%s AND aggregate_version=%s",
        (
            resulting_version,
            _candidate_staff_id_from_request_context(cursor, request),
            request.expected_staff_payables_version.value,
        ),
    )
    if int(cursor.rowcount) != 1:
        raise RuntimeError("staff payable aggregate version compare-and-swap failed")


def _candidate_staff_id_from_request_context(cursor, request) -> int:
    identities = request.selection.obligation_identities
    placeholders = _placeholders(identities)
    cursor.execute(
        "SELECT MIN(staff_id) AS staff_id FROM staff_obligations "
        f"WHERE obligation_identity IN ({placeholders})",
        identities,
    )
    row = cursor.fetchone()
    return int(row["staff_id"])


def _outbox_payload(candidate, request, payout_difference_identity=None) -> dict[str, object]:
    return {
        "staff_id": candidate.staff_id,
        "event_type": request.selection.event_type.value,
        "obligation_identities": request.selection.obligation_identities,
        "resulting_status": candidate.resulting_status.value,
        "difference_mode": None if request.selection.difference_mode is None else request.selection.difference_mode.value,
        "payout_difference_identity": payout_difference_identity,
        "finance_import_row_identities": tuple(
            event.finance_import_fact_identity
            for event in _candidate_events(candidate)
            if event.finance_import_fact_identity is not None
        ),
        "recovery_identity": None if not isinstance(candidate, StaffPayoutCandidate) or candidate.recovery is None else candidate.recovery.identity,
        "resulting_staff_payables_version": request.expected_staff_payables_version.value + 1,
        "expected_bank_facts_version": request.expected_bank_facts_version.value,
        "correlation_id": request.correlation_id.value,
    }


def _outbox_intent_key(key: IdempotencyKey) -> str:
    digest = hashlib.sha256(key.value.encode("utf-8")).hexdigest()
    return f"staff-payable-refresh:{digest}"


def _payout_difference_identity(key: IdempotencyKey) -> str:
    digest = hashlib.sha256(key.value.encode("utf-8")).hexdigest()
    return f"staff-payout-difference:{digest}"


def _event_idempotency_key(key, ordinal) -> str:
    digest = hashlib.sha256(f"{key.value}:{ordinal}".encode("utf-8")).hexdigest()
    return f"staff-payout-event:{digest}"


def _receipt_payload(receipt) -> dict[str, object]:
    return {
        "event_type": receipt.event_type.value,
        "staff_id": receipt.staff_id,
        "staff_payables_version": receipt.staff_payables_version,
        "bank_facts_version": receipt.bank_facts_version,
        "resulting_status": receipt.resulting_status.value,
        "event_count": receipt.event_count,
        "obligation_link_count": receipt.obligation_link_count,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "difference_mode": None if receipt.difference_mode is None else receipt.difference_mode.value,
        "recovery_identity": receipt.recovery_identity,
        "recovery_amount_ntd": receipt.recovery_amount_ntd,
    }


def _stored_receipt(row) -> StoredStaffPayoutReceipt:
    payload = _json_object(row["result_snapshot"])
    receipt = StaffPayoutReceipt(
        StaffPayoutEventType(str(payload["event_type"])),
        int(payload["staff_id"]),
        int(payload["staff_payables_version"]),
        int(payload["bank_facts_version"]),
        StaffPayableStatus(str(payload["resulting_status"])),
        int(payload["event_count"]),
        int(payload["obligation_link_count"]),
        PreviewFingerprint(str(payload["preview_fingerprint"])),
        None if payload.get("difference_mode") is None else StaffPayoutDifferenceMode(str(payload["difference_mode"])),
        payload.get("recovery_identity"),
        int(payload.get("recovery_amount_ntd", 0)),
    )
    if receipt.preview_fingerprint.value != str(row["preview_fingerprint"]):
        raise RuntimeError("staff payout receipt preview fingerprint mismatch")
    return StoredStaffPayoutReceipt(
        PreviewFingerprint(str(row["command_fingerprint"])),
        receipt,
    )


def _query_obligation_rows(cursor, staff_id):
    cursor.execute(
        "SELECT obligations.obligation_identity,obligations.case_no,"
        "obligations.amount_due_ntd,obligations.due_date,"
        "COALESCE(projection.net_paid_ntd,0) AS net_paid_ntd,"
        "COALESCE(projection.balance_ntd,obligations.amount_due_ntd) "
        "AS balance_ntd,"
        "COALESCE(projection.status,'payable') AS payout_status "
        "FROM staff_obligations obligations "
        "LEFT JOIN staff_payable_projections projection "
        "ON projection.obligation_identity=obligations.obligation_identity "
        "WHERE obligations.staff_id=%s "
        "AND obligations.direction='payable_to_staff' "
        "AND obligations.status<>'cancelled' "
        "AND obligations.amount_due_ntd>0 "
        "ORDER BY obligations.due_date,obligations.obligation_identity",
        (staff_id,),
    )
    return tuple(_materialize_query_row(row) for row in cursor.fetchall())


def _query_event_rows(cursor, staff_id):
    cursor.execute(
        "SELECT id,event_type,amount_ntd,occurred_on,"
        "finance_import_row_id,reversal_of_event_id,reconciliation_reference "
        "FROM staff_payout_events WHERE staff_id=%s ORDER BY occurred_on,id",
        (staff_id,),
    )
    return tuple(_materialize_query_row(row) for row in cursor.fetchall())


def _materialize_query_row(row) -> dict[str, object]:
    return {
        str(key): _json_scalar(value)
        for key, value in row.items()
    }


def _canonical_json(payload) -> str:
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
        raise RuntimeError("staff payout JSON snapshot must be an object")
    return parsed


def _json_scalar(value):
    if isinstance(value, (date, Decimal)):
        return str(value)
    return value


def _date_text(value) -> str | None:
    return value.isoformat() if isinstance(value, date) else None


def _decimal_text(value) -> str | None:
    return None if value is None else str(value)


def _optional_text(value) -> str | None:
    return None if value is None else str(value)


def _optional_int(value) -> int | None:
    return None if value is None else int(value)


def _placeholders(values) -> str:
    if not values:
        return "NULL"
    return ",".join("%s" for _ in values)


_RECEIPT_SELECT_SQL = (
    "SELECT command_fingerprint,preview_fingerprint,result_snapshot "
    "FROM staff_payables_apply_receipts WHERE idempotency_key=%s FOR UPDATE"
)
_EVENT_INSERT_SQL = (
    "INSERT INTO staff_payout_events "
    "(staff_id,finance_import_row_id,event_type,amount_ntd,occurred_on,"
    "bank_account_identity_hash,reversal_of_event_id,"
    "reconciliation_reference,idempotency_key,actor,reason) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_LINK_INSERT_SQL = (
    "INSERT INTO staff_payout_obligation_links "
    "(payout_event_id,obligation_identity,allocated_amount_ntd,"
    "allocation_ordinal) VALUES (%s,%s,%s,%s)"
)
_PROJECTION_UPSERT_SQL = (
    "INSERT INTO staff_payable_projections "
    "(obligation_identity,staff_id,obligation_amount_ntd,net_paid_ntd,"
    "balance_ntd,status,aggregate_version,current_event_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE "
    "staff_id=VALUES(staff_id),"
    "obligation_amount_ntd=VALUES(obligation_amount_ntd),"
    "net_paid_ntd=VALUES(net_paid_ntd),"
    "balance_ntd=VALUES(balance_ntd),status=VALUES(status),"
    "aggregate_version=VALUES(aggregate_version),"
    "current_event_id=VALUES(current_event_id)"
)
_OUTBOX_INSERT_SQL = (
    "INSERT INTO staff_payables_outbox "
    "(staff_id,intent_key,intent_type,payload_snapshot) "
    "VALUES (%s,%s,%s,%s)"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO staff_payables_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,"
    "staff_id,result_snapshot) VALUES (%s,%s,%s,%s,%s)"
)
_RECOVERY_INSERT_SQL = (
    "INSERT INTO staff_overpayment_recoveries "
    "(recovery_identity,staff_id,original_amount_ntd,remaining_amount_ntd,"
    "source_bank_fact_identities,source_payout_event_ids,source_obligation_identities,"
    "actor,reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
__all__ = [
    "MySqlStaffPayoutRepository",
    "StaffPayoutMySqlUnitOfWork",
    "build_return_reopen_identity",
    "build_reversal_reopen_identity",
]
