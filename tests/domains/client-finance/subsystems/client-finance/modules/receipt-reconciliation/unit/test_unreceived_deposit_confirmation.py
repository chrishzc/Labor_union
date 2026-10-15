"""Finance must positively read canonical history before confirming an unreceived deposit."""

import pytest

from domains.client_finance.reconciliation import UnreceivedDepositConfirmation
from infrastructure.mysql.client_receipt_reconciliation_repository import MySqlClientReceiptReconciliationRepository


@pytest.mark.parametrize("account_version", [None, 0, 3])
def test_absent_payment_roots_are_confirmed_without_fabricating_a_settlement(account_version):
    proof = UnreceivedDepositConfirmation("CASE", account_version, (), (), ())
    assert proof.confirmed
    assert proof.account_version is account_version
    assert not hasattr(proof, "contracted_amount_ntd")


@pytest.mark.parametrize("identities,events,entries", [(('deposit:1',), (), ()), ((), (8,), ()), ((), (), (9,))])
def test_any_formal_financial_history_prevents_the_absence_confirmation(identities, events, entries):
    assert not UnreceivedDepositConfirmation("CASE", 1, identities, events, entries).confirmed


@pytest.mark.parametrize("account_version", [-1, True, "0"])
def test_confirmation_rejects_unknown_or_invalid_source_versions(account_version):
    with pytest.raises(ValueError):
        UnreceivedDepositConfirmation("CASE", account_version, (), (), ())


class _Cursor:
    def __init__(self, account, roots):
        self.account, self.roots = account, roots
        self.statements = []

    def __enter__(self): return self
    def __exit__(self, *args): return False

    def execute(self, sql, params):
        assert params == ('CASE',)
        assert sql.startswith('SELECT ') and sql.endswith(' FOR UPDATE')
        self.statements.append(sql)

    def fetchone(self): return self.account

    def fetchall(self):
        for table, rows in self.roots.items():
            if f'FROM {table} ' in self.statements[-1]: return rows
        raise AssertionError(self.statements[-1])


class _Connection:
    def __init__(self, cursor): self._cursor = cursor
    def cursor(self): return self._cursor
    def commit(self): raise AssertionError('A financial confirmation Query must not commit')
    def rollback(self): raise AssertionError('The caller owns the transaction')


@pytest.mark.parametrize("existing_table", [None, 'client_obligations', 'client_obligation_events', 'client_ledger_entries'])
def test_financial_reader_locks_the_case_before_reading_all_history_and_never_writes(existing_table):
    roots = {'client_obligations': [], 'client_obligation_events': [], 'client_ledger_entries': []}
    if existing_table:
        roots[existing_table] = [{'obligation_identity': 'deposit:1'}] if existing_table == 'client_obligations' else [{'id': 9}]
    cursor = _Cursor({'aggregate_version': 4}, roots)
    proof = MySqlClientReceiptReconciliationRepository(_Connection(cursor)).query_unreceived_deposit('CASE')
    assert proof.case_no == 'CASE' and proof.account_version == 4
    assert proof.confirmed == (existing_table is None)
    assert 'FROM client_finance_accounts ' in cursor.statements[0]
    assert len(cursor.statements) == 4
