"""Actual HTTP/composition/application/UoW boundary with no project SQL."""
import ast
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymysql.err import OperationalError
import pytest

from api.dependencies.admin_auth import require_admin
from api.dependencies.finance_import import get_accounting_workspace
import api.routes.finance_statement_workspace as routes
from subsystems.finance_import.accounting_workspace import CaseAccounting
from subsystems.finance_import.case_manual_supplement import ManualSupplementResult
from subsystems.finance_import.case_manual_supplement_application import CaseManualSupplementApplication
from subsystems.finance_import.statement_archive import StatementCommandConflict
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork


def run_command(monkeypatch, failure=None):
    events=[];staged=[];observed=[]
    case=CaseAccounting('CASE','Synthetic',1000,300,None,None,0,(),(),(),())
    class Connection:
        def cursor(self):raise AssertionError('Project SQL including fake cursor SQL is forbidden')
        def begin(self):events.append('begin')
        def commit(self):
            events.append('commit')
            if failure in {'commit_transport','commit_and_rollback'}:raise OperationalError(2006,'synthetic commit acknowledgement unavailable')
        def rollback(self):
            events.append('rollback')
            if failure in {'commit_and_rollback','typed_and_rollback','view_and_rollback'}:
                raise OperationalError(2013,'synthetic rollback acknowledgement unavailable')
            staged.clear()
    connection=Connection()
    class Commands:
        def __init__(self,actual):assert actual is connection
        def execute(self,**command):
            events.append('command');observed.append(command);staged.append('source-and-owner-effects')
            if failure=='writer_runtime':raise RuntimeError('synthetic writer failure')
            if failure=='typed_and_rollback':raise StatementCommandConflict('idempotency_conflict')
            return ManualSupplementResult('CASE',9,41,'client_receipt','deposit:CASE',300,True)
    def query(case_no):
        assert case_no=='CASE' and events==['begin','command']
        events.append('query')
        if failure=='query_runtime':raise RuntimeError('synthetic query failure')
        return replace(case,case_no=None) if failure in {'typed_view','view_and_rollback'} else case
    original_view=routes._case_view
    def fixed_view(facts):events.append('typed_view');return original_view(facts)
    monkeypatch.setattr('subsystems.finance_import.case_manual_supplement.CaseManualSupplementService',Commands)
    monkeypatch.setattr(routes,'_case_view',fixed_view)
    app=FastAPI();app.include_router(routes.router)
    app.dependency_overrides[require_admin]=lambda:SimpleNamespace(id=1,username='synthetic')
    app.dependency_overrides[get_accounting_workspace]=lambda:SimpleNamespace(state=SimpleNamespace(connection=connection),query=query)
    with TestClient(app,raise_server_exceptions=False) as client:
        response=client.post('/cases/CASE/manual-supplement',headers={'Idempotency-Key':'original-key'},json={
            'bank':'sinopac','direction':'client_receipt','target_item':'deposit:CASE','amount_ntd':300,'transaction_date':'2026-11-06'})
    return response,events,staged,observed


def test_application_owns_begin_command_same_connection_query_typed_view_then_single_commit(monkeypatch):
    response,events,staged,observed=run_command(monkeypatch)
    assert response.status_code==200 and response.json()['data']['received_ntd']==300
    assert events==['begin','command','query','typed_view','commit']
    assert staged==['source-and-owner-effects'] and observed[0]['idempotency_key']=='original-key'
    assert observed[0]['actor']=='admin_user_id:1' and observed[0]['target_item']=='deposit:CASE'


@pytest.mark.parametrize('failure,status,events',[
    ('writer_runtime',500,['begin','command','rollback']),
    ('query_runtime',500,['begin','command','query','rollback']),
    ('typed_view',422,['begin','command','query','typed_view','rollback']),
])
def test_unexpected_writer_query_or_schema_failure_exits_the_original_uow_without_commit(monkeypatch,failure,status,events):
    response,actual,staged,observed=run_command(monkeypatch,failure)
    assert response.status_code==status and actual==events
    assert staged==[] and len(observed)==1
    # Staged port cleanup proves rollback dispatch; it does not establish
    # persistence or atomicity of a real MySQL connection.


def test_commit_acknowledgement_failure_does_not_retry_the_command_or_add_route_compensation(monkeypatch):
    response,events,_staged,observed=run_command(monkeypatch,'commit_transport')
    assert response.status_code==503 and response.json()['detail']['error']['code']=='accounting_unavailable'
    assert events==['begin','command','query','typed_view','commit','rollback'] and len(observed)==1
    # A transport failure during commit remains UNKNOWN in a real database.
    # One UoW rollback invocation is not proof that the commit did not occur.


def test_transport_and_application_keep_the_existing_transaction_layers_separate():
    root=Path(__file__).resolve().parents[6]
    route=ast.parse((root/'api/routes/finance_statement_workspace.py').read_text(encoding='utf-8'))
    command=next(node for node in route.body if isinstance(node,ast.FunctionDef) and node.name=='create_case_manual_supplement')
    assert not any(isinstance(node,ast.Attribute) and node.attr in {'begin','commit','rollback','connection'} for node in ast.walk(command))
    assert not any(isinstance(node,ast.Name) and node.id=='CaseManualSupplementService' for node in ast.walk(command))
    application=ast.parse((root/'subsystems/finance_import/case_manual_supplement_application.py').read_text(encoding='utf-8'))
    assert not any(isinstance(node,ast.ImportFrom) and node.module and node.module.startswith(('fastapi','infrastructure')) for node in ast.walk(application))


@pytest.mark.parametrize('explicit_cause',[False,True])
def test_uow_keeps_primary_identity_traceback_explicit_cause_and_detaches_secondary_context_cycle(explicit_cause):
    events=[];primary=StatementCommandConflict('idempotency_conflict');secondary=OperationalError(2013,'rollback unavailable')
    source_cause=RuntimeError('original owner storage mapping') if explicit_cause else None
    class Connection:
        def begin(self):events.append('begin')
        def rollback(self):events.append('rollback');raise secondary
    try:
        if explicit_cause:raise primary from source_cause
        raise primary
    except StatementCommandConflict as caught:
        original_tb=caught.__traceback__;original_suppressed=caught.__suppress_context__
        unit=MySqlUnitOfWork(Connection());unit.__enter__()
        assert unit.__exit__(type(caught),caught,original_tb) is False
        assert caught is primary and caught.__traceback__ is original_tb
        assert caught.__cause__ is source_cause and caught.__suppress_context__ is original_suppressed
        assert caught.__context__ is secondary and secondary.__context__ is None
        assert secondary.__cause__ is None
    assert events==['begin','rollback']


def test_uow_without_primary_still_propagates_rollback_failure():
    secondary=OperationalError(2013,'rollback unavailable');events=[]
    class Connection:
        def begin(self):events.append('begin')
        def rollback(self):events.append('rollback');raise secondary
    with pytest.raises(OperationalError) as failure:
        with MySqlUnitOfWork(Connection()):pass
    assert failure.value is secondary and events==['begin','rollback']


def test_uow_preserves_original_commit_failure_identity_when_rollback_also_fails():
    primary=OperationalError(2006,'commit acknowledgement unavailable');secondary=OperationalError(2013,'rollback unavailable')
    events=[]
    class Connection:
        def begin(self):events.append('begin')
        def commit(self):events.append('commit');raise primary
        def rollback(self):events.append('rollback');raise secondary
    with pytest.raises(OperationalError) as failure:
        with MySqlUnitOfWork(Connection()) as unit:unit.commit()
    assert failure.value is primary and primary.__context__ is secondary and secondary.__context__ is None
    assert events==['begin','commit','rollback']
    # Commit outcome is UNKNOWN; neither failed acknowledgement proves no DB effect.


@pytest.mark.parametrize('failure,status,code',[
    ('typed_and_rollback',409,'accounting_source_changed'),
    ('view_and_rollback',422,'invalid_statement_command'),
    ('commit_and_rollback',503,'accounting_unavailable'),
])
def test_http_keeps_the_primary_typed_failure_when_secondary_rollback_fails(monkeypatch,failure,status,code):
    response,events,_staged,observed=run_command(monkeypatch,failure)
    assert response.status_code==status and response.json()['detail']['error']['code']==code
    assert events.count('rollback')==1 and len(observed)==1
    assert events.count('commit')==(1 if failure=='commit_and_rollback' else 0)


@pytest.mark.parametrize('failure',[None,'command','query','readback'])
def test_application_can_run_directly_without_transport_and_rolls_back_each_failure_stage(failure):
    events=[];case=CaseAccounting('CASE','Synthetic',1000,300,None,None,0,(),(),(),())
    primary=RuntimeError('synthetic direct application failure')
    class Connection:
        def begin(self):events.append('begin')
        def commit(self):events.append('commit')
        def rollback(self):events.append('rollback')
    class Commands:
        def execute(self,**command):
            events.append('command');assert command['case_no']=='CASE'
            if failure=='command':raise primary
    def query(case_no):
        events.append('query');assert case_no=='CASE'
        if failure=='query':raise primary
        return case
    def readback(facts):
        events.append('readback');assert facts is case
        if failure=='readback':raise primary
        return 'rendered-original-case'
    application=CaseManualSupplementApplication(Commands(),query,lambda:MySqlUnitOfWork(Connection()))
    def execute():return application.execute(case_no='CASE',bank='sinopac',direction='client_receipt',target_item='deposit:CASE',
        amount_ntd=300,transaction_date='2026-11-06',reason='',idempotency_key='key',actor='admin_user_id:1',readback=readback)
    if failure is None:
        assert execute()=='rendered-original-case' and events==['begin','command','query','readback','commit']
    else:
        with pytest.raises(RuntimeError) as rejected:execute()
        assert rejected.value is primary and events[-1]=='rollback' and 'commit' not in events


@pytest.mark.parametrize('failure',[None,'query','build'])
def test_real_dependency_generator_closes_the_same_connection_used_by_command_query_and_uow(monkeypatch,failure):
    import api.dependencies.finance_import as dependencies
    import infrastructure.mysql.accounting_workspace_repository as workspace_repository
    events=[];case=CaseAccounting('CASE','Synthetic',1000,300,None,None,0,(),(),(),())
    class Connection:
        def cursor(self):raise AssertionError('Project SQL is forbidden')
        def begin(self):events.append('begin')
        def commit(self):events.append('commit')
        def rollback(self):events.append('rollback')
        def close(self):events.append('close')
    connection=Connection()
    def query(case_no):
        events.append('query');assert case_no=='CASE'
        if failure=='query':raise RuntimeError('synthetic query failure')
        return case
    workspace=SimpleNamespace(state=SimpleNamespace(connection=connection),query=query)
    def build(actual):
        assert actual is connection;events.append('build')
        if failure=='build':raise RuntimeError('synthetic composition failure')
        return workspace
    class Commands:
        def __init__(self,actual):assert actual is connection
        def execute(self,**command):events.append('command')
    monkeypatch.setattr(dependencies,'get_connection',lambda:connection)
    monkeypatch.setattr(workspace_repository,'build_accounting_workspace',build)
    monkeypatch.setattr('subsystems.finance_import.case_manual_supplement.CaseManualSupplementService',Commands)
    generator=dependencies.get_accounting_workspace()
    if failure=='build':
        with pytest.raises(RuntimeError):next(generator)
        assert events==['build','close']
        return
    try:
        actual_workspace=next(generator);assert actual_workspace is workspace
        application=dependencies.get_case_manual_supplement_application(actual_workspace)
        def execute():return application.execute(case_no='CASE',bank='sinopac',direction='client_receipt',target_item='deposit:CASE',
            amount_ntd=300,transaction_date='2026-11-06',reason='',idempotency_key='key',actor='admin_user_id:1',readback=lambda facts:facts)
        if failure=='query':
            with pytest.raises(RuntimeError):execute()
        else:assert execute() is case
    finally:generator.close()
    assert events==['build','begin','command','query','rollback' if failure else 'commit','close']
