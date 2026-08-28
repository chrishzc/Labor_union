"""
File: historical_baseline_client_finance_owner_adapter.py
Description: 以借用的 MySQL 連線讀取 Client Finance HCAT v2 根事實。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalBaselineOwnerRootDescriptor,
    HistoricalOrderIdentity,
)
from infrastructure.mysql.historical_client_finance_completion_read_adapter import (
    _CURRENT_CASE_READ_SQL,
    _ledger_row,
    _mapping_rows,
    _obligation_row,
    _readback,
)
from shared_kernel.validation import require_canonical_text
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerObservationReadback,
)
from subsystems.orders.historical_completion_oracle import (
    HistoricalSettlementReadback,
)


_CASE_NUMBER_MAXIMUM_LENGTH = 50
_IDENTITY_MAXIMUM_LENGTH = 191
_SIGNED_BIGINT_MAXIMUM = 9_223_372_036_854_775_807


_TERMS_READ_SQL = """
SELECT t.case_no AS terms_case_no,
       t.policy_version, t.client_hourly_rate_ntd, t.deposit_service_days,
       t.deposit_due_date, t.first_payment_due_date, t.second_payment_due_date,
       t.current_event_id AS terms_current_event_id,
       e.id AS terms_event_id, e.case_no AS terms_event_case_no,
       e.policy_version AS event_policy_version,
       e.client_hourly_rate_ntd AS event_client_hourly_rate_ntd,
       e.deposit_service_days AS event_deposit_service_days,
       e.deposit_due_date AS event_deposit_due_date,
       e.first_payment_due_date AS event_first_payment_due_date,
       e.second_payment_due_date AS event_second_payment_due_date,
       e.expected_account_version AS event_expected_account_version,
       e.source_event_identity AS terms_source_event_identity
FROM client_payment_terms t
JOIN client_payment_terms_events e ON e.id=t.current_event_id
WHERE t.case_no=%s
"""

_OBLIGATION_EVENTS_SQL = """
SELECT e.id AS obligation_event_id, e.obligation_identity,
       e.case_no AS obligation_event_case_no, e.obligation_type,
       e.direction AS event_direction, e.event_type,
       e.after_amount_ntd, e.after_due_date,
       e.source_event_identity, e.expected_account_version
FROM client_obligation_events e
WHERE e.case_no=%s ORDER BY e.id
"""

_BANK_FACT_SQL = """
SELECT l.id AS ledger_entry_id, l.case_no AS ledger_case_no,
       l.finance_import_row_id, l.entry_type,
       f.id AS bank_fact_id, f.direction AS bank_direction,
       f.reconciliation_status, f.reconciliation_reference
FROM client_ledger_entries l
JOIN finance_import_rows f ON f.id=l.finance_import_row_id
WHERE l.case_no=%s ORDER BY l.id
"""


_SUPPORTED_DESCRIPTORS = {
    (item.step, item.root_identity_kind): item
    for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.owner_domain == "client_finance"
}


class MySqlHistoricalBaselineClientFinanceOwnerAdapter:
    """Read Client Finance observations without owning transaction state."""

    owner_domain = "client_finance"

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def read_owner_observations(
        self,
        identity: HistoricalOrderIdentity,
        descriptor: HistoricalBaselineOwnerRootDescriptor,
        *,
        for_update: bool = False,
    ) -> HistoricalBaselineOwnerObservationReadback:
        """Read one adopted descriptor using the caller's connection and lock mode."""

        self._validate_request(identity, descriptor, for_update)
        if identity.order_identity != f"order:{identity.case_no}":
            return HistoricalBaselineOwnerObservationReadback(
                identity,
                (_unavailable(descriptor, identity.case_no, "client_finance_order_identity_mismatch"),),
            )
        try:
            readback, rows, account, events, bank_facts = self._read_case(identity.case_no, for_update=for_update)
            if descriptor.step == 7 and descriptor.root_identity_kind == "deposit_obligation":
                observations = self._deposit_obligation(
                    identity, descriptor, readback, rows, account, events, for_update
                )
            elif descriptor.step == 7 and descriptor.root_identity_kind == "ledger_allocation":
                observations = self._ledger_allocation(
                    identity, descriptor, readback, rows, account, events, bank_facts, for_update
                )
            elif descriptor.step == 7:
                observations = self._settlement(
                    identity, descriptor, readback, rows, account, events, bank_facts, for_update
                )
            else:
                observations = self._client_settlement(
                    identity, descriptor, readback, rows, account
                )
        except Exception:
            observations = (
                _unavailable(
                    descriptor,
                    identity.case_no,
                    f"client_finance_step_{descriptor.step}_{descriptor.root_identity_kind}_readback_unavailable",
                ),
            )
        return HistoricalBaselineOwnerObservationReadback(identity, tuple(observations))

    def load_completion_readback(
        self, case_no: str, *, for_update: bool = False
    ) -> HistoricalSettlementReadback | None:
        """Expose the same complete reducer used by the Step 11 observation."""

        require_canonical_text(case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        readback, _rows, _account, _events, _bank_facts = self._read_case(case_no, for_update=for_update)
        return readback

    @staticmethod
    def _validate_request(identity, descriptor, for_update) -> None:
        if not isinstance(identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline Client Finance identity is invalid")
        if not isinstance(descriptor, HistoricalBaselineOwnerRootDescriptor):
            raise TypeError("historical baseline Client Finance descriptor is invalid")
        if not isinstance(for_update, bool):
            raise TypeError("historical baseline Client Finance read mode is invalid")
        expected = _SUPPORTED_DESCRIPTORS.get(
            (descriptor.step, descriptor.root_identity_kind)
        )
        if expected is None or descriptor.canonical_tuple != expected.canonical_tuple:
            raise ValueError("historical_baseline_client_finance_descriptor_unsupported")

    def _read_case(
        self, case_no: str, *, for_update: bool
    ) -> tuple[HistoricalSettlementReadback | None, tuple[Mapping[str, Any], ...], Mapping[str, Any] | None, tuple[Mapping[str, Any], ...], tuple[Mapping[str, Any], ...]]:
        """Read one consistent case snapshot; all statements inherit lock mode."""

        require_canonical_text(case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_CURRENT_CASE_READ_SQL + suffix, (case_no, case_no, case_no))
            rows = _mapping_rows(cursor.fetchall(), "client finance current roots")
            cursor.execute(_OBLIGATION_EVENTS_SQL + suffix, (case_no,))
            events = _mapping_rows(cursor.fetchall(), "client finance obligation events")
            cursor.execute(_BANK_FACT_SQL + suffix, (case_no,))
            bank_facts = _mapping_rows(cursor.fetchall(), "client finance bank facts")

        account_rows = tuple(row for row in rows if row.get("row_kind") == "account")
        if any(
            row.get("row_kind") not in {"account", "obligation", "ledger"}
            for row in rows
        ):
            raise ValueError("client finance current roots contain an unknown row kind")
        if not account_rows:
            return None, rows, None, events, bank_facts
        if len(account_rows) != 1:
            raise ValueError("client finance account readback is ambiguous")
        account = account_rows[0]
        if account.get("account_case_no") != case_no:
            raise ValueError("client finance account case identity mismatch")
        obligation_rows = tuple(
            _obligation_row(row) for row in rows if row.get("row_kind") == "obligation"
        )
        ledger_rows = tuple(
            _ledger_row(row) for row in rows if row.get("row_kind") == "ledger"
        )
        readback = _readback(case_no, account, obligation_rows, ledger_rows)
        return readback, rows, account, events, bank_facts

    def _deposit_obligation(
        self, identity, descriptor, readback, rows, account, events, for_update
    ):
        if readback is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_deposit_obligation_missing"),)
        if not readback.readback_available or readback.integrity_blockers:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_deposit_obligation_integrity_invalid"),)
        terms = self._read_terms(identity.case_no, for_update=for_update)
        if terms is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_terms_missing"),)
        obligations = tuple(
            row for row in rows
            if row.get("row_kind") == "obligation"
            and row.get("obligation_type") == "deposit"
        )
        if len(obligations) != 1:
            return (_unavailable(
                descriptor,
                identity.case_no,
                "client_finance_step_7_deposit_obligation_ambiguous"
                if obligations else "client_finance_step_7_deposit_obligation_missing",
            ),)
        row = obligations[0]
        if not self._terms_exact(terms, account, identity.case_no):
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_terms_drift"),)
        if row.get("obligation_direction") != "receivable_from_client":
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_deposit_direction_invalid"),)
        event = _current_obligation_event(events, row, identity.case_no)
        if event is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_obligation_event_invalid"),)
        amount = _integer(row.get("obligation_amount_due_ntd"))
        contracted = _integer(row.get("obligation_contracted_amount_ntd"))
        projection_version = _integer(row.get("obligation_projection_version"))
        event_id = _integer(row.get("obligation_current_event_id"), positive=True)
        if (
            row.get("obligation_case_no") != identity.case_no
            or amount is None
            or contracted is None
            or projection_version is None
            or event_id is None
            or projection_version > _integer(account.get("account_aggregate_version"))
            or _integer(event.get("expected_account_version")) > projection_version
            or contracted <= 0
            or row.get("obligation_status") not in {"open", "settled"}
        ):
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_deposit_obligation_amount_drift"),)
        allocation_total = _deposit_allocation_total(rows, row.get("obligation_identity"))
        if allocation_total is None or allocation_total < 0 or allocation_total > contracted:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_deposit_allocation_invalid"),)
        terminal = readback.readback_available and not readback.integrity_blockers and row.get("obligation_status") == "settled" and allocation_total == contracted
        source_event = event["source_event_identity"]
        return (_available(
            descriptor,
            identity.case_no,
            str(row.get("obligation_identity")),
            source_event,
            projection_version,
            terminal,
        ),)

    def _ledger_allocation(self, identity, descriptor, readback, rows, account, events, bank_facts, for_update):
        if readback is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_ledger_allocation_missing"),)
        terms = self._read_terms(identity.case_no, for_update=for_update)
        if terms is None or not self._terms_exact(terms, account, identity.case_no):
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_terms_drift"),)
        if not readback.readback_available or readback.integrity_blockers:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_ledger_allocation_invalid"),)
        deposit = _deposit_row(rows)
        if deposit is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_deposit_obligation_missing"),)
        allocations = _allocation_rows(rows, deposit.get("obligation_identity"))
        if not allocations:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_ledger_allocation_missing"),)
        if _current_obligation_event(events, deposit, identity.case_no) is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_obligation_event_invalid"),)
        version = _integer(account.get("account_aggregate_version"))
        if version is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_account_version_invalid"),)
        event_ids = _source_vector(rows, deposit.get("obligation_identity"), events=events)
        if event_ids is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_ledger_source_invalid"),)
        root = _bounded_identity(
            f"client-finance-ledger-allocation:{identity.case_no}:{event_ids}"
        )
        source = _bounded_identity(
            f"client-finance-ledger-events:{identity.case_no}:{event_ids}"
        )
        if root is None or source is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_ledger_source_vector_too_large"),)
        deposit_total = _deposit_allocation_total(rows, deposit.get("obligation_identity"))
        contracted = _integer(deposit.get("obligation_contracted_amount_ntd"), positive=True)
        terminal = (
            deposit_total is not None
            and contracted is not None
            and deposit_total == contracted
            and _bank_receipts_exact(bank_facts, allocations, identity.case_no)
        )
        return (_available(descriptor, identity.case_no, root, source, version, terminal),)

    def _settlement(self, identity, descriptor, readback, rows, account, events, bank_facts, for_update):
        if readback is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_settlement_missing"),)
        terms = self._read_terms(identity.case_no, for_update=for_update)
        if terms is None or not self._terms_exact(terms, account, identity.case_no):
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_terms_drift"),)
        if not readback.readback_available or readback.integrity_blockers:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_settlement_invalid"),)
        deposit = _deposit_row(rows)
        if deposit is None or _current_obligation_event(events, deposit, identity.case_no) is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_obligation_event_invalid"),)
        allocations = _allocation_rows(rows, deposit.get("obligation_identity"))
        if not allocations or not _bank_receipts_exact(bank_facts, allocations, identity.case_no):
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_7_bank_fact_invalid"),)
        return (self._aggregate_observation(
            identity, descriptor, readback, rows, account,
            prefix="settlement",
            require_deposit=True,
            events=events,
        ),)

    def _client_settlement(self, identity, descriptor, readback, rows, account):
        if readback is None:
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_11_settlement_readback_unavailable"),)
        if (
            not readback.readback_available
            or readback.integrity_blockers
            or readback.open_obligation_count != 0
        ):
            return (_unavailable(descriptor, identity.case_no, "client_finance_step_11_settlement_not_terminal"),)
        return (self._aggregate_observation(
            identity, descriptor, readback, rows, account,
            prefix="client-settlement",
            require_deposit=False,
        ),)

    def _aggregate_observation(
        self, identity, descriptor, readback, rows, account, *, prefix, require_deposit, events=()
    ):
        if not require_deposit and (
            not isinstance(readback.settlement_lineage_identity, str)
            or not isinstance(readback.allocation_lineage_identity, str)
        ):
            return _unavailable(descriptor, identity.case_no, "client_finance_step_11_settlement_identity_missing")
        if not require_deposit:
            return _available(
                descriptor,
                identity.case_no,
                readback.settlement_lineage_identity,
                readback.allocation_lineage_identity,
                _integer(account.get("account_aggregate_version")),
                True,
            )
        version = _integer(account.get("account_aggregate_version"))
        vector = _source_vector(rows, events=events)
        if version is None or vector is None:
            return _unavailable(descriptor, identity.case_no, "client_finance_source_vector_invalid")
        if require_deposit:
            deposit = _deposit_row(rows)
            if deposit is None or deposit.get("obligation_status") != "settled":
                return _unavailable(descriptor, identity.case_no, "client_finance_step_7_deposit_not_settled")
        root = _bounded_identity(f"client-finance-{prefix}:{identity.case_no}:account-v{version}:{vector}")
        source = _bounded_identity(f"client-finance-source-events:{identity.case_no}:{vector}")
        if root is None or source is None:
            return _unavailable(descriptor, identity.case_no, "client_finance_source_vector_too_large")
        return _available(descriptor, identity.case_no, root, source, version, True)

    def _read_terms(self, case_no: str, *, for_update: bool) -> Mapping[str, Any] | None:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(_TERMS_READ_SQL + suffix, (case_no,))
            rows = _mapping_rows(cursor.fetchall(), "client finance payment terms")
        if len(rows) != 1:
            return None
        return rows[0]

    @staticmethod
    def _terms_exact(terms, account, case_no) -> bool:
        if terms.get("terms_case_no") != case_no or terms.get("terms_event_case_no") != case_no:
            return False
        event_id = _integer(terms.get("terms_event_id"), positive=True)
        current_id = _integer(terms.get("terms_current_event_id"), positive=True)
        account_version = _integer(account.get("account_aggregate_version"))
        expected_version = _integer(terms.get("event_expected_account_version"))
        if event_id is None or current_id != event_id or account_version is None or expected_version is None:
            return False
        if expected_version > account_version:
            return False
        if not isinstance(terms.get("terms_source_event_identity"), str):
            return False
        try:
            require_canonical_text(
                terms["terms_source_event_identity"],
                "client finance terms source event identity",
                _IDENTITY_MAXIMUM_LENGTH,
            )
        except (TypeError, ValueError):
            return False
        pairs = (
            ("policy_version", "event_policy_version"),
            ("client_hourly_rate_ntd", "event_client_hourly_rate_ntd"),
            ("deposit_service_days", "event_deposit_service_days"),
            ("deposit_due_date", "event_deposit_due_date"),
            ("first_payment_due_date", "event_first_payment_due_date"),
            ("second_payment_due_date", "event_second_payment_due_date"),
        )
        return all(terms.get(left) == terms.get(right) for left, right in pairs)


def _deposit_row(rows):
    values = tuple(
        row for row in rows
        if row.get("row_kind") == "obligation" and row.get("obligation_type") == "deposit"
    )
    return values[0] if len(values) == 1 else None


def _current_obligation_event(events, obligation, case_no):
    event_id = _integer(obligation.get("obligation_current_event_id"), positive=True)
    if event_id is None:
        return None
    matches = tuple(event for event in events if event.get("obligation_event_id") == event_id)
    if len(matches) != 1:
        return None
    event = matches[0]
    if (
        event.get("obligation_event_case_no") != case_no
        or event.get("obligation_identity") != obligation.get("obligation_identity")
        or event.get("obligation_type") != obligation.get("obligation_type")
        or event.get("event_direction") != obligation.get("obligation_direction")
        or event.get("after_amount_ntd") != obligation.get("obligation_contracted_amount_ntd")
        or _integer(event.get("expected_account_version")) is None
        or _integer(event.get("expected_account_version")) > _integer(obligation.get("obligation_projection_version"))
        or not isinstance(event.get("source_event_identity"), str)
    ):
        return None
    try:
        require_canonical_text(event["source_event_identity"], "client obligation source event", _IDENTITY_MAXIMUM_LENGTH)
    except (TypeError, ValueError):
        return None
    return event


def _bank_receipts_exact(bank_facts, allocations, case_no):
    by_ledger = {row.get("ledger_entry_id"): row for row in bank_facts}
    if len(by_ledger) != len(bank_facts):
        return False
    for allocation in allocations:
        ledger_id = allocation.get("ledger_entry_id")
        fact = by_ledger.get(ledger_id)
        if (
            fact is None
            or fact.get("ledger_case_no") != case_no
            or _integer(fact.get("finance_import_row_id"), positive=True) is None
            or fact.get("bank_fact_id") != fact.get("finance_import_row_id")
            or fact.get("entry_type") != "receipt"
            or fact.get("bank_direction") != "incoming"
            or fact.get("reconciliation_status") not in {"reconciled", "completed"}
        ):
            return False
    return True


def _allocation_rows(rows, obligation_identity):
    return tuple(
        row for row in rows
        if row.get("row_kind") == "ledger"
        and row.get("allocation_obligation_identity") == obligation_identity
    )


def _deposit_allocation_total(rows, obligation_identity):
    allocations = _allocation_rows(rows, obligation_identity)
    if not allocations:
        return 0
    values = []
    for row in allocations:
        amount = _integer(row.get("allocation_amount_ntd"), positive=True)
        if amount is None:
            return None
        sign = -1 if row.get("ledger_entry_type") in {
            "reversal",
            "refund_reversal",
            "subsidy_return_reversal",
            "subsidy_advance_reversal",
        } else 1
        values.append(sign * amount)
    return sum(values)


def _source_vector(rows, obligation_identity=None, *, events=()):
    identities: set[str] = set()
    event_sources = {
        event.get("obligation_event_id"): event.get("source_event_identity")
        for event in events
    }
    for row in rows:
        if row.get("row_kind") == "obligation":
            if obligation_identity is not None and row.get("obligation_identity") != obligation_identity:
                continue
            event_id = _integer(row.get("obligation_current_event_id"), positive=True)
            if event_id is None:
                return None
            source_identity = row.get("obligation_source_event_identity") or event_sources.get(event_id)
            if not isinstance(source_identity, str):
                source_identity = f"obligation-event:{event_id}"
            if _bounded_identity(source_identity) is None:
                return None
            identities.add(source_identity)
        elif row.get("row_kind") == "ledger":
            if obligation_identity is not None and row.get("allocation_obligation_identity") != obligation_identity:
                continue
            ledger_id = _integer(row.get("ledger_entry_id"), positive=True)
            if ledger_id is None:
                return None
            source_identity = row.get("ledger_source_event_identity")
            if not isinstance(source_identity, str):
                ordinal = _integer(row.get("allocation_ordinal"), positive=True)
                source_identity = (
                    f"ledger-entry:{ledger_id}:allocation:{ordinal}"
                    if ordinal is not None
                    else f"ledger-entry:{ledger_id}"
                )
            if _bounded_identity(source_identity) is None:
                return None
            identities.add(source_identity)
    if not identities:
        return None
    return "|".join(sorted(identities))


def _integer(value: Any, *, positive: bool = False) -> int | None:
    if type(value) is not int or value > _SIGNED_BIGINT_MAXIMUM:
        return None
    if value < (1 if positive else 0):
        return None
    return value


def _bounded_identity(value: str) -> str | None:
    try:
        require_canonical_text(value, "client finance owner identity", _IDENTITY_MAXIMUM_LENGTH)
    except (TypeError, ValueError):
        return None
    return value


def _available(descriptor, case_no, root_identity, source_event_identity, source_version, terminal):
    return HistoricalBaselineOwnerObservation(
        descriptor,
        root_identity,
        source_event_identity,
        source_version,
        terminal,
        None,
        case_no,
    )


def _unavailable(descriptor, case_no: str, code: str):
    require_canonical_text(code, "historical baseline Client Finance unavailable code", 500)
    return HistoricalBaselineOwnerObservation.unavailable(descriptor, code=code, case_no=case_no)


HistoricalBaselineClientFinanceOwnerAdapter = MySqlHistoricalBaselineClientFinanceOwnerAdapter
MySqlHistoricalBaselineOwnerClientFinanceAdapter = MySqlHistoricalBaselineClientFinanceOwnerAdapter


__all__ = [
    "HistoricalBaselineClientFinanceOwnerAdapter",
    "MySqlHistoricalBaselineClientFinanceOwnerAdapter",
    "MySqlHistoricalBaselineOwnerClientFinanceAdapter",
]
