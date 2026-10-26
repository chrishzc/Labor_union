"""ADVREC: exact lineage, conflict, replay, atomic failure, and authenticated API."""

from copy import deepcopy
from dataclasses import asdict, replace
from datetime import date

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.subsidy_advance_settlement import get_advance_settlement_application
from api.routes.subsidy_advance_settlement import router
from domains.client_finance.subsidy_advance import SubsidyAdvanceFacts
from domains.client_finance.subsidy_advance_settlement import (
    AdvanceEntitlement, AdvanceGovernmentReceipt, AdvanceSettlementFacts, project_advance_settlement,
)
from shared_kernel.money import MoneyNTD
from infrastructure.mysql.subsidy_advance_settlement_repository import MySqlAdvanceSettlementRepository, _facts
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_finance.subsidy_advance_recovery import SubsidyAdvanceRecoveryTarget
from subsystems.client_finance.subsidy_advance_settlement import (
    AdvanceSettlementApplication, AdvanceSettlementCommand, AdvanceSettlementConflict,
)


def facts():
    return AdvanceSettlementFacts(
        10, 'TEST-001', '測試客戶', 12000, date(2026, 3, 15), date(2026, 1, 20), 3,
        1, 12000, 0, (AdvanceEntitlement(1, 20, 2, 5, 12000, 12000, True),),
        (AdvanceGovernmentReceipt(30, 40, 20, 12000, 0, date(2026, 4, 1), 50, True, 1),), 0, None,
    )


@pytest.mark.parametrize('change,expected,reason', [
    ({}, 'ready', None),
    ({'receipts': ()}, 'waiting_receipt', None),
    ({'entitlements': ()}, 'review_required', 'entitlement_not_unique'),
    ({'obligation_count': 2}, 'review_required', 'advance_obligation_not_unique'),
    ({'reversed_advance_ntd': 12000}, 'review_required', 'reversed_source'),
    ({'account_version': None}, 'review_required', 'owner_facts_incomplete'),
    ({'recovered_amount_ntd': 12000, 'recovered_allocation_id': 30}, 'recovered', None),
    ({'recovered_amount_ntd': 6000, 'recovered_allocation_id': 30}, 'review_required', 'recovery_mismatch'),
])
def test_owner_readback(change, expected, reason):
    row = project_advance_settlement(replace(facts(), **change))
    assert (row.status, row.review_reason) == (expected, reason)


@pytest.mark.parametrize('change,reason', [
    ({'amount_ntd': 6000}, 'amount_mismatch'),
    ({'source_outbox_id': None}, 'allocation_evidence_missing'),
    ({'evidence_matches': False}, 'allocation_evidence_missing'),
    ({'reversed_amount_ntd': 12000}, 'reversed_source'),
    ({'advance_target_count': 2}, 'receipt_not_unique'),
])
def test_receipt_must_exactly_prove_recovery(change, reason):
    current = facts()
    row = project_advance_settlement(replace(current, receipts=(replace(current.receipts[0], **change),)))
    assert (row.status, row.review_reason) == ('review_required', reason)


class Repository:
    def __init__(self):
        self.facts = facts()
        self.receipts = {}
        self.recovery_count = self.commit_count = 0
        self.fail_receipt = False

    def list_facts(self, after_id, search, limit):
        return (self.facts,) if after_id < self.facts.advance_id else ()

    def load(self, advance_id, *, lock=False):
        return self.facts if advance_id == self.facts.advance_id else None

    def load_receipt(self, key):
        return self.receipts.get(key)

    def recovery_repository(self):
        return self

    def find_target(self, event):
        return SubsidyAdvanceRecoveryTarget(
            f'client-ledger:{self.facts.advance_id}', MoneyNTD(self.facts.advance_amount_ntd),
            MoneyNTD(self.facts.recovered_amount_ntd),
            SubsidyAdvanceFacts(self.facts.case_no, self.facts.completed_on, MoneyNTD(12000), MoneyNTD(0)),
        )

    def save_recovery(self, event, recovery):
        self.facts = replace(self.facts, recovered_amount_ntd=recovery.amount.amount, recovered_allocation_id=30)
        self.recovery_count += 1
        return True

    def record_anomaly(self, event, reason):
        raise AssertionError('invalid candidates must not reach the existing writer')

    def save_receipt(self, command, command_hash, facts, result):
        if self.fail_receipt:
            raise RuntimeError('receipt failure')
        self.facts = replace(self.facts, account_version=result['account_version'])
        self.receipts[command.idempotency_key] = {'command_fingerprint': command_hash, 'result_snapshot': result}

    def __enter__(self):
        self.before = deepcopy((self.facts, self.receipts, self.recovery_count))
        self.committed = False
        return self

    def commit(self):
        self.committed = True
        self.commit_count += 1

    def __exit__(self, kind, error, traceback):
        if not self.committed:
            self.facts, self.receipts, self.recovery_count = self.before


def setup():
    repo = Repository()
    app = AdvanceSettlementApplication(repo, lambda: repo)
    preview = app.preview(10)
    command = AdvanceSettlementCommand(10, 3, 5, preview.preview_fingerprint, 'test:advance-10', 'admin', '核對政府入款證據')
    return repo, app, command


def test_apply_once_then_replay_original_receipt():
    repo, app, command = setup()
    first = app.apply(command)
    assert first == app.apply(command)
    assert (repo.recovery_count, repo.commit_count) == (1, 1)
    assert app.query()['rows'][0]['status'] == 'recovered'
    with pytest.raises(AdvanceSettlementConflict, match='idempotency_mismatch'):
        app.apply(replace(command, reason='不同說明'))


@pytest.mark.parametrize('change', [
    {'account_version': 4},
    {'entitlements': (replace(facts().entitlements[0], batch_version=6),)},
    {'receipts': (replace(facts().receipts[0], reversed_amount_ntd=12000),)},
    {'recovered_amount_ntd': 12000, 'recovered_allocation_id': 30},
])
def test_human_preview_cannot_overwrite_changed_facts(change):
    repo, app, command = setup()
    repo.facts = replace(repo.facts, **change)
    with pytest.raises(AdvanceSettlementConflict):
        app.apply(command)
    assert repo.recovery_count == 0 and repo.commit_count == 0


def test_receipt_failure_rolls_back_recovery():
    repo, app, command = setup()
    repo.fail_receipt = True
    with pytest.raises(RuntimeError, match='receipt failure'):
        app.apply(command)
    assert repo.facts.recovered_amount_ntd == 0
    assert repo.receipts == {} and repo.recovery_count == 0


def api_client(application):
    api = FastAPI()
    api.include_router(router)
    api.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(1, 'admin', '管理員', 'system_admin')
    api.dependency_overrides[get_advance_settlement_application] = lambda: application
    return api, TestClient(api)


def test_authenticated_history_remains_read_only_and_old_mutations_are_retired():
    repo, application, command = setup()
    api, client = api_client(application)
    base = '/api/v1/client-finance/subsidy-advance-recoveries'
    assert client.get(base).json()['data']['rows'][0]['status'] == 'ready'
    assert client.post(f'{base}/10/preview',json={}).status_code==410
    body = {key: value for key, value in asdict(command).items() if key in {
        'expected_account_version', 'expected_batch_version', 'preview_fingerprint', 'reason'}}
    response = client.post(f'{base}/10/apply', json=body, headers={'Idempotency-Key': command.idempotency_key})
    assert response.status_code == 410
    assert response.json()['detail']['error']['code']=='subsidy_period_recovery_required'
    assert client.get(base).json()['data']['rows'][0]['status'] == 'ready'
    assert client.post(f'{base}/10/apply', json=body, headers={'Idempotency-Key': command.idempotency_key}).json() == response.json()
    conflict = client.post(f'{base}/10/apply', json={**body, 'reason': '不同指令'}, headers={'Idempotency-Key': command.idempotency_key})
    assert conflict.status_code == 410
    assert repo.recovery_count==0 and repo.commit_count==0


def test_invalid_command_and_denied_admin_never_write():
    repo, application, command = setup()
    api, client = api_client(application)
    base = '/api/v1/client-finance/subsidy-advance-recoveries'
    assert client.post(f'{base}/10/apply', json={}, headers={'Idempotency-Key': 'invalid key'}).status_code == 410
    assert client.get(base + '?page_size=101').status_code == 422

    def denied():
        raise HTTPException(403, 'forbidden')

    api.dependency_overrides[require_system_admin] = denied
    assert client.get(base).status_code == 403
    assert client.post(f'{base}/10/preview').status_code == 403
    assert client.post(f'{base}/10/apply', json=asdict(command)).status_code == 403
    assert repo.recovery_count == 0


def stored_row():
    return dict(advance_id=10, case_no='TEST-001', client_name='測試客戶', advance_amount_ntd=12000,
                advanced_on=date(2026, 3, 15), actual_end_date=date(2026, 1, 20), account_version=3,
                obligation_identity='subsidy:10', advance_allocation_amount=12000,
                obligation_case_no='TEST-001', obligation_type='subsidy_return', direction='payable_to_client',
                link_id=1, claim_item_id=20, batch_id=2, batch_version=5, entitled_amount_ntd=12000,
                approved_amount=12000, claim_case_no='TEST-001', allocation_id=30, transaction_id=40,
                receipt_amount=12000, receipt_reversed=0, received_on=date(2026, 4, 1), source_outbox_id=50,
                payload_snapshot={'kind': 'receipt', 'transaction_id': 40, 'batch_id': 2,
                                  'allocations': [{'claim_item_id': 20, 'case_no': 'TEST-001', 'amount_ntd': 12000}]},
                advance_reversed=0, recovered_amount_ntd=0, recovered_allocation_id=None, advance_target_count=1)


def test_adapter_preserves_exact_lineage_and_rejects_fractional_money():
    stored = stored_row()
    assert _facts([stored, stored]) == facts()
    wrong_event = {**stored['payload_snapshot'], 'transaction_id': 999}
    assert project_advance_settlement(_facts([{**stored, 'payload_snapshot': wrong_event}])).status == 'review_required'
    with pytest.raises(ValueError, match='money_invalid'):
        _facts([{**stored, 'receipt_amount': '12000.50'}])


def test_adapter_writes_audit_and_bounded_outbox_key_without_hidden_commit():
    repo, app, command = setup()
    statements = []

    class Connection:
        rowcount = 1

        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params):
            statements.append((sql, params))

    command = replace(command, idempotency_key='a' * 191)
    result = dict(advance_id=10, case_no='TEST-001', recovered_amount_ntd=12000, account_version=4)
    MySqlAdvanceSettlementRepository(Connection()).save_receipt(command, 'b' * 64, facts(), result)
    assert len(statements) == 3
    assert len(statements[-1][1][1]) <= 191
    import json
    audit = json.loads(statements[-1][1][2])
    assert (audit['actor'], audit['source_outbox_id'], audit['government_allocation_id']) == ('admin', 50, 30)
