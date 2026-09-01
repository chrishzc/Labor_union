"""
File: historical_client_finance_completion_read_adapter.py
Description: 唯讀重建 Client Finance 義務、ledger 與 allocation 供歷史案件結清判定。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer
from subsystems.orders.historical_completion_oracle import (
    CompletionOwner,
    HistoricalSettlementReadback,
)


_CASE_NUMBER_MAXIMUM_LENGTH = 50
_IDENTITY_MAXIMUM_LENGTH = 191
_SIGNED_BIGINT_MAXIMUM = 9_223_372_036_854_775_807
_POSITIVE_ENTRY_TYPES = frozenset(
    {
        "receipt",
        "refund",
        "subsidy_return",
        "subsidy_advance",
        "adjustment",
    }
)
_REVERSAL_ENTRY_TYPES = frozenset(
    {
        "reversal",
        "refund_reversal",
        "subsidy_return_reversal",
        "subsidy_advance_reversal",
    }
)
_CLIENT_LEDGER_ENTRY_TYPES = _POSITIVE_ENTRY_TYPES | _REVERSAL_ENTRY_TYPES
_REVERSAL_TARGET_TYPES = {
    "reversal": "receipt",
    "refund_reversal": "refund",
    "subsidy_return_reversal": "subsidy_return",
    "subsidy_advance_reversal": "subsidy_advance",
}
_CLIENT_OBLIGATION_TYPES = frozenset(
    {"deposit", "first", "second", "refund", "subsidy_return", "adjustment"}
)
_CLIENT_OBLIGATION_DIRECTIONS = frozenset(
    {"receivable_from_client", "payable_to_client"}
)


# One statement is intentional: MySQL gives one statement-level consistent read
# without changing the caller connection's transaction state.  A read-only
# START TRANSACTION would leave ownership of commit/rollback ambiguous here.
_CURRENT_CASE_READ_SQL = """
SELECT 'account' AS row_kind,
       a.case_no AS account_case_no,
       a.aggregate_version AS account_aggregate_version,
       NULL AS obligation_identity,
       NULL AS obligation_case_no,
       NULL AS obligation_type,
       NULL AS obligation_direction,
       NULL AS obligation_status,
       NULL AS obligation_amount_due_ntd,
       NULL AS obligation_current_event_id,
       NULL AS obligation_projection_version,
       NULL AS obligation_contracted_amount_ntd,
       NULL AS ledger_entry_id,
       NULL AS ledger_entry_type,
       NULL AS ledger_amount_ntd,
       NULL AS ledger_occurred_on,
       NULL AS ledger_reconciliation_reference,
       NULL AS ledger_reversal_of_entry_id,
       NULL AS target_entry_id,
       NULL AS target_case_no,
       NULL AS target_entry_type,
       NULL AS target_amount_ntd,
       NULL AS target_reversal_of_entry_id,
       NULL AS allocation_obligation_identity,
       NULL AS allocation_amount_ntd,
       NULL AS allocation_ordinal,
       NULL AS historical_projection_event_id,
       NULL AS historical_projection_case_no,
       NULL AS historical_projection_confirmation_kind,
       NULL AS historical_projection_amount_ntd,
       NULL AS historical_projection_obligation_version,
       NULL AS historical_projection_account_version,
       NULL AS historical_event_identity,
       NULL AS historical_event_case_no,
       NULL AS historical_event_direction,
       NULL AS historical_event_confirmation_kind,
       NULL AS historical_event_payer_role,
       NULL AS historical_event_payee_role,
       NULL AS historical_event_adoption_receipt_id,
       NULL AS historical_event_expected_version,
       NULL AS historical_event_resulting_version,
       NULL AS historical_link_amount_ntd,
       NULL AS historical_link_obligation_type,
       NULL AS historical_link_direction,
       NULL AS historical_link_obligation_version,
       NULL AS historical_link_ordinal
FROM client_finance_accounts a
WHERE a.case_no=%s
UNION ALL
SELECT 'obligation', a.case_no, a.aggregate_version,
       o.obligation_identity, o.case_no, o.obligation_type, o.direction,
       o.status, o.amount_due_ntd, o.current_event_id, o.projection_version,
       e.after_amount_ntd,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL,
       hp.current_event_id, hp.case_no, hp.confirmation_kind,
       hp.amount_snapshot_ntd, hp.obligation_projection_version,
       hp.account_version, he.event_identity, he.case_no, he.direction,
       he.confirmation_kind, he.payer_role, he.payee_role,
       he.historical_adoption_receipt_id, he.expected_account_version,
       he.resulting_account_version, hl.amount_snapshot_ntd,
       hl.obligation_type, hl.obligation_direction,
       hl.obligation_projection_version, hl.link_ordinal
FROM client_finance_accounts a
JOIN client_obligations o ON o.case_no=a.case_no
LEFT JOIN client_obligation_events e ON e.id=o.current_event_id
LEFT JOIN historical_client_payment_projections hp
       ON hp.obligation_identity=o.obligation_identity
LEFT JOIN historical_client_payment_events he ON he.id=hp.current_event_id
LEFT JOIN historical_client_payment_obligation_links hl
       ON hl.event_id=hp.current_event_id
      AND hl.obligation_identity=o.obligation_identity
WHERE a.case_no=%s
UNION ALL
SELECT 'ledger', a.case_no, a.aggregate_version,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       ledger.id, ledger.entry_type, ledger.amount_ntd, ledger.occurred_on,
       ledger.reconciliation_reference, ledger.reversal_of_entry_id,
       target.id, target.case_no, target.entry_type, target.amount_ntd,
       target.reversal_of_entry_id,
       allocation.obligation_identity, allocation.amount_ntd,
       allocation.allocation_ordinal,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
FROM client_finance_accounts a
JOIN client_ledger_entries ledger ON ledger.case_no=a.case_no
LEFT JOIN client_ledger_entries target
       ON target.id=ledger.reversal_of_entry_id
LEFT JOIN client_ledger_obligation_allocations allocation
       ON allocation.ledger_entry_id=ledger.id
WHERE a.case_no=%s
"""


class MySqlClientFinanceCompletionReadAdapter:
    """Read one case's current Client Finance roots without locking or writes."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_completion_readback(
        self, case_no: str, *, for_update: bool = False
    ) -> HistoricalSettlementReadback | None:
        """Return a reducer-validated readback from one statement-level snapshot."""

        require_canonical_text(case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        if for_update is not False:
            raise ValueError("historical client finance completion read is read-only")

        with self._connection.cursor() as cursor:
            cursor.execute(_CURRENT_CASE_READ_SQL, (case_no, case_no, case_no))
            rows = _mapping_rows(cursor.fetchall(), "client finance current roots")

        account_rows = tuple(row for row in rows if row.get("row_kind") == "account")
        if not account_rows:
            return None
        if len(account_rows) != 1:
            raise ValueError("client finance account readback is invalid")
        account = account_rows[0]
        _validate_account(account, case_no)
        if any(
            not isinstance(row.get("row_kind"), str)
            or row.get("row_kind") not in {"account", "obligation", "ledger"}
            for row in rows
        ):
            raise ValueError("client finance current roots contain an unknown row kind")
        obligation_rows = tuple(
            _obligation_row(row) for row in rows if row.get("row_kind") == "obligation"
        )
        ledger_rows = tuple(
            _ledger_row(row) for row in rows if row.get("row_kind") == "ledger"
        )
        historical_rows = tuple(
            _historical_row(row)
            for row in rows
            if row.get("row_kind") == "obligation"
            and row.get("historical_projection_event_id") is not None
        )
        return _readback(
            case_no, account, obligation_rows, ledger_rows, historical_rows
        )


def _obligation_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "obligation_identity": row.get("obligation_identity"),
        "case_no": row.get("obligation_case_no"),
        "obligation_type": row.get("obligation_type"),
        "direction": row.get("obligation_direction"),
        "status": row.get("obligation_status"),
        "amount_due_ntd": row.get("obligation_amount_due_ntd"),
        "current_event_id": row.get("obligation_current_event_id"),
        "projection_version": row.get("obligation_projection_version"),
        "contracted_amount_ntd": row.get("obligation_contracted_amount_ntd"),
    }


def _ledger_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "ledger_entry_id": row.get("ledger_entry_id"),
        "entry_type": row.get("ledger_entry_type"),
        "amount_ntd": row.get("ledger_amount_ntd"),
        "occurred_on": row.get("ledger_occurred_on"),
        "reconciliation_reference": row.get("ledger_reconciliation_reference"),
        "reversal_of_entry_id": row.get("ledger_reversal_of_entry_id"),
        "target_entry_id": row.get("target_entry_id"),
        "target_case_no": row.get("target_case_no"),
        "target_entry_type": row.get("target_entry_type"),
        "target_amount_ntd": row.get("target_amount_ntd"),
        "target_reversal_of_entry_id": row.get("target_reversal_of_entry_id"),
        "obligation_identity": row.get("allocation_obligation_identity"),
        "allocation_amount_ntd": row.get("allocation_amount_ntd"),
        "allocation_ordinal": row.get("allocation_ordinal"),
        # The SQL is case-scoped; this keeps an explicit case value available
        # to tests and future adapter implementations.
        "case_no": row.get("account_case_no"),
    }


def _historical_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "obligation_identity": row.get("obligation_identity"),
        "projection_event_id": row.get("historical_projection_event_id"),
        "projection_case_no": row.get("historical_projection_case_no"),
        "projection_confirmation_kind": row.get(
            "historical_projection_confirmation_kind"
        ),
        "projection_amount_ntd": row.get("historical_projection_amount_ntd"),
        "projection_obligation_version": row.get(
            "historical_projection_obligation_version"
        ),
        "projection_account_version": row.get(
            "historical_projection_account_version"
        ),
        "event_identity": row.get("historical_event_identity"),
        "event_case_no": row.get("historical_event_case_no"),
        "event_direction": row.get("historical_event_direction"),
        "event_confirmation_kind": row.get("historical_event_confirmation_kind"),
        "event_payer_role": row.get("historical_event_payer_role"),
        "event_payee_role": row.get("historical_event_payee_role"),
        "event_adoption_receipt_id": row.get(
            "historical_event_adoption_receipt_id"
        ),
        "event_expected_version": row.get("historical_event_expected_version"),
        "event_resulting_version": row.get("historical_event_resulting_version"),
        "link_amount_ntd": row.get("historical_link_amount_ntd"),
        "link_obligation_type": row.get("historical_link_obligation_type"),
        "link_direction": row.get("historical_link_direction"),
        "link_obligation_version": row.get("historical_link_obligation_version"),
        "link_ordinal": row.get("historical_link_ordinal"),
    }


def _readback(
    case_no: str,
    account: Mapping[str, Any],
    obligation_rows: tuple[Mapping[str, Any], ...],
    ledger_rows: tuple[Mapping[str, Any], ...],
    historical_rows: tuple[Mapping[str, Any], ...] = (),
) -> HistoricalSettlementReadback:
    blockers: list[str] = []
    account_version = int(account["account_aggregate_version"])
    obligation_payload, obligation_valid, obligation_index = _validate_obligations(
        obligation_rows, case_no, account_version, blockers
    )
    if not obligation_rows:
        blockers.append("client_finance_obligations_missing")

    zero_payment_terminal = bool(obligation_payload) and all(
        item["status"] == "settled"
        and item["amount_due_ntd"] == 0
        and item["contracted_amount_ntd"] == 0
        for item in obligation_payload
    )
    ledger_payload, allocation_payload, ledger_valid, allocations_by_obligation = (
        _validate_ledger_lineage(ledger_rows, case_no, set(obligation_index), blockers)
    )
    historical_payload, historical_link_payload, historical_terminal = (
        _validate_historical_lineage(
            historical_rows,
            case_no,
            account_version,
            obligation_index,
            blockers,
        )
    )
    _validate_reversal_lineage(ledger_rows, case_no, blockers)
    normal_obligations = {
        identity: obligation
        for identity, obligation in obligation_index.items()
        if identity not in historical_terminal
    }
    _validate_obligation_net_state(
        normal_obligations, allocations_by_obligation, blockers
    )
    all_terminal_without_ledger = bool(obligation_payload) and all(
        item["status"] == "cancelled"
        or (
            item["status"] == "settled"
            and item["amount_due_ntd"] == 0
            and item["contracted_amount_ntd"] == 0
        )
        or item["obligation_identity"] in historical_terminal
        for item in obligation_payload
    )
    if not ledger_rows and not all_terminal_without_ledger:
        blockers.extend(
            (
                "client_finance_settlement_lineage_missing",
                "client_finance_allocation_lineage_missing",
            )
        )
    lineage_valid = obligation_valid and ledger_valid and not blockers
    settlement_identity = (
        fingerprint_payload(
            {
                "case_no": case_no,
                "account_aggregate_version": account_version,
                "obligations": obligation_payload,
                "ledger_entries": ledger_payload,
                "historical_payments": historical_payload,
                "zero_payment_terminal": zero_payment_terminal,
            }
        ).value
        if obligation_payload
        and (ledger_payload or zero_payment_terminal or historical_payload)
        and lineage_valid
        else None
    )
    allocation_identity = (
        fingerprint_payload(
            {
                "case_no": case_no,
                "obligations": tuple(
                    item["obligation_identity"] for item in obligation_payload
                ),
                "allocations": allocation_payload,
                "historical_links": historical_link_payload,
                "zero_payment_terminal": zero_payment_terminal,
            }
        ).value
        if (
            allocation_payload
            or zero_payment_terminal
            or historical_link_payload
        )
        and lineage_valid
        else None
    )
    return HistoricalSettlementReadback(
        case_no=case_no,
        owner=CompletionOwner.CLIENT_FINANCE,
        aggregate_version=account_version,
        settlement_lineage_identity=settlement_identity,
        obligation_count=len(obligation_rows),
        open_obligation_count=sum(
            1
            for row in obligation_rows
            if row.get("status") == "open"
            and row.get("obligation_identity") not in historical_terminal
        ),
        allocation_lineage_identity=allocation_identity,
        readback_available=not blockers,
        integrity_blockers=tuple(sorted(set(blockers))),
    )


def _validate_historical_lineage(
    rows: tuple[Mapping[str, Any], ...],
    case_no: str,
    account_version: int,
    obligations: Mapping[str, Mapping[str, Any]],
    blockers: list[str],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], set[str]]:
    payload: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    terminal: set[str] = set()
    seen_events: set[int] = set()
    seen_ordinals: dict[int, set[int]] = {}
    for row in rows:
        identity = row.get("obligation_identity")
        obligation = obligations.get(identity) if isinstance(identity, str) else None
        valid = obligation is not None
        if obligation is None:
            blockers.append("client_finance_historical_obligation_missing")
            continue
        event_id = row.get("projection_event_id")
        if not _is_positive_bigint(event_id):
            blockers.append("client_finance_historical_event_missing")
            valid = False
        confirmation = row.get("projection_confirmation_kind")
        if confirmation not in {"paid", "settled"}:
            blockers.append("client_finance_historical_confirmation_kind_invalid")
            valid = False
        if row.get("projection_case_no") != case_no or row.get("event_case_no") != case_no:
            blockers.append("client_finance_historical_case_mismatch")
            valid = False
        amount = row.get("projection_amount_ntd")
        if amount != obligation.get("amount_due_ntd") or amount != row.get(
            "link_amount_ntd"
        ):
            blockers.append("client_finance_historical_amount_mismatch")
            valid = False
        obligation_version = obligation.get("projection_version")
        if (
            row.get("projection_obligation_version") != obligation_version
            or row.get("link_obligation_version") != obligation_version
        ):
            blockers.append("client_finance_historical_obligation_version_mismatch")
            valid = False
        if row.get("projection_account_version") != account_version:
            blockers.append("client_finance_historical_account_version_mismatch")
            valid = False
        expected_version = row.get("event_expected_version")
        resulting_version = row.get("event_resulting_version")
        if (
            not _is_nonnegative_bigint(expected_version)
            or not _is_positive_bigint(resulting_version)
            or resulting_version != expected_version + 1
            or resulting_version != account_version
        ):
            blockers.append("client_finance_historical_event_version_mismatch")
            valid = False
        event_identity = row.get("event_identity")
        if not isinstance(event_identity, str):
            blockers.append("client_finance_historical_event_identity_invalid")
            valid = False
        else:
            try:
                require_canonical_text(
                    event_identity,
                    "historical client payment event identity",
                    _IDENTITY_MAXIMUM_LENGTH,
                )
            except ValueError:
                blockers.append("client_finance_historical_event_identity_invalid")
                valid = False
        direction = obligation.get("direction")
        roles = (
            ("client", "union")
            if direction == "receivable_from_client"
            else ("union", "client")
        )
        if (
            row.get("event_direction") != direction
            or row.get("link_direction") != direction
            or row.get("event_payer_role") != roles[0]
            or row.get("event_payee_role") != roles[1]
        ):
            blockers.append("client_finance_historical_direction_mismatch")
            valid = False
        if row.get("event_confirmation_kind") != confirmation:
            blockers.append("client_finance_historical_confirmation_mismatch")
            valid = False
        if row.get("link_obligation_type") != obligation.get("obligation_type"):
            blockers.append("client_finance_historical_obligation_type_mismatch")
            valid = False
        adoption_receipt_id = row.get("event_adoption_receipt_id")
        ordinal = row.get("link_ordinal")
        if not _is_positive_bigint(adoption_receipt_id):
            blockers.append("client_finance_historical_adoption_receipt_missing")
            valid = False
        if not _is_positive_bigint(ordinal):
            blockers.append("client_finance_historical_link_ordinal_invalid")
            valid = False
        elif _is_positive_bigint(event_id):
            ordinals = seen_ordinals.setdefault(event_id, set())
            if ordinal in ordinals:
                blockers.append("client_finance_historical_link_ordinal_duplicate")
                valid = False
            ordinals.add(ordinal)
        if _is_positive_bigint(event_id):
            seen_events.add(event_id)
        event_payload = {
            "event_id": event_id,
            "event_identity": event_identity,
            "case_no": case_no,
            "direction": direction,
            "confirmation_kind": confirmation,
            "expected_account_version": expected_version,
            "resulting_account_version": resulting_version,
            "adoption_receipt_id": adoption_receipt_id,
        }
        if not any(item["event_id"] == event_id for item in payload):
            payload.append(event_payload)
        links.append(
            {
                "event_id": event_id,
                "obligation_identity": identity,
                "amount_ntd": amount,
                "obligation_version": obligation_version,
                "link_ordinal": ordinal,
            }
        )
        if valid:
            terminal.add(identity)
    return (
        tuple(sorted(payload, key=lambda item: item["event_id"])),
        tuple(
            sorted(
                links,
                key=lambda item: (item["event_id"], item["link_ordinal"]),
            )
        ),
        terminal,
    )


def _validate_account(account: Mapping[str, Any], case_no: str) -> None:
    if account.get("account_case_no") != case_no:
        raise ValueError("client finance account case identity mismatch")
    value = account.get("account_aggregate_version")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("client finance aggregate version is invalid")
    require_nonnegative_integer(value, "client finance aggregate version")


def _validate_obligations(
    rows: tuple[Mapping[str, Any], ...],
    case_no: str,
    account_version: int,
    blockers: list[str],
) -> tuple[tuple[dict[str, Any], ...], bool, dict[str, dict[str, Any]]]:
    payload: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    valid = True
    for row in rows:
        identity = row.get("obligation_identity")
        if not isinstance(identity, str):
            blockers.append("client_finance_obligation_identity_missing")
            valid = False
            continue
        try:
            require_canonical_text(identity, "client obligation identity", _IDENTITY_MAXIMUM_LENGTH)
        except ValueError:
            blockers.append("client_finance_obligation_identity_invalid")
            valid = False
            continue
        if identity in index:
            blockers.append("client_finance_obligation_duplicate")
            valid = False
        if row.get("case_no") != case_no:
            blockers.append("client_finance_obligation_case_identity_mismatch")
            valid = False
        status = row.get("status")
        if not isinstance(status, str) or status not in {"open", "settled", "cancelled"}:
            blockers.append("client_finance_obligation_status_invalid")
            valid = False
        obligation_type = row.get("obligation_type")
        if not isinstance(obligation_type, str) or obligation_type not in _CLIENT_OBLIGATION_TYPES:
            blockers.append("client_finance_obligation_type_invalid")
            valid = False
        direction = row.get("direction")
        if not isinstance(direction, str) or direction not in _CLIENT_OBLIGATION_DIRECTIONS:
            blockers.append("client_finance_obligation_direction_invalid")
            valid = False
        amount = row.get("amount_due_ntd")
        if not _is_nonnegative_bigint(amount):
            blockers.append("client_finance_obligation_amount_invalid")
            valid = False
            amount = 0
        elif status == "open" and amount <= 0:
            blockers.append("client_finance_open_obligation_amount_invalid")
            valid = False
        elif isinstance(status, str) and status in {"settled", "cancelled"} and amount != 0:
            blockers.append("client_finance_closed_obligation_amount_invalid")
            valid = False
        event_id = row.get("current_event_id")
        if not _is_positive_bigint(event_id):
            blockers.append("client_finance_obligation_event_missing")
            valid = False
        projection_version = row.get("projection_version")
        if (
            isinstance(projection_version, bool)
            or not isinstance(projection_version, int)
            or projection_version < 0
        ):
            blockers.append("client_finance_obligation_projection_version_invalid")
            valid = False
            projection_version = 0
        elif projection_version > account_version:
            blockers.append("client_finance_obligation_projection_version_ahead")
            valid = False
        contracted = row.get("contracted_amount_ntd")
        if not _is_nonnegative_bigint(contracted):
            blockers.append("client_finance_obligation_contract_amount_invalid")
            valid = False
            contracted = 0
        elif status == "open" and contracted <= 0:
            blockers.append("client_finance_obligation_contract_amount_invalid")
            valid = False
        normalized = {
            "obligation_identity": identity,
            "case_no": row.get("case_no"),
            "obligation_type": obligation_type,
            "direction": direction,
            "status": status,
            "amount_due_ntd": amount,
            "current_event_id": event_id,
            "projection_version": projection_version,
            "contracted_amount_ntd": contracted,
        }
        payload.append(normalized)
        index.setdefault(identity, normalized)
    return tuple(sorted(payload, key=lambda item: item["obligation_identity"])), valid, index


def _validate_ledger_lineage(
    rows: tuple[Mapping[str, Any], ...],
    case_no: str,
    obligation_identities: set[str],
    blockers: list[str],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], bool, dict[str, int]]:
    ledger_by_id: dict[int, dict[str, Any]] = {}
    allocations_by_ledger: dict[int, list[dict[str, Any]]] = {}
    allocations_by_obligation: dict[str, int] = {}
    valid = True
    for row in rows:
        ledger_id = row.get("ledger_entry_id")
        if not _is_positive_bigint(ledger_id):
            blockers.append("client_finance_ledger_identity_invalid")
            valid = False
            continue
        entry_type = row.get("entry_type")
        amount = row.get("amount_ntd")
        reference = row.get("reconciliation_reference")
        occurred = _date_text(row.get("occurred_on"))
        if row.get("case_no") != case_no:
            blockers.append("client_finance_ledger_case_identity_mismatch")
            valid = False
        if not isinstance(entry_type, str) or entry_type not in _CLIENT_LEDGER_ENTRY_TYPES:
            blockers.append("client_finance_ledger_entry_type_invalid")
            valid = False
        if isinstance(entry_type, str) and entry_type in _POSITIVE_ENTRY_TYPES and any(
            row.get(field) is not None
            for field in (
                "reversal_of_entry_id",
                "target_entry_id",
                "target_case_no",
                "target_entry_type",
                "target_amount_ntd",
                "target_reversal_of_entry_id",
            )
        ):
            blockers.append("client_finance_positive_entry_reversal_shape_invalid")
            valid = False
        if isinstance(entry_type, str) and entry_type in _REVERSAL_ENTRY_TYPES:
            reversal_id = row.get("reversal_of_entry_id")
            target_id = row.get("target_entry_id")
            target_amount = row.get("target_amount_ntd")
            if (
                not _is_positive_bigint(reversal_id)
                or not _is_positive_bigint(target_id)
                or target_id != reversal_id
                or not _is_positive_bigint(target_amount)
            ):
                blockers.append("client_finance_reversal_target_invalid")
                valid = False
        if not _is_positive_bigint(amount):
            blockers.append("client_finance_ledger_amount_invalid")
            valid = False
            amount = 0
        if not isinstance(reference, str):
            blockers.append("client_finance_settlement_lineage_missing")
            valid = False
        else:
            try:
                require_canonical_text(reference, "client settlement lineage identity", _IDENTITY_MAXIMUM_LENGTH)
            except ValueError:
                blockers.append("client_finance_settlement_lineage_missing")
                valid = False
        if occurred is None:
            blockers.append("client_finance_ledger_date_invalid")
            valid = False
        normalized = {
            "ledger_entry_id": ledger_id,
            "entry_type": entry_type,
            "amount_ntd": amount,
            "occurred_on": occurred,
            "reconciliation_reference": reference,
            "reversal_of_entry_id": row.get("reversal_of_entry_id"),
            "target_entry_id": row.get("target_entry_id"),
            "target_case_no": row.get("target_case_no"),
            "target_entry_type": row.get("target_entry_type"),
            "target_amount_ntd": row.get("target_amount_ntd"),
            "target_reversal_of_entry_id": row.get("target_reversal_of_entry_id"),
        }
        previous = ledger_by_id.get(ledger_id)
        immutable_fields = tuple(normalized)
        if previous is not None and any(previous[field] != normalized[field] for field in immutable_fields):
            blockers.append("client_finance_ledger_identity_conflict")
            valid = False
        ledger_by_id.setdefault(ledger_id, normalized)

        allocation_identity = row.get("obligation_identity")
        allocation_amount = row.get("allocation_amount_ntd")
        ordinal = row.get("allocation_ordinal")
        if allocation_identity is None and allocation_amount is None and ordinal is None:
            continue
        if (
            not isinstance(allocation_identity, str)
            or (isinstance(allocation_identity, str) and allocation_identity not in obligation_identities)
            or not _is_positive_bigint(allocation_amount)
            or not _is_positive_bigint(ordinal)
        ):
            blockers.append(
                "client_finance_allocation_obligation_missing"
                if not isinstance(allocation_identity, str)
                or allocation_identity not in obligation_identities
                else "client_finance_allocation_invalid"
            )
            valid = False
            continue
        allocation = {
            "ledger_entry_id": ledger_id,
            "obligation_identity": allocation_identity,
            "amount_ntd": allocation_amount,
            "allocation_ordinal": ordinal,
            "target_case_no": row.get("target_case_no"),
            "target_entry_type": row.get("target_entry_type"),
            "target_amount_ntd": row.get("target_amount_ntd"),
            "target_reversal_of_entry_id": row.get("target_reversal_of_entry_id"),
            "entry_type": entry_type,
            "reversal_of_entry_id": row.get("reversal_of_entry_id"),
            "target_entry_id": row.get("target_entry_id"),
        }
        existing = allocations_by_ledger.setdefault(ledger_id, [])
        if any(
            item["obligation_identity"] == allocation_identity
            or item["allocation_ordinal"] == ordinal
            for item in existing
        ):
            blockers.append("client_finance_allocation_duplicate")
            valid = False
        existing.append(allocation)

    for ledger_id, ledger in ledger_by_id.items():
        allocations = allocations_by_ledger.get(ledger_id, [])
        if not allocations:
            blockers.append("client_finance_ledger_allocation_missing")
            valid = False
            continue
        allocated_total = sum(item["amount_ntd"] for item in allocations)
        if allocated_total != ledger["amount_ntd"]:
            blockers.append(
                "client_finance_reversal_allocation_total_mismatch"
                if isinstance(ledger["entry_type"], str)
                and ledger["entry_type"] in _REVERSAL_ENTRY_TYPES
                else "client_finance_ledger_allocation_total_mismatch"
            )
            valid = False
        sign = -1 if isinstance(ledger["entry_type"], str) and ledger["entry_type"] in _REVERSAL_ENTRY_TYPES else 1
        for allocation in allocations:
            identity = allocation["obligation_identity"]
            allocations_by_obligation[identity] = allocations_by_obligation.get(identity, 0) + sign * allocation["amount_ntd"]

    ledger_payload = tuple(sorted(ledger_by_id.values(), key=lambda item: item["ledger_entry_id"]))
    allocation_payload = tuple(
        sorted(
            (
                item
                for allocations in allocations_by_ledger.values()
                for item in allocations
            ),
            key=lambda item: (item["ledger_entry_id"], item["allocation_ordinal"]),
        )
    )
    return ledger_payload, allocation_payload, valid, allocations_by_obligation


def _validate_reversal_lineage(
    rows: tuple[Mapping[str, Any], ...], case_no: str, blockers: list[str]
) -> None:
    ledger_by_id: dict[int, Mapping[str, Any]] = {}
    allocations_by_ledger: dict[int, dict[str, int]] = {}
    reversal_rows: dict[int, Mapping[str, Any]] = {}
    for row in rows:
        ledger_id = row.get("ledger_entry_id")
        if not _is_positive_bigint(ledger_id):
            continue
        ledger_by_id.setdefault(ledger_id, row)
        identity = row.get("obligation_identity")
        amount = row.get("allocation_amount_ntd")
        if isinstance(identity, str) and _is_positive_bigint(amount):
            allocations_by_ledger.setdefault(ledger_id, {})[identity] = amount
        if isinstance(row.get("entry_type"), str) and row.get("entry_type") in _REVERSAL_ENTRY_TYPES:
            # The ledger/allocation join emits one row per allocation.  The
            # amount and target belong to the ledger entry, so validate them
            # once while retaining every allocation in the map above.
            reversal_rows.setdefault(ledger_id, row)

    reversed_amounts: dict[int, int] = {}
    reversed_allocations: dict[tuple[int, str], int] = {}
    for row in reversal_rows.values():
        reversal_id = row["ledger_entry_id"]
        target_id = row.get("reversal_of_entry_id")
        target = (
            ledger_by_id.get(target_id)
            if _is_positive_bigint(target_id)
            else None
        )
        target_entry_id = row.get("target_entry_id")
        if (
            target is None
            or not _is_positive_bigint(target_entry_id)
            or target_entry_id != target_id
        ):
            blockers.append("client_finance_reversal_target_invalid")
            continue
        if row.get("target_case_no") != case_no:
            blockers.append("client_finance_reversal_target_case_mismatch")
        target_type = target.get("entry_type")
        if isinstance(target_type, str) and target_type in _REVERSAL_ENTRY_TYPES:
            blockers.append("client_finance_reversal_of_reversal_forbidden")
        reversal_type = row.get("entry_type")
        expected_target_type = (
            _REVERSAL_TARGET_TYPES.get(reversal_type)
            if isinstance(reversal_type, str)
            else None
        )
        if target_type != expected_target_type:
            blockers.append("client_finance_reversal_target_type_invalid")
        if row.get("target_entry_type") != target_type:
            blockers.append("client_finance_reversal_target_type_mismatch")
        if target.get("reversal_of_entry_id") is not None:
            blockers.append("client_finance_reversal_of_reversal_forbidden")
        if row.get("target_reversal_of_entry_id") != target.get("reversal_of_entry_id"):
            blockers.append("client_finance_reversal_target_lineage_mismatch")
        target_amount = target.get("amount_ntd")
        amount = row.get("amount_ntd")
        if (
            not _is_positive_bigint(target_amount)
            or not _is_positive_bigint(amount)
        ):
            blockers.append("client_finance_reversal_target_amount_invalid")
            continue
        if row.get("target_amount_ntd") != target_amount:
            blockers.append("client_finance_reversal_target_amount_mismatch")
        reversed_amounts[target_id] = reversed_amounts.get(target_id, 0) + amount
        if reversed_amounts[target_id] > target_amount:
            blockers.append("client_finance_reversal_amount_exceeded")
        for identity, allocation_amount in allocations_by_ledger.get(reversal_id, {}).items():
            key = (target_id, identity)
            reversed_allocations[key] = reversed_allocations.get(key, 0) + allocation_amount
            target_allocated = allocations_by_ledger.get(target_id, {}).get(identity, 0)
            if reversed_allocations[key] > target_allocated:
                blockers.append("client_finance_reversal_allocation_exceeded")


def _validate_obligation_net_state(
    obligations: Mapping[str, Mapping[str, Any]],
    allocations_by_obligation: Mapping[str, int],
    blockers: list[str],
) -> None:
    for identity, obligation in obligations.items():
        status = obligation.get("status")
        if not isinstance(status, str) or status not in {"open", "settled"}:
            continue
        net = allocations_by_obligation.get(identity, 0)
        contracted = obligation.get("contracted_amount_ntd")
        remaining = obligation.get("amount_due_ntd")
        if not isinstance(contracted, int) or not isinstance(remaining, int):
            continue
        if net < 0 or net > contracted or net + remaining != contracted:
            blockers.append("client_finance_obligation_net_state_mismatch")
        elif status == "settled" and net != contracted:
            blockers.append("client_finance_settled_obligation_net_mismatch")
        elif status == "open" and net == contracted:
            blockers.append("client_finance_open_obligation_net_mismatch")


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if type(value) is date:
        return value.isoformat()
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return None
        return parsed.isoformat() if parsed.isoformat() == value else None
    return None


def _is_nonnegative_bigint(value: Any) -> bool:
    return type(value) is int and 0 <= value <= _SIGNED_BIGINT_MAXIMUM


def _is_positive_bigint(value: Any) -> bool:
    return type(value) is int and 0 < value <= _SIGNED_BIGINT_MAXIMUM


def _mapping_rows(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{label} readback is invalid")
    rows = tuple(value)
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError(f"{label} readback is invalid")
    return rows


MySqlClientFinanceCompletionReadRepository = MySqlClientFinanceCompletionReadAdapter


__all__ = [
    "MySqlClientFinanceCompletionReadAdapter",
    "MySqlClientFinanceCompletionReadRepository",
]
