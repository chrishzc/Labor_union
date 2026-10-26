"""Borrow existing owner writers inside the caller's transaction; never commit or send."""
from dataclasses import replace

from domains.client_finance.obligation_planning import (
    ClientObligationActionKind, automatic_subsidy_return_plan, build_client_finance_terms_candidate,
)
from infrastructure.mysql.client_finance_terms_writer import (
    persist_client_finance_terms_impact, persist_subsidy_return_plan,
)
from infrastructure.mysql.order_terms_read_model import load_calculable_client_finance_facts, select_order
from subsystems.orders.terms_workflow import ClientFinanceImpactPersistenceCommand


def synchronize_client_charges(cursor, case_no, *, actor, key, correlation_id, source_family, source_id):
    order = select_order(cursor, case_no, lock=True)
    if str(order["status"]).startswith("歷史") or str(order["status"]) in ("訂單取消", "訂單完成"):
        # Historical/terminal amounts require their actual-service owner writer.
        cursor.execute("SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE", (case_no,))
        account = cursor.fetchone()
        if account is None:
            raise ValueError("client_finance_bootstrap_required")
        return int(account["aggregate_version"])
    facts, _ = load_calculable_client_finance_facts(cursor, order, lock=True)
    candidate = build_client_finance_terms_candidate(facts, f"{source_family}:{source_id}")
    if (all(action.action is ClientObligationActionKind.UNCHANGED for action in candidate.actions)
            and candidate.payment_terms == facts.payment_terms and candidate.subsidy_return_plan is None):
        return facts.account_version
    persist_client_finance_terms_impact(cursor, ClientFinanceImpactPersistenceCommand(
        candidate, key, actor, "系統依完整案件資料同步客戶應付", correlation_id, source_family, source_id,
    ))
    return candidate.resulting_account_version


def synchronize_terminal_subsidy_return(cursor, case_no, *, actor, key, correlation_id,
                                       source_family, source_id, advance_version=True):
    order = select_order(cursor, case_no, lock=True)
    if str(order['status']).startswith('歷史'):
        return
    if any(order.get(name) is None for name in ('start_date','service_days','service_hours_per_day','floor_fee')):
        return
    facts, source = load_calculable_client_finance_facts(cursor, order, lock=True,
        allow_planned=str(order['status']) not in ('訂單完成','訂單取消'))
    if facts is None:
        return  # Actual service facts must exist; planned/signed dates cannot authorize a refund.
    plan = automatic_subsidy_return_plan(facts, identity_status=source.identity_status,
        completed_on=max(day.service_date for day in facts.charge_days), existing_return_count=source.existing_subsidy_return_count)
    if plan is None:
        return
    candidate = replace(build_client_finance_terms_candidate(facts, f"{source_family}:{source_id}"),
                        actions=(), subsidy_return_plan=plan,
                        stage_plans=(),payment_terms=None,
                        resulting_account_version=facts.account_version + int(advance_version))
    command = ClientFinanceImpactPersistenceCommand(candidate, key, actor,
        "系統依案件資料同步應退補助", correlation_id, source_family, source_id)
    if advance_version:
        persist_client_finance_terms_impact(cursor, command)
    else:
        # The receipt writer already advanced the same account in this outer command.
        persist_subsidy_return_plan(cursor, command)
