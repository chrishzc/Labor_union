"""Static policy ordering only: project SQL, including fake SQL, is prohibited."""
import ast
from pathlib import Path


def test_government_blocker_explains_the_existing_period_entry():
    from subsystems.finance_import.case_manual_supplement import ManualSupplementBlocked
    failure=ManualSupplementBlocked("government_subsidy_period_selection_required")
    assert failure.error.message=="政府補助入款請從銀行對帳選取原政府流水，進入政府整期核對。"


def test_legacy_government_route_returns_typed_period_instruction_without_committing(monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api.routes.finance_statement_workspace as routes
    from api.dependencies.admin_auth import require_admin
    from api.dependencies.finance_import import get_accounting_workspace
    from subsystems.finance_import.case_manual_supplement import ManualSupplementBlocked
    calls=[]
    class Connection:
        def cursor(self):raise AssertionError("Project SQL is forbidden")
        def commit(self):calls.append("commit")
        def rollback(self):calls.append("rollback")
    class Service:
        def __init__(self,connection):pass
        def execute(self,**command):
            assert command["direction"]=="government_subsidy"
            raise ManualSupplementBlocked("government_subsidy_period_selection_required")
    def query(case_no):raise AssertionError("Rejected period selection must not return success")
    monkeypatch.setattr(routes,"CaseManualSupplementService",Service)
    app=FastAPI();app.include_router(routes.router)
    app.dependency_overrides[require_admin]=lambda:SimpleNamespace(id=1,username="synthetic")
    app.dependency_overrides[get_accounting_workspace]=lambda:SimpleNamespace(state=SimpleNamespace(connection=Connection()),query=query)
    with TestClient(app) as client:
        response=client.post("/cases/CASE/manual-supplement",headers={"Idempotency-Key":"legacy-key"},json={
            "bank":"taishin","direction":"government_subsidy","target_item":"government_subsidy",
            "amount_ntd":1000,"transaction_date":"2026-11-06"})
    assert response.status_code==422
    error=response.json()["detail"]["error"]
    assert error["code"]=="government_subsidy_period_selection_required"
    assert error["category"]=="domain_blocked"
    assert error["message"]=="政府補助入款請從銀行對帳選取原政府流水，進入政府整期核對。"
    assert calls==["rollback"]


def test_new_government_supplement_requires_original_period_owner_after_legacy_replay_before_writes():
    path=Path(__file__).resolve().parents[6]/"subsystems/finance_import/case_manual_supplement.py"
    module=ast.parse(path.read_text(encoding="utf-8"))
    service=next(node for node in module.body if isinstance(node,ast.ClassDef) and node.name=="CaseManualSupplementService")
    execute=next(node for node in service.body if isinstance(node,ast.FunctionDef) and node.name=="execute")
    transaction=next(node for node in execute.body if isinstance(node,ast.With))
    replay=next(i for i,node in enumerate(transaction.body) if isinstance(node,ast.If) and isinstance(node.test,ast.Name) and node.test.id=="existing")
    blocker=next(i for i,node in enumerate(transaction.body) if isinstance(node,ast.If)
        and any(isinstance(value,ast.Constant) and value.value=="government_subsidy_period_selection_required" for value in ast.walk(node)))
    target=next(i for i,node in enumerate(transaction.body) if any(isinstance(value,ast.Attribute) and value.attr=="lock_target" for value in ast.walk(node)))
    first_insert=next(i for i,node in enumerate(transaction.body) if any(isinstance(value,ast.Attribute)
        and value.attr=="append_source" for value in ast.walk(node)))
    assert replay < blocker < target < first_insert
    assert any(isinstance(value,ast.Raise) for value in ast.walk(transaction.body[blocker]))
    assert not any(isinstance(value,ast.Constant) and isinstance(value.value,str)
        and "INSERT INTO government_subsidy_period" in value.value for value in ast.walk(execute))
    adapter=ast.parse((path.parents[2]/"infrastructure/mysql/case_manual_supplement_source_store.py").read_text(encoding="utf-8"))
    store=next(node for node in adapter.body if isinstance(node,ast.ClassDef) and node.name=="_MySqlManualSupplementSourceSession")
    legacy=next(node for node in store.body if isinstance(node,ast.FunctionDef) and node.name=="load_replay_entries")
    assert any(isinstance(value,ast.Constant) and isinstance(value.value,str)
        and "FROM government_subsidy_period_entries" in value.value for value in ast.walk(legacy))
