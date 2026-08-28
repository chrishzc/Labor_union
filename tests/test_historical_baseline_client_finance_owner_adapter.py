"""Client Finance HCAT owner adapter: locked, borrowed, exact readbacks."""

from __future__ import annotations

from datetime import date

import pytest

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalOrderIdentity,
)
from infrastructure.mysql.historical_baseline_client_finance_owner_adapter import (
    MySqlHistoricalBaselineClientFinanceOwnerAdapter,
)


IDENTITY = HistoricalOrderIdentity("order:CASE-1", "CASE-1")
DESCRIPTORS = {
    item.root_identity_kind: item
    for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if item.owner_domain == "client_finance"
}


class Cursor:
    def __init__(self, roots, terms, events, bank_facts):
        self.roots = roots
        self.terms = terms
        self.events = events
        self.bank_facts = bank_facts
        self.calls = []
        self._rows = ()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.calls.append((statement, parameters))
        if "FROM client_payment_terms" in statement:
            self._rows = self.terms
        elif "FROM client_obligation_events" in statement:
            self._rows = self.events
        elif "FROM client_ledger_entries l" in statement:
            self._rows = self.bank_facts
        else:
            self._rows = self.roots

    def fetchall(self):
        return self._rows


class Connection:
    def __init__(self, roots, terms, bank_facts=None):
        events = [
            {
                "obligation_event_id": row["obligation_current_event_id"],
                "obligation_identity": row["obligation_identity"],
                "obligation_event_case_no": "CASE-1",
                "obligation_type": row["obligation_type"],
                "event_direction": row["obligation_direction"],
                "event_type": "established",
                "after_amount_ntd": row["obligation_contracted_amount_ntd"],
                "after_due_date": date(2026, 8, 1),
                "source_event_identity": f"event:{row['obligation_current_event_id']}",
                "expected_account_version": 7,
            }
            for row in roots
            if row.get("row_kind") == "obligation"
        ]
        generated_bank_facts = [
            {
                "ledger_entry_id": row["ledger_entry_id"],
                "ledger_case_no": "CASE-1",
                "finance_import_row_id": row["ledger_entry_id"] + 1000,
                "entry_type": "receipt",
                "bank_fact_id": row["ledger_entry_id"] + 1000,
                "bank_direction": "incoming",
                "reconciliation_status": "reconciled",
                "reconciliation_reference": row["ledger_reconciliation_reference"],
            }
            for row in roots
            if row.get("row_kind") == "ledger"
        ]
        self.cursor_instance = Cursor(roots, terms, events, generated_bank_facts if bank_facts is None else bank_facts)
        self.commit_count = 0
        self.rollback_count = 0
        self.close_count = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_count += 1

    def rollback(self):
        self.rollback_count += 1

    def close(self):
        self.close_count += 1


def _account(version=7):
    return {"row_kind": "account", "account_case_no": "CASE-1", "account_aggregate_version": version}


def _obligation(identity="deposit:CASE-1", *, status="settled", amount=0, contracted=100):
    return {
        "row_kind": "obligation",
        "obligation_identity": identity,
        "obligation_case_no": "CASE-1",
        "obligation_type": "deposit" if identity.startswith("deposit") else "first",
        "obligation_direction": "receivable_from_client",
        "obligation_status": status,
        "obligation_amount_due_ntd": amount,
        "obligation_current_event_id": 11 if identity.startswith("deposit") else 12,
        "obligation_projection_version": 7,
        "obligation_contracted_amount_ntd": contracted,
    }


def _ledger(ledger_id, obligation_identity, amount, ordinal=1):
    return {
        "row_kind": "ledger",
        "account_case_no": "CASE-1",
        "ledger_entry_id": ledger_id,
        "ledger_entry_type": "receipt",
        "ledger_amount_ntd": amount,
        "ledger_occurred_on": date(2026, 8, 1),
        "ledger_reconciliation_reference": f"bank:{ledger_id}",
        "ledger_reversal_of_entry_id": None,
        "target_entry_id": None,
        "target_case_no": None,
        "target_entry_type": None,
        "target_amount_ntd": None,
        "target_reversal_of_entry_id": None,
        "allocation_obligation_identity": obligation_identity,
        "allocation_amount_ntd": amount,
        "allocation_ordinal": ordinal,
    }


def _terms(**changes):
    row = {
        "terms_case_no": "CASE-1",
        "policy_version": "policy-v1",
        "client_hourly_rate_ntd": 50,
        "deposit_service_days": 2,
        "deposit_due_date": date(2026, 8, 1),
        "first_payment_due_date": date(2026, 8, 2),
        "second_payment_due_date": None,
        "terms_current_event_id": 101,
        "terms_event_id": 101,
        "terms_event_case_no": "CASE-1",
        "event_policy_version": "policy-v1",
        "event_client_hourly_rate_ntd": 50,
        "event_deposit_service_days": 2,
        "event_deposit_due_date": date(2026, 8, 1),
        "event_first_payment_due_date": date(2026, 8, 2),
        "event_second_payment_due_date": None,
        "event_expected_account_version": 7,
        "terms_source_event_identity": "terms:101",
    }
    row.update(changes)
    return row


def _fixture(*, include_second=False, terms=None):
    roots = [_account(), _obligation(), _ledger(21, "deposit:CASE-1", 100)]
    if include_second:
        roots.extend([_obligation("first:CASE-1", contracted=50), _ledger(22, "first:CASE-1", 50)])
    return roots, [terms or _terms()]


@pytest.mark.parametrize("kind", ["deposit_obligation", "ledger_allocation", "settlement", "client_settlement"])
def test_each_descriptor_has_distinct_exact_owner_identity(kind):
    roots, terms = _fixture(include_second=True)
    connection = Connection(roots, terms)
    result = MySqlHistoricalBaselineClientFinanceOwnerAdapter(connection).read_owner_observations(
        IDENTITY, DESCRIPTORS[kind]
    )
    observation = result.observations[0]
    assert observation.available
    assert observation.terminal_result is True
    assert (
        observation.root_identity.startswith("client-finance-")
        or observation.root_identity == "deposit:CASE-1"
        or len(observation.root_identity) == 64
    )
    assert observation.source_event_identity
    assert observation.source_version == 7


def test_locked_reads_are_forwarded_and_connection_state_is_borrowed():
    roots, terms = _fixture()
    connection = Connection(roots, terms)
    MySqlHistoricalBaselineClientFinanceOwnerAdapter(connection).read_owner_observations(
        IDENTITY, DESCRIPTORS["deposit_obligation"], for_update=True
    )
    assert len(connection.cursor_instance.calls) == 4
    assert all("FOR UPDATE" in statement.upper() for statement, _ in connection.cursor_instance.calls)
    assert connection.commit_count == connection.rollback_count == connection.close_count == 0


def test_multiple_allocations_are_retained_in_source_vector():
    roots = [_account(), _obligation(), _ledger(21, "deposit:CASE-1", 60), _ledger(22, "deposit:CASE-1", 40, ordinal=2)]
    connection = Connection(roots, [_terms()])
    observation = MySqlHistoricalBaselineClientFinanceOwnerAdapter(connection).read_owner_observations(
        IDENTITY, DESCRIPTORS["ledger_allocation"]
    ).observations[0]
    assert observation.available
    assert "ledger-entry:21" in observation.source_event_identity
    assert "ledger-entry:22" in observation.source_event_identity


@pytest.mark.parametrize(
    ("kind", "roots", "terms", "expected"),
    [
        ("deposit_obligation", [], [_terms()], "client_finance_step_7_deposit_obligation_missing"),
        ("deposit_obligation", [_account(), _obligation(), _ledger(21, "deposit:CASE-1", 90)], [_terms()], "client_finance_step_7_deposit_obligation_integrity_invalid"),
        ("settlement", [_account(), _obligation(), _ledger(21, "deposit:CASE-1", 90)], [_terms()], "client_finance_step_7_settlement_invalid"),
        ("client_settlement", [_account(), _obligation(status="open", amount=100), _ledger(21, "deposit:CASE-1", 100)], [_terms()], "client_finance_step_11_settlement_not_terminal"),
    ],
)
def test_missing_stale_amount_drift_and_open_state_are_unavailable(kind, roots, terms, expected):
    observation = MySqlHistoricalBaselineClientFinanceOwnerAdapter(Connection(roots, terms)).read_owner_observations(
        IDENTITY, DESCRIPTORS[kind]
    ).observations[0]
    assert not observation.available
    assert observation.unavailable_code == expected


def test_terms_drift_is_unavailable():
    roots, terms = _fixture(terms=_terms(event_policy_version="policy-v2"))
    observation = MySqlHistoricalBaselineClientFinanceOwnerAdapter(Connection(roots, terms)).read_owner_observations(
        IDENTITY, DESCRIPTORS["deposit_obligation"]
    ).observations[0]
    assert observation.unavailable_code == "client_finance_step_7_terms_drift"


def test_deposit_direction_and_current_event_identity_are_authoritative():
    roots, terms = _fixture()
    roots[1]["obligation_direction"] = "payable_to_client"
    observation = MySqlHistoricalBaselineClientFinanceOwnerAdapter(Connection(roots, terms)).read_owner_observations(
        IDENTITY, DESCRIPTORS["deposit_obligation"]
    ).observations[0]
    assert observation.unavailable_code == "client_finance_step_7_deposit_direction_invalid"

    roots, terms = _fixture()
    connection = Connection(roots, terms)
    connection.cursor_instance.events[0]["source_event_identity"] = ""
    observation = MySqlHistoricalBaselineClientFinanceOwnerAdapter(connection).read_owner_observations(
        IDENTITY, DESCRIPTORS["deposit_obligation"]
    ).observations[0]
    assert observation.unavailable_code == "client_finance_step_7_obligation_event_invalid"


def test_projection_lineage_can_be_behind_account_but_partial_bank_receipt_is_not_terminal():
    roots, terms = _fixture()
    roots[1]["obligation_projection_version"] = 6
    connection = Connection(roots, terms)
    connection.cursor_instance.events[0]["expected_account_version"] = 6
    observation = MySqlHistoricalBaselineClientFinanceOwnerAdapter(connection).read_owner_observations(
        IDENTITY, DESCRIPTORS["deposit_obligation"]
    ).observations[0]
    assert observation.available and observation.terminal_result is True

    roots, terms = _fixture()
    roots[1]["obligation_status"] = "open"
    roots[1]["obligation_amount_due_ntd"] = 40
    roots[2]["ledger_amount_ntd"] = 60
    roots[2]["allocation_amount_ntd"] = 60
    observation = MySqlHistoricalBaselineClientFinanceOwnerAdapter(Connection(roots, terms)).read_owner_observations(
        IDENTITY, DESCRIPTORS["ledger_allocation"]
    ).observations[0]
    assert observation.available and observation.terminal_result is False


def test_ledger_requires_formal_incoming_bank_receipt():
    roots, terms = _fixture()
    observation = MySqlHistoricalBaselineClientFinanceOwnerAdapter(Connection(roots, terms, bank_facts=[])).read_owner_observations(
        IDENTITY, DESCRIPTORS["settlement"]
    ).observations[0]
    assert observation.unavailable_code == "client_finance_step_7_bank_fact_invalid"


def test_step_eleven_binds_reducer_lineage_identities_directly():
    roots, terms = _fixture(include_second=True)
    adapter = MySqlHistoricalBaselineClientFinanceOwnerAdapter(Connection(roots, terms))
    readback = adapter.load_completion_readback("CASE-1")
    observation = adapter.read_owner_observations(
        IDENTITY, DESCRIPTORS["client_settlement"]
    ).observations[0]
    assert readback is not None
    assert observation.root_identity == readback.settlement_lineage_identity
    assert observation.source_event_identity == readback.allocation_lineage_identity


def test_descriptor_dispatch_is_strict():
    roots, terms = _fixture()
    adapter = MySqlHistoricalBaselineClientFinanceOwnerAdapter(Connection(roots, terms))
    with pytest.raises(ValueError, match="descriptor_unsupported"):
        adapter.read_owner_observations(IDENTITY, next(item for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2 if item.owner_domain == "orders"))
