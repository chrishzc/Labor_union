"""Borrow existing owner writers inside the caller's transaction; never commit or send."""
from domains.client_finance.obligation_planning import (
    ClientObligationActionKind, build_client_finance_terms_candidate,
)
from infrastructure.mysql.client_finance_terms_writer import (
    persist_client_finance_terms_impact,
)
from infrastructure.mysql.order_terms_read_model import load_calculable_client_finance_facts, select_order
from subsystems.orders.terms_workflow import ClientFinanceImpactPersistenceCommand


def synchronize_client_charges(cursor, case_no, *, actor, key, correlation_id, source_family, source_id):
    order = select_order(cursor, case_no, lock=True)
    from infrastructure.mysql.government_period_difference_repository import synchronize_government_case_amount
    synchronize_government_case_amount(cursor,case_no,key.value,actor.actor_id,'案件資料更新後重新計算政府補助')
    if str(order["status"]).startswith("歷史") or str(order["status"]) in ("訂單取消", "訂單完成"):
        # Historical/terminal amounts require their actual-service owner writer.
        cursor.execute("SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s FOR UPDATE", (case_no,))
        account = cursor.fetchone()
        if account is None:
            raise ValueError("client_finance_bootstrap_required")
        return int(account["aggregate_version"])
    facts, _ = load_calculable_client_finance_facts(cursor, order, lock=True)
    candidate = build_client_finance_terms_candidate(facts, f"{source_family}:{source_id}")
    if candidate.blockers:
        return facts.account_version  # Keep protected history; the case query exposes the conflict.
    if (all(action.action is ClientObligationActionKind.UNCHANGED for action in candidate.actions)
            and candidate.payment_terms == facts.payment_terms and candidate.subsidy_return_plan is None):
        synchronize_terminal_subsidy_return(cursor, case_no, actor=actor, key=key,
            correlation_id=correlation_id, source_family=source_family, source_id=source_id)
        cursor.execute('SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s', (case_no,))
        return int(cursor.fetchone()['aggregate_version'])
    persist_client_finance_terms_impact(cursor, ClientFinanceImpactPersistenceCommand(
        candidate, key, actor, "系統依完整案件資料同步客戶應付", correlation_id, source_family, source_id,
    ))
    synchronize_terminal_subsidy_return(cursor, case_no, actor=actor, key=key,
        correlation_id=correlation_id, source_family=source_family, source_id=source_id, advance_version=False)
    return candidate.resulting_account_version


def synchronize_terminal_subsidy_return(cursor, case_no, *, actor, key, correlation_id,
                                       source_family, source_id, advance_version=True):
    order = select_order(cursor, case_no, lock=True)
    if str(order['status']) not in ('訂單完成', '訂單取消', '歷史訂單－服務完成', '歷史訂單－帳務完成'):
        return
    from infrastructure.mysql.accounting_workspace_repository import MySqlAccountingWorkspaceState, query_subsidy_payable_handoff
    from infrastructure.mysql.subsidy_confirmation_repository import preview_manual_subsidy_plan, persist_confirmed_refund
    current = MySqlAccountingWorkspaceState(cursor.connection).subsidy_plan(case_no)
    scheme = current.selected_scheme or query_subsidy_payable_handoff(cursor.connection, case_no).scheme
    if scheme != 'advance':
        return
    preview = preview_manual_subsidy_plan(cursor.connection, case_no, scheme, current.version, for_update=True)
    if preview.blocker or preview.refund_plan is None:
        return
    persist_confirmed_refund(cursor.connection, case_no, preview.refund_plan, actor, key,
        correlation_id, str(source_id), advance_version=advance_version)
