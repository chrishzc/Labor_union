"""Focused guards for Task 97 scheduling and contract transaction boundaries."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from subsystems.scheduling import matching_communication_workflow as matching_communication


ROOT = Path(__file__).resolve().parents[1]


def _function_calls(path: str, symbol: str) -> set[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    found: set[str] = set()
    stack: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            stack.append(node.name)
            if ".".join(stack) == symbol:
                for call in ast.walk(node):
                    if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
                        found.add(call.func.attr)
            self.generic_visit(node)
            stack.pop()

    Visitor().visit(tree)
    return found


@pytest.mark.parametrize(
    ("path", "symbol"),
    (
        ("subsystems/scheduling/availability_lock_acquisition_workflow.py", "acquire_caregiver_availability_lock"),
        ("subsystems/scheduling/availability_lock_release_workflow.py", "release_caregiver_availability_lock"),
        ("subsystems/scheduling/candidate_contact_pool_workflow.py", "add_candidates"),
        ("subsystems/scheduling/candidate_contact_pool_workflow.py", "apply_manual_information_confirmation"),
        ("subsystems/scheduling/candidate_contact_pool_workflow.py", "send_information"),
        ("subsystems/scheduling/candidate_contact_pool_workflow.py", "record_willingness"),
        ("subsystems/scheduling/matching_communication_workflow.py", "send_matching_plan_information"),
        ("subsystems/scheduling/matching_communication_workflow.py", "record_matching_plan_willingness"),
        ("subsystems/scheduling/matching_communication_workflow.py", "send_matching_plan_resumes"),
        ("subsystems/scheduling/matching_communication_workflow.py", "cancel_matching_plan"),
        ("subsystems/scheduling/matching_plan_workflow.py", "create_matching_plan_version"),
        ("subsystems/contract_signing/client_contract_application.py", "ClientContractSigningApplication.record_manual_attestation"),
        ("subsystems/contract_signing/client_contract_application.py", "ClientContractSigningApplication._persist_sent_contract"),
        ("subsystems/contract_signing/client_contract_application.py", "ClientContractSigningApplication._persist_signed_return"),
        ("subsystems/contract_signing/staff_contract_application.py", "StaffContractSigningApplication.record_manual_attestation"),
        ("subsystems/contract_signing/staff_contract_application.py", "StaffContractSigningApplication._persist_sent_contract"),
        ("subsystems/contract_signing/staff_contract_application.py", "StaffContractSigningApplication._persist_signed_return"),
    ),
)
def test_recorded_mutation_symbols_do_not_own_commit(path: str, symbol: str) -> None:
    assert "commit" not in _function_calls(path, symbol)


def test_matching_contact_query_has_no_transaction_side_effect() -> None:
    calls = _function_calls(
        "subsystems/scheduling/matching_notification_application.py",
        "MatchingNotificationApplication.get_contact_state",
    )
    assert calls.isdisjoint({"commit", "rollback"})


class _Connection:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return object()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_matching_mutation_failure_rolls_back_once_without_commit(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(matching_communication, "get_connection", lambda: connection)

    with pytest.raises(RuntimeError, match="provider window"):
        matching_communication._run_in_application_uow(
            lambda _connection, _cursor: (_ for _ in ()).throw(RuntimeError("provider window"))
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed is True
