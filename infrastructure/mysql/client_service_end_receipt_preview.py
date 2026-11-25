"""Client Finance read model for an explicitly confirmed late Sinopac receipt."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from collections.abc import Mapping
from typing import Any

from domains.client_finance.obligation_planning import (
    LateServiceEndReceiptBalance,
    _build_stage_plans,
    build_late_service_end_receipt_balance,
)
from domains.finance_import.cancellation_code import resolve_finance_cancellation_code
from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.client_payments_query_repository import (
    query_cancellation_accounting,
    query_case_net_cash,
)
from infrastructure.mysql.order_terms_read_model import (
    load_calculable_client_finance_facts,
    select_order,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.money import MoneyNTD
from subsystems.client_finance.virtual_account_resolution import resolve_client_virtual_account


@dataclass(frozen=True, slots=True)
class LateReceiptOpenBalance:
    identity: str
    obligation_type: str
    direction: str
    amount_ntd: int
    event_id: int


@dataclass(frozen=True, slots=True)
class ClientServiceEndReceiptPreview:
    row_id: int
    case_no: str
    transaction_date: date
    bank_amount_ntd: int
    service_due_ntd: int
    fee_ntd: int
    account_version: int
    balance: LateServiceEndReceiptBalance
    open_balances: tuple[LateReceiptOpenBalance, ...]
    fingerprint: PreviewFingerprint


def preview_client_service_end_receipt(
    connection: Any, *, row_id: int, case_no: str, lock: bool = False,
) -> ClientServiceEndReceiptPreview:
    """Resolve case, earned charges, and cash only; no mutation or auto-posting."""
    suffix = " FOR UPDATE" if lock else ""
    with connection.cursor() as cursor:
        order = select_order(cursor, case_no, lock=lock)
        cursor.execute(
            "SELECT aggregate_version FROM client_finance_accounts WHERE case_no=%s" + suffix,
            (case_no,),
        )
        account = cursor.fetchone()
        if account is None:
            raise ValueError("client_finance_bootstrap_required")
        cursor.execute(
            "SELECT format_id,direction,reconciliation_status,transaction_date,currency,"
            "credit,debit,bank_references,cancellation_code,"
            "(SELECT e.canonical_fact_version FROM finance_import_classification_events e "
            "WHERE e.finance_import_row_id=bank.id ORDER BY e.id DESC LIMIT 1) AS canonical_fact_version "
            "FROM finance_import_rows bank WHERE bank.id=%s" + suffix,
            (row_id,),
        )
        row = cursor.fetchone()
        if row is None or row["format_id"] != "sinopac" or row["direction"] != "incoming":
            raise ValueError("late_service_end_receipt_requires_sinopac_income")
        if row["reconciliation_status"] != "pending" or row["canonical_fact_version"] is None:
            raise ValueError("late_service_end_receipt_not_pending")
        transaction_date = row["transaction_date"]
        if not isinstance(transaction_date, date) or (
            row["currency"] is not None and str(row["currency"]).upper() not in {"TWD", "NTD"}
        ):
            raise ValueError("late_service_end_receipt_bank_facts_invalid")
        amount = Decimal(str(row["credit"] or 0))
        if not amount.is_finite() or amount <= 0 or amount != amount.to_integral_value() or row["debit"]:
            raise ValueError("late_service_end_receipt_bank_facts_invalid")
        references = row["bank_references"]
        if isinstance(references, (str, bytes)):
            references = json.loads(references)
        account_code = resolve_finance_cancellation_code({**row, "bank_references": references})["cancellation_code"]
        resolved = resolve_client_virtual_account(cursor, account_code)
        if resolved["result"] != "resolved" or resolved["case_no"] != case_no:
            raise ValueError("late_service_end_receipt_case_not_verified")
        service_due, fee, end_evidence = _terminal_charge_facts(connection, cursor, order, lock=lock)
        cursor.execute(
            "SELECT obligation_identity,obligation_type,direction,amount_due_ntd,current_event_id "
            "FROM client_obligations WHERE case_no=%s AND status='open' AND amount_due_ntd>0 "
            "AND obligation_type<>'subsidy_return' ORDER BY obligation_identity" + suffix,
            (case_no,),
        )
        open_balances = tuple(
            LateReceiptOpenBalance(
                str(item["obligation_identity"]), str(item["obligation_type"]), str(item["direction"]),
                int(item["amount_due_ntd"]), int(item["current_event_id"]),
            )
            for item in cursor.fetchall()
        )
        net_cash = query_case_net_cash(cursor, case_no)

    pending_refund = sum(i.amount_ntd for i in open_balances if i.direction == "payable_to_client")
    balance = build_late_service_end_receipt_balance(
        service_due=MoneyNTD(service_due), authorized_fee=MoneyNTD(fee), net_cash_before=MoneyNTD(net_cash),
        confirmed_bank_receipt=MoneyNTD(int(amount)), existing_pending_refund=MoneyNTD(pending_refund),
    )
    return ClientServiceEndReceiptPreview(
        row_id, case_no, transaction_date, int(amount), service_due, fee, int(account["aggregate_version"]),
        balance, open_balances, fingerprint_payload({
            "row_id": row_id, "case_no": case_no, "transaction_date": transaction_date.isoformat(),
            "canonical_fact_version": int(row["canonical_fact_version"]),
            "account_version": int(account["aggregate_version"]),
            "order_version": int(order["lifecycle_version"]), "service_due": service_due, "fee": fee,
            "end_evidence": end_evidence, "balance": asdict(balance),
            "open_balances": tuple(asdict(i) for i in open_balances),
        }),
    )


def _terminal_charge_facts(
    connection: Any, cursor: Any, order: Mapping[str, Any], *, lock: bool,
) -> tuple[int, int, str]:
    case_no = str(order["case_no"])
    status = str(order["status"])
    if status in {OrderLifecycleStatus.CANCELLED, OrderLifecycleStatus.ESTABLISHED_UNSERVED}:
        settlement = query_cancellation_accounting(connection, case_no)
        if settlement is None or settlement.service_due_ntd != 0:
            raise ValueError("late_service_end_receipt_cancellation_not_verified")
        return 0, settlement.fee_ntd, "active_zero_service_cancellation"

    if (status != OrderLifecycleStatus.COMPLETED
            or order.get("actual_start_date") is None or order.get("actual_end_date") is None):
        raise ValueError("late_service_end_receipt_completion_not_verified")
    cursor.execute(
        "SELECT receipt.id FROM order_terms_apply_receipts receipt "
        "JOIN order_terms_change_events event ON event.id=receipt.order_terms_event_id "
        "AND event.case_no=receipt.case_no "
        "JOIN scheduling_aggregates aggregate ON aggregate.case_no=receipt.case_no "
        "JOIN scheduling_generations generation ON generation.id=aggregate.effective_generation_id "
        "AND generation.case_no=receipt.case_no AND generation.generation_number=receipt.scheduling_generation "
        "WHERE receipt.case_no=%s AND receipt.lifecycle_status IN ('服務中','訂單完成') "
        "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(event.before_terms,'$.service_days')) AS UNSIGNED)>"
        "CAST(JSON_UNQUOTE(JSON_EXTRACT(event.after_terms,'$.service_days')) AS UNSIGNED) "
        "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(event.after_terms,'$.service_days')) AS UNSIGNED)=%s "
        "ORDER BY receipt.id DESC LIMIT 1",
        (case_no, order["service_days"]),
    )
    shortening = cursor.fetchone()
    if shortening is None:
        raise ValueError("late_service_end_receipt_shortening_not_verified")
    facts, _ = load_calculable_client_finance_facts(cursor, order, lock=lock, allow_planned=False)
    if (facts is None or len(facts.charge_days) != int(order["service_days"])
            or any(not order["actual_start_date"] <= day.service_date <= order["actual_end_date"]
                   for day in facts.charge_days)):
        raise ValueError("late_service_end_receipt_actual_service_not_verified")
    return sum(stage.amount.amount for stage in _build_stage_plans(facts)), 0, f"terms:{int(shortening['id'])}"
