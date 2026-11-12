"""Missing historical scenarios: no daily schedule, real original cash, explicit corrections."""
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
import os
import runpy

import pytest
from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
from infrastructure.mysql.historical_service_accounting_repository import MySqlHistoricalServiceAccountingRepository
from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.identities import ActorContext,CorrelationId,IdempotencyKey,ExpectedVersion
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.pricing_configuration import PricingConfigurationApplication
from subsystems.orders.terms_workflow import OrderTermsWorkflow
from subsystems.orders.historical_service_accounting_workflow import HistoricalServiceAccountingWorkflow,ConfirmHistoricalServiceDaysIntent,ApplyHistoricalServiceAccounting
from domains.orders.historical_service_accounting import HistoricalActualServiceDaysInput
from subsystems.finance_import.query import FinanceImportQueryService
from infrastructure.mysql.client_receipt_reconciliation_repository import MySqlClientReceiptReconciliationRepository
from api.dependencies.client_receipt_reconciliation import ClientReceiptReconciliationApplication
from subsystems.client_finance.reconciliation_workflow import ClientReconciliationWorkflow, ClientReconciliationApplyRequest, ReconciliationSelection
from infrastructure.mysql.client_difference_repository import MySqlClientDifferenceRepository
from subsystems.client_finance.difference_resolution import ClientDifferenceApplication, ClientDifferenceCommand
from infrastructure.mysql.payroll_amount_correction_repository import MySqlPayrollAmountRepository
from subsystems.payroll.amount_correction import PayrollAmountApplication, PayrollAmountCommand
from domains.client_finance.pricing_policy import HourlyRates

_scenario=runpy.run_path(str(Path(__file__).with_name('historical_accounting_scenarios.py')))
pytestmark=pytest.mark.skipif(os.getenv('ACCOUNTING_SYNC_MYSQL')!='1',reason='opt-in localhost historical scenarios')


@pytest.fixture(scope='module')
def scenarios():
    with _scenario['scenario_database']() as connection:
        cases={
            'shortened':_scenario['create_historical_scenario'](connection,'115990001'),
            'closed_fee':_scenario['create_historical_scenario'](connection,'115990002',paid=72000,waiting=1000),
            'subsidy_hours':_scenario['create_historical_scenario'](connection,'115990003',waiting=64000,excess_rate=400,subsidy_return=True),
            'subsidy_rates':_scenario['create_historical_scenario'](connection,'115990004',waiting=72000,subsidy_return=True),
            'legacy_identity':_scenario['create_historical_scenario'](connection,'115990008',legacy_identity=True),
            **{f'plan_{scheme}':_scenario['create_historical_scenario'](connection,f'11599000{index}',waiting=48000)
               for index,scheme in enumerate(('advance','split','direct'),5)},
        }
        yield connection,cases


def bank_candidate(connection, case):
    connection.commit()
    page=FinanceImportQueryService(connection).bank_transactions(bank=None,direction=None,status='all',start=None,end=None,search='',limit=50,before_row_id=None,row_id=case.bank_row_id)
    assert len(page['items'])==1
    return page['items'][0]


def reconcile_original_source(connection, case):
    row=bank_candidate(connection,case)
    assert row['status']=='pending'
    target=row['reconciliation_target']
    assert target is not None and target['case_no']==case.case_no
    repository=MySqlClientReceiptReconciliationRepository(connection)
    application=ClientReceiptReconciliationApplication(repository,ClientReconciliationWorkflow(repository,lambda:MySqlUnitOfWork(connection)))
    selection=ReconciliationSelection(case.case_no,None,(str(case.bank_row_id),),tuple(target['obligation_identities']))
    preview=application.preview(selection)
    assert preview.candidate.status.value=='exact'
    request=ClientReconciliationApplyRequest(selection,ExpectedVersion(preview.account_version),preview.fingerprint,
        IdempotencyKey(case.case_no+'-original-bank-reconcile'),ActorContext('synthetic'),'核銷原歷史流水',CorrelationId(case.case_no+'-original-bank-reconcile'))
    receipt=application.apply(request)
    assert application.apply(request)==receipt
    assert bank_candidate(connection,case)['status']=='posted'


def assert_original_cash_preserved(connection, case, before):
    after=_scenario['cash_snapshot'](connection,case)
    for name,rows in before.items():
        assert all(row in after[name] for row in rows),name


def assert_payroll_expected(connection, case, amount):
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting
    items,_=query_case_staff_accounting(connection,case.case_no)
    assert sum(item.expected_ntd for item in items if item.direction=='payable' and item.summary_included)==amount


def original_installments(connection, case):
    with connection.cursor() as cursor:
        cursor.execute("SELECT obligation_identity,obligation_type,due_date FROM client_obligations WHERE case_no=%s AND obligation_type IN ('deposit','first','second') AND status<>'cancelled' ORDER BY obligation_identity",(case.case_no,))
        return cursor.fetchall()


def assert_historical_service_preserved(connection, case):
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) n FROM staff_schedule WHERE case_no=%s',(case.case_no,))
        assert cursor.fetchone()['n']==0
        cursor.execute('SELECT status,actual_start_date,actual_end_date FROM orders WHERE case_no=%s',(case.case_no,))
        assert cursor.fetchone()=={'status':'歷史訂單－服務完成','actual_start_date':date(2025,1,2),'actual_end_date':date(2025,1,31)}


def test_fixtures_include_historical_bindings_original_cash_and_zero_daily_schedule(scenarios):
    connection,cases=scenarios
    for case in cases.values():
        from api.routes.finance_statement_workspace import _case_view
        assert _case_view(build_accounting_workspace(connection).query(case.case_no)).case_no==case.case_no
        facts=MySqlHistoricalServiceAccountingRepository(connection).load(case.case_no,for_update=False)
        assert facts.adoption_receipt_id>0 and facts.assignments
        assert facts.lifecycle_status.value=='歷史訂單－服務完成'
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) n FROM staff_schedule WHERE case_no=%s',(case.case_no,))
            assert cursor.fetchone()['n']==0
        cash=_scenario['cash_snapshot'](connection,case)
        assert cash['client_cash'] and cash['staff_cash']
        assert sum(row['amount_ntd'] for row in cash['client_cash'])==case.original_client_paid
        assert sum(row['amount_ntd'] for row in cash['staff_cash'])==case.original_staff_paid


def test_adoption_preserves_preexisting_obligation_with_a_legacy_identity(scenarios):
    connection,cases=scenarios;case=cases['legacy_identity']
    # An older root need not use today's generated identity. Adoption must not
    # turn the same evidenced assignment into a second service liability.
    with connection.cursor() as cursor:
        cursor.execute("SELECT obligation_identity FROM staff_obligations WHERE case_no=%s AND status<>'cancelled'",(case.case_no,))
        assert [row['obligation_identity'] for row in cursor.fetchall()]==[case.staff_obligation]


def test_historical_shortened_service_saves_comparison_without_overwriting_original_cash(scenarios):
    connection,cases=scenarios;case=cases['shortened']
    before=_scenario['cash_snapshot'](connection,case)
    installments=original_installments(connection,case)
    workflow=HistoricalServiceAccountingWorkflow(MySqlHistoricalServiceAccountingRepository(connection),lambda:MySqlUnitOfWork(connection))
    intent=ConfirmHistoricalServiceDaysIntent(case.case_no,(HistoricalActualServiceDaysInput(f'assignment:{case.assignment_id}',case.staff_id,20),))
    preview=workflow.preview(intent)
    request=ApplyHistoricalServiceAccounting(intent,preview.facts.lifecycle_version,preview.facts.historical_day_revision,
        preview.facts.client_finance_version,preview.facts.payroll_version,preview.fingerprint,
        IdempotencyKey('synthetic-historical-shortened'),ActorContext('synthetic'),'提早結束：確認實際二十天',CorrelationId('synthetic-historical-shortened'))
    receipt=workflow.apply(request)
    assert receipt.total_actual_service_days==20
    assert receipt.client_obligation_amount_ntd==48000
    assert receipt.staff_obligation_amount_ntd==48000
    assert _scenario['cash_snapshot'](connection,case)==before
    assert workflow.apply(request).total_actual_service_days==20
    # Historical day revisions are comparison facts; use the existing explicit
    # owner correction, then reconcile the already-imported source.
    client=ClientDifferenceApplication(MySqlClientDifferenceRepository(connection),lambda:MySqlUnitOfWork(connection))
    command=ClientDifferenceCommand(case.case_no,case.client_obligation,'manual_amount',48000,'依確認二十天更正原期款',client.query(case.case_no).version,case.case_no+'-client-correct','synthetic')
    client.apply(command)
    assert client.apply(command).version==command.expected_version+1
    payroll=PayrollAmountApplication(MySqlPayrollAmountRepository(connection),lambda:MySqlUnitOfWork(connection))
    staff_command=PayrollAmountCommand(case.case_no,case.staff_obligation,'manual_amount',48000,'依確認二十天更正原應付',payroll.query(case.case_no).version,case.case_no+'-staff-correct','synthetic')
    payroll.apply(staff_command)
    assert payroll.apply(staff_command).version==staff_command.expected_version+1
    assert_payroll_expected(connection,case,48000)
    assert_original_cash_preserved(connection,case,before)
    reconcile_original_source(connection,case)
    assert_original_cash_preserved(connection,case,before)
    assert original_installments(connection,case)==installments


def test_historical_closed_fee_formal_preview_does_not_require_daily_schedule(scenarios):
    connection,cases=scenarios;case=cases['closed_fee']
    before=_scenario['cash_snapshot'](connection,case)
    installments=original_installments(connection,case)
    repository=MySqlOrderTermsRepository(connection)
    terms=repository.load_for_query(case.case_no).registry.order.terms
    workflow=OrderTermsWorkflow(repository,lambda:MySqlUnitOfWork(connection),SystemBusinessClock())
    preview=workflow.preview(case.case_no,replace(terms,floor_fee=MoneyNTD(1000)),floor_fee_correction=True)
    assert preview.requires_formal_apply
    assert not preview.scheduling_replacement_required
    assert _scenario['cash_snapshot'](connection,case)==before
    from subsystems.orders.terms_workflow import OrderTermsApplyRequest
    request=OrderTermsApplyRequest(case.case_no,preview.after,ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version),ExpectedVersion(preview.client_finance_version),ExpectedVersion(preview.payroll_version),
        preview.fingerprint,IdempotencyKey(case.case_no+'-floor'),ActorContext('synthetic'),'結案漏填樓層費',CorrelationId(case.case_no+'-floor'),floor_fee_correction=True)
    # A new historical-volume revision invalidates the original Preview even
    # when the day count and downstream account versions happen to be equal.
    history=HistoricalServiceAccountingWorkflow(MySqlHistoricalServiceAccountingRepository(connection),lambda:MySqlUnitOfWork(connection))
    intent=ConfirmHistoricalServiceDaysIntent(case.case_no,(HistoricalActualServiceDaysInput(f'assignment:{case.assignment_id}',case.staff_id,30),))
    volume=history.preview(intent)
    history.apply(ApplyHistoricalServiceAccounting(intent,volume.facts.lifecycle_version,volume.facts.historical_day_revision,
        volume.facts.client_finance_version,volume.facts.payroll_version,volume.fingerprint,
        IdempotencyKey(case.case_no+'-confirm-days'),ActorContext('synthetic'),'確認原服務天數',CorrelationId(case.case_no+'-confirm-days')))
    from subsystems.orders.terms_workflow import TermsWorkflowError
    with pytest.raises(TermsWorkflowError) as stale:
        workflow.apply(request)
    assert stale.value.error.code=='stale_preview'
    preview=workflow.preview(case.case_no,preview.after,floor_fee_correction=True)
    request=replace(request,preview_fingerprint=preview.fingerprint)
    class FailingRepository(MySqlOrderTermsRepository):
        def persist_historical_correction(self,plan,command):
            super().persist_historical_correction(plan,command)
            raise RuntimeError('synthetic historical correction rollback')
    failure=OrderTermsWorkflow(FailingRepository(connection),lambda:MySqlUnitOfWork(connection),SystemBusinessClock())
    with pytest.raises(RuntimeError,match='synthetic historical correction rollback'):
        failure.apply(request)
    assert repository.load_for_query(case.case_no).registry.order.terms==terms
    assert _scenario['cash_snapshot'](connection,case)==before
    receipt=workflow.apply(request)
    assert workflow.apply(request)==receipt
    assert _scenario['cash_snapshot'](connection,case)==before
    assert_payroll_expected(connection,case,73000)
    reconcile_original_source(connection,case)
    assert_original_cash_preserved(connection,case,before)
    assert_historical_service_preserved(connection,case)
    assert original_installments(connection,case)==installments
    with pytest.raises(TermsWorkflowError):
        workflow.apply(replace(request,proposed_terms=replace(terms,floor_fee=MoneyNTD(1500))))
    next_terms=replace(terms,floor_fee=MoneyNTD(1500))
    next_preview=workflow.preview(case.case_no,next_terms,floor_fee_correction=True)
    next_request=replace(request,proposed_terms=next_terms,expected_order_version=ExpectedVersion(next_preview.order_version),
        expected_client_finance_version=ExpectedVersion(next_preview.client_finance_version),expected_payroll_version=ExpectedVersion(next_preview.payroll_version),
        preview_fingerprint=next_preview.fingerprint,idempotency_key=IdempotencyKey(case.case_no+'-floor-next'))
    workflow.apply(next_request)
    assert bank_candidate(connection,case)['status']=='posted'
    assert_payroll_expected(connection,case,73500)
    assert_original_cash_preserved(connection,case,before)


@pytest.mark.parametrize('has_original_deposit', [False, True])
def test_historical_social_floor_fee_is_read_back_as_deposit(scenarios, has_original_deposit, monkeypatch):
    from infrastructure.mysql.client_registry_query_repository import _finance_values
    from infrastructure.mysql import pricing_configuration_repository
    from subsystems.orders.terms_workflow import OrderTermsApplyRequest

    connection, _ = scenarios
    case = _scenario['create_historical_scenario'](
        connection, '115990011' if has_original_deposit else '115990010',
        paid=72000 if has_original_deposit else 0, waiting=1500,
        client_stage='deposit' if has_original_deposit else 'first',
    )
    if has_original_deposit:
        history = HistoricalServiceAccountingWorkflow(
            MySqlHistoricalServiceAccountingRepository(connection), lambda: MySqlUnitOfWork(connection),
        )
        intent = ConfirmHistoricalServiceDaysIntent(case.case_no, (
            HistoricalActualServiceDaysInput(f'assignment:{case.assignment_id}', case.staff_id, 20),
        ))
        volume = history.preview(intent)
        history.apply(ApplyHistoricalServiceAccounting(
            intent, volume.facts.lifecycle_version, volume.facts.historical_day_revision,
            volume.facts.client_finance_version, volume.facts.payroll_version, volume.fingerprint,
            IdempotencyKey(case.case_no+'-recorded-days'), ActorContext('synthetic'), '確認歷史服務天數',
            CorrelationId(case.case_no+'-recorded-days'),
        ))
    with connection.cursor() as cursor:
        cursor.execute("UPDATE clients SET identity_status='補助市民' WHERE case_no=%s", (case.case_no,))
        if not has_original_deposit:
            cursor.execute("UPDATE client_obligations SET status='cancelled',amount_due_ntd=0 WHERE obligation_identity=%s",
                           (case.client_obligation,))
            cursor.execute("UPDATE staff_obligations SET status='cancelled',amount_due_ntd=0 WHERE obligation_identity=%s",
                           (case.staff_obligation,))
    connection.commit()
    original_cash = _scenario['cash_snapshot'](connection, case)
    def snapshots():
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM historical_service_day_projections WHERE case_no=%s', (case.case_no,))
            service_volume = cursor.fetchone()
            cursor.execute('SELECT * FROM staff_obligations WHERE case_no=%s ORDER BY obligation_identity', (case.case_no,))
            return service_volume, cursor.fetchall()

    service_and_payables = snapshots()
    if not has_original_deposit:
        assert all(row['status'] == 'cancelled' for row in service_and_payables[1])

    def reject_combined_repricing(*args, **kwargs):
        pytest.fail('Customer deposit correction must not load Payroll or reconstruct historical hours')

    monkeypatch.setattr(pricing_configuration_repository, 'load_historical_pricing_facts', reject_combined_repricing)
    repository = MySqlOrderTermsRepository(connection)
    workflow = OrderTermsWorkflow(repository, lambda: MySqlUnitOfWork(connection), SystemBusinessClock())
    terms = repository.load_for_query(case.case_no).registry.order.terms

    for fee in (1200, 1500):
        expected_delta = fee * 20 // 30 if has_original_deposit else fee
        preview = workflow.preview(case.case_no, replace(terms, floor_fee=MoneyNTD(fee)), floor_fee_correction=True)
        assert preview.payroll_version is None
        request = OrderTermsApplyRequest(
            case.case_no, preview.after, ExpectedVersion(preview.order_version),
            ExpectedVersion(preview.scheduling_version), ExpectedVersion(preview.client_finance_version),
            None, preview.fingerprint,
            IdempotencyKey(f'{case.case_no}-fee-{fee}'), ActorContext('synthetic'),
            '補登樓層費', CorrelationId(f'{case.case_no}-fee-{fee}'), floor_fee_correction=True,
        )
        receipt = workflow.apply(request)
        assert receipt.payroll_version is None
        assert workflow.apply(request) == receipt
        assert _scenario['cash_snapshot'](connection, case) == original_cash
        assert snapshots() == service_and_payables
        status, code, values = _finance_values(connection, case.case_no)
        assert (status, code) == ('ready', None)
        assert values['deposit_amount_ntd'] == case.original_client_paid + expected_delta
        assert values['customer_balance_ntd'] == expected_delta
        with connection.cursor() as cursor:
            cursor.execute("SELECT obligation_identity,status,amount_due_ntd FROM client_obligations "
                           "WHERE case_no=%s AND obligation_type='deposit' AND status<>'cancelled'", (case.case_no,))
            (deposit,) = cursor.fetchall()
            if has_original_deposit:
                assert (deposit['obligation_identity'], deposit['status']) == (case.client_obligation, 'settled')
                cursor.execute("SELECT SUM(amount_due_ntd) AS amount FROM client_obligations "
                               "WHERE source_obligation_identity=%s AND status='open'", (case.client_obligation,))
                assert cursor.fetchone()['amount'] == expected_delta
            else:
                assert (deposit['status'], deposit['amount_due_ntd']) == ('open', expected_delta)

    if not has_original_deposit:
        reconcile_original_source(connection, case)
        status, code, values = _finance_values(connection, case.case_no)
        assert (status, code) == ('ready', None)
        assert values['deposit_amount_ntd'] == values['received_total_ntd'] == 1500
        assert values['customer_balance_ntd'] == 0
        assert snapshots() == service_and_payables
    assert_historical_service_preserved(connection, case)


def test_historical_subsidy_hours_formal_apply_preserves_original_cash(scenarios,monkeypatch):
    connection,cases=scenarios;case=cases['subsidy_hours']
    before=_scenario['cash_snapshot'](connection,case)
    installments=original_installments(connection,case)
    application=PricingConfigurationApplication(MySqlPricingConfigurationRepository(connection),lambda:MySqlUnitOfWork(connection))
    current,_=application.query_case(case.case_no)
    terms=replace(current.terms,subsidy_hours=Decimal(80))
    preview=application.preview_case(case.case_no,terms,current.revision)
    import infrastructure.mysql.pricing_configuration_repository as persistence
    real_persist=persistence.persist_historical_repricing
    def fail_after_amounts(*args,**kwargs):
        real_persist(*args,**kwargs)
        raise RuntimeError('synthetic historical pricing rollback')
    with monkeypatch.context() as patch:
        patch.setattr(persistence,'persist_historical_repricing',fail_after_amounts)
        with pytest.raises(RuntimeError,match='synthetic historical pricing rollback'):
            application.apply_case(case.case_no,terms,current.revision,preview.fingerprint,'synthetic','測試歷史補助上限更正','synthetic-history-cap')
    assert application.query_case(case.case_no)[0].revision==current.revision
    assert_payroll_expected(connection,case,92000)
    assert _scenario['cash_snapshot'](connection,case)==before
    version=application.apply_case(case.case_no,terms,current.revision,preview.fingerprint,'synthetic','測試歷史補助上限更正','synthetic-history-cap')
    assert application.apply_case(case.case_no,terms,current.revision,preview.fingerprint,'synthetic','測試歷史補助上限更正','synthetic-history-cap')==version
    assert application.query_case(case.case_no)[0].revision==version
    assert _scenario['cash_snapshot'](connection,case)==before
    # Different covered/excess rates make the hours change observable in money.
    assert_payroll_expected(connection,case,88000)
    reconcile_original_source(connection,case)
    assert_original_cash_preserved(connection,case,before)
    assert original_installments(connection,case)==installments
    assert_historical_service_preserved(connection,case)
    with connection.cursor() as cursor:
        cursor.execute("SELECT amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'",(case.case_no,))
        assert cursor.fetchone()['amount_due_ntd']==24000


def test_historical_subsidy_rates_reconcile_original_source(scenarios):
    connection,cases=scenarios;case=cases['subsidy_rates']
    before=_scenario['cash_snapshot'](connection,case)
    installments=original_installments(connection,case)
    application=PricingConfigurationApplication(MySqlPricingConfigurationRepository(connection),lambda:MySqlUnitOfWork(connection))
    current,_=application.query_case(case.case_no)
    terms=replace(current.terms,client=HourlyRates(400,400),payroll=HourlyRates(400,400))
    application.apply_case(case.case_no,terms,current.revision,None,'synthetic','歷史費率更正',case.case_no+'-rate')
    assert _scenario['cash_snapshot'](connection,case)==before
    assert_payroll_expected(connection,case,96000)
    reconcile_original_source(connection,case)
    assert_original_cash_preserved(connection,case,before)
    assert original_installments(connection,case)==installments
    assert_historical_service_preserved(connection,case)
    with connection.cursor() as cursor:
        cursor.execute("SELECT amount_due_ntd FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return'",(case.case_no,))
        assert cursor.fetchone()['amount_due_ntd']==16000


@pytest.mark.parametrize('scheme',('advance','split','direct'))
def test_historical_manual_plan_versions_preserve_money_and_original_bank_candidate(scenarios,scheme):
    connection,cases=scenarios;case=cases[f'plan_{scheme}']
    before=_scenario['cash_snapshot'](connection,case)
    workspace=build_accounting_workspace(connection)
    for version,plan in enumerate(('advance','split',scheme)):
        preview=workspace.preview_subsidy_plan(case.case_no,plan,version)
        assert _scenario['cash_snapshot'](connection,case)==before
        result=workspace.save_subsidy_plan(
            case.case_no,plan,version,f'{case.case_no}-plan-{version}','synthetic',
            preview_fingerprint=preview.fingerprint.value,
        )
        assert result.applied_version==version+1
        assert _scenario['cash_snapshot'](connection,case)==before
    assert_payroll_expected(connection,case,72000)
    reconcile_original_source(connection,case)
    assert_original_cash_preserved(connection,case,before)
