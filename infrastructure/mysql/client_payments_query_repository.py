"""MySQL adapter for the bounded Client Finance read model.

This adapter only reads canonical Client Finance roots.  It borrows the
request connection and never commits, rolls back, or opens a nested unit of
work.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator

from pymysql.err import OperationalError
from infrastructure.mysql.case_category_query import CASE_CATEGORY_SQL
from subsystems.client_finance.client_payments_query import FinanceCaseCategory

from subsystems.client_finance.client_payments_query import (
    ClientFinanceAllocationFact,
    ClientFinanceCaseQuery,
    ClientFinanceCaseSummary,
    ClientFinanceLedgerEntryFact,
    ClientFinanceObligationFact,
    ClientFinancePageQuery,
)


class ClientFinanceCaseNotFound(ValueError):
    """The requested case has no canonical Client Finance account."""


def query_case_payment_terms(connection, case_no):
    """Use formal terms to prove zero stages without creating ledger or obligation rows."""
    from decimal import Decimal
    from domains.client_finance.obligation_planning import confirmed_zero_payment_stages
    from domains.client_finance.pricing_policy import calculate_case_total_amount
    from infrastructure.mysql.order_terms_read_model import select_order, load_calculable_client_finance_facts
    from subsystems.client_finance.case_accounting_query import ClientCaseFunding, ClientCasePaymentTerms
    with connection.cursor() as cursor:
        order = select_order(cursor, case_no, lock=False)
        status = str(order['status'])
        if status.startswith('歷史'):
            # Historical obligations retain their original legal period grain;
            # do not require or manufacture the normal three-period schedule.
            return ClientCasePaymentTerms(historical_stages=True)
        if any(order.get(key) is None for key in
                ('start_date', 'service_days', 'service_hours_per_day', 'floor_fee', 'client_identity_status')):
            return ClientCasePaymentTerms()
        if (order['pricing_policy_id'] is None and order['pricing_override_event_id'] is None
                and order['client_identity_status'] not in {'一般市民', '非市民'}):
            return ClientCasePaymentTerms()
        cursor.execute('SELECT 1 FROM client_finance_accounts a JOIN client_payment_terms t ON t.case_no=a.case_no '
            'JOIN client_payment_terms_events e ON e.id=t.current_event_id WHERE a.case_no=%s', (case_no,))
        if cursor.fetchone() is None:
            return ClientCasePaymentTerms()
        facts, _ = load_calculable_client_finance_facts(cursor, order, lock=False,
            allow_planned=status not in ('訂單完成', '訂單取消'))
    if facts is None or not facts.charge_days:
        return ClientCasePaymentTerms()
    pricing = facts.pricing
    funding = None
    if pricing is not None:
        hours = Decimal(str(facts.service_hours_per_day))
        funding = ClientCaseFunding(case_no, facts.identity_status, hours * len(facts.charge_days),
            pricing.subsidy_hours, calculate_case_total_amount(pricing,
                tuple((hours, day.is_double_pay) for day in facts.charge_days), facts.floor_fee.amount),
            facts.existing_subsidy_return_count > 0)

    # Cancellation has separate actual-service terms. An incomplete service
    # schedule or inconsistent amounts cannot establish a zero stage.
    if status == '訂單取消' or len(facts.charge_days) != int(order['service_days']):
        return ClientCasePaymentTerms(funding)
    return ClientCasePaymentTerms(funding, confirmed_zero_payment_stages(facts))


class MySqlClientFinanceQueryRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def query_all(self) -> ClientFinancePageQuery:
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_CASE_SUMMARY_SQL)
            rows = cursor.fetchall()
        return ClientFinancePageQuery(
            tuple(_summary(row) for row in rows)
        )

    def query_categories(self) -> tuple[FinanceCaseCategory, ...]:
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute("SELECT o.case_no," + CASE_CATEGORY_SQL + " AS category "
                           "FROM orders o JOIN clients c ON c.id=o.client_id ORDER BY o.case_no")
            return tuple(FinanceCaseCategory(str(row["case_no"]), row["category"]) for row in cursor.fetchall())

    def query_case(self, case_no: str) -> ClientFinanceCaseQuery:
        normalized = _case_no(case_no)
        with _mysql_cursor(self._connection) as cursor:
            cursor.execute(_ACCOUNT_SQL, (normalized,))
            account = cursor.fetchone()
            if account is None:
                raise ClientFinanceCaseNotFound("client_finance_case_not_found")
            cursor.execute(_OBLIGATIONS_SQL, (normalized,))
            obligation_rows = cursor.fetchall()
            cursor.execute(_LEDGER_SQL, (normalized,))
            ledger_rows = cursor.fetchall()
        return ClientFinanceCaseQuery(
            normalized,
            str(_nonnegative(account["aggregate_version"], "aggregate_version")),
            tuple(_obligation(row) for row in obligation_rows),
            _ledger_entries(ledger_rows),
        )


def _case_no(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("client_finance_case_not_found")
    normalized = value.strip()
    if not normalized or len(normalized) > 50:
        raise ValueError("client_finance_case_not_found")
    return normalized


def _summary(row) -> ClientFinanceCaseSummary:
    outstanding = _nonnegative(row["open_receivable_amount_ntd"], "open_receivable_amount_ntd")
    has_receipts = int(row["net_receipt_amount_ntd"]) > 0 or int(row["historical_paid_count"]) > 0
    receipt_status = (
        "partially_received" if outstanding > 0 and has_receipts else
        "unpaid" if outstanding > 0 else
        "received" if has_receipts else
        "settled" if int(row["receivable_count"]) > 0 else "pending"
    )
    return ClientFinanceCaseSummary(
        str(row["case_no"]),
        str(_nonnegative(row["aggregate_version"], "aggregate_version")),
        _nonnegative(row["open_receivable_amount_ntd"], "open_receivable_amount_ntd"),
        _nonnegative(row["open_payable_amount_ntd"], "open_payable_amount_ntd"),
        _nonnegative(row["obligation_count"], "obligation_count"),
        _nonnegative(row["ledger_entry_count"], "ledger_entry_count"),
        _nonnegative(row["receipt_entry_count"], "receipt_entry_count"),
        receipt_status,
    )


def _obligation(row) -> ClientFinanceObligationFact:
    obligation_type = str(row["obligation_type"])
    direction = str(row["direction"])
    if obligation_type not in {
        "deposit", "first", "second", "refund", "subsidy_return", "adjustment"
    } or direction not in {"receivable_from_client", "payable_to_client"}:
        raise ValueError("client_finance_obligation_invalid")
    status = str(row["status"])
    if status not in {"open", "settled", "cancelled"}:
        raise ValueError("client_finance_obligation_invalid")
    return ClientFinanceObligationFact(
        str(row["obligation_identity"]),
        obligation_type,
        direction,
        _nonnegative(row["amount_due_ntd"], "amount_due_ntd"),
        _date_value(row["due_date"]),
        status,
        str(_nonnegative(row["projection_version"], "projection_version")),
    )


def _ledger_entries(rows) -> tuple[ClientFinanceLedgerEntryFact, ...]:
    entries: dict[int, ClientFinanceLedgerEntryFact] = {}
    allocations: dict[int, list[ClientFinanceAllocationFact]] = {}
    for row in rows:
        entry_id = _positive(row["entry_id"], "entry_id")
        entry_type = str(row["entry_type"])
        if entry_type not in {"receipt", "refund", "adjustment", "reversal", "subsidy_return", "subsidy_advance"}:
            raise ValueError("client_finance_ledger_entry_invalid")
        if entry_id not in entries:
            entries[entry_id] = ClientFinanceLedgerEntryFact(
                entry_id,
                entry_type,
                _positive(row["amount_ntd"], "amount_ntd"),
                _required_date(row["occurred_on"], "occurred_on"),
                str(row["reconciliation_reference"]),
                _optional_positive(row["reversal_of_entry_id"]),
                _datetime_value(row["created_at"]),
                (),
            )
        identity = row.get("allocation_obligation_identity")
        if identity is not None:
            allocations.setdefault(entry_id, []).append(
                ClientFinanceAllocationFact(
                    str(identity),
                    _positive(row["allocation_amount_ntd"], "allocation_amount_ntd"),
                )
            )
    return tuple(
        ClientFinanceLedgerEntryFact(
            entry.entry_id,
            entry.entry_type,
            entry.amount_ntd,
            entry.occurred_on,
            entry.reconciliation_reference,
            entry.reversal_of_entry_id,
            entry.created_at,
            tuple(allocations.get(entry_id, ())),
        )
        for entry_id, entry in entries.items()
    )


def _nonnegative(value, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"client_finance_{field}_invalid")
    result = int(value)
    if result < 0:
        raise ValueError(f"client_finance_{field}_invalid")
    return result


def _positive(value, field: str) -> int:
    result = _nonnegative(value, field)
    if result <= 0:
        raise ValueError(f"client_finance_{field}_invalid")
    return result


def _optional_positive(value):
    return None if value is None else _positive(value, "reversal_of_entry_id")


def _date_value(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _required_date(value, field: str) -> date:
    result = _date_value(value)
    if result is None:
        raise ValueError(f"client_finance_{field}_invalid")
    return result


def _datetime_value(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


@contextmanager
def _mysql_cursor(connection) -> Iterator[object]:
    try:
        with connection.cursor() as cursor:
            yield cursor
    except OperationalError:
        raise


_CASE_SUMMARY_SQL = """
SELECT account.case_no, account.aggregate_version,
       COALESCE(SUM(CASE WHEN obligation.direction='receivable_from_client'
                         AND obligation.status='open'
                         AND historical.obligation_identity IS NULL
                        THEN obligation.amount_due_ntd ELSE 0 END), 0)
           AS open_receivable_amount_ntd,
       COALESCE(SUM(CASE WHEN obligation.direction='payable_to_client'
                         AND obligation.status='open'
                         AND historical.obligation_identity IS NULL
                        THEN obligation.amount_due_ntd ELSE 0 END), 0)
           AS open_payable_amount_ntd,
       COUNT(DISTINCT obligation.obligation_identity) AS obligation_count,
       (SELECT COUNT(*) FROM client_ledger_entries ledger
         WHERE ledger.case_no=account.case_no) AS ledger_entry_count,
       (SELECT COUNT(*) FROM client_ledger_entries receipt
         WHERE receipt.case_no=account.case_no
           AND receipt.entry_type='receipt') AS receipt_entry_count,
       COUNT(CASE WHEN obligation.direction='receivable_from_client'
                   AND obligation.status<>'cancelled' THEN 1 END) AS receivable_count,
       COUNT(CASE WHEN obligation.direction='receivable_from_client'
                   AND obligation.status<>'cancelled'
                   AND historical.confirmation_kind='paid' THEN 1 END) AS historical_paid_count,
       COALESCE((SELECT SUM(CASE WHEN ledger.entry_type='receipt' THEN ledger.amount_ntd
                                WHEN ledger.entry_type='reversal' AND target.entry_type='receipt' THEN -ledger.amount_ntd
                                ELSE 0 END)
          FROM client_ledger_entries ledger
          LEFT JOIN client_ledger_entries target ON target.id=ledger.reversal_of_entry_id AND target.case_no=ledger.case_no
         WHERE ledger.case_no=account.case_no),0) AS net_receipt_amount_ntd
FROM client_finance_accounts account
LEFT JOIN client_obligations obligation
       ON obligation.case_no=account.case_no
LEFT JOIN historical_client_payment_projections historical
       ON historical.obligation_identity=obligation.obligation_identity
      AND historical.amount_snapshot_ntd=obligation.amount_due_ntd
      AND historical.obligation_projection_version=obligation.projection_version
GROUP BY account.case_no, account.aggregate_version
ORDER BY account.case_no
"""

_ACCOUNT_SQL = (
    "SELECT case_no,aggregate_version FROM client_finance_accounts WHERE case_no=%s"
)
_OBLIGATIONS_SQL = (
    "SELECT obligation_identity,obligation_type,direction,amount_due_ntd,due_date,"
    "status,projection_version FROM client_obligations "
    "WHERE case_no=%s ORDER BY obligation_identity"
)
_LEDGER_SQL = (
    "SELECT ledger.id AS entry_id,ledger.entry_type,ledger.amount_ntd,"
    "ledger.occurred_on,ledger.reconciliation_reference,"
    "ledger.reversal_of_entry_id,ledger.created_at,"
    "allocation.obligation_identity AS allocation_obligation_identity,"
    "allocation.amount_ntd AS allocation_amount_ntd "
    "FROM client_ledger_entries ledger LEFT JOIN "
    "client_ledger_obligation_allocations allocation "
    "ON allocation.ledger_entry_id=ledger.id WHERE ledger.case_no=%s "
    "ORDER BY ledger.occurred_on,ledger.id,allocation.allocation_ordinal"
)


__all__ = [
    "ClientFinanceCaseNotFound",
    "MySqlClientFinanceQueryRepository",
]


def query_case_net_cash(cursor, case_no):
    cursor.execute(
        "SELECT COALESCE(SUM(CASE "
        "WHEN entry.entry_type='receipt' THEN entry.amount_ntd "
        "WHEN entry.entry_type='refund' THEN -entry.amount_ntd "
        "WHEN entry.entry_type='reversal' AND original.entry_type='receipt' THEN -entry.amount_ntd "
        "WHEN entry.entry_type='reversal' AND original.entry_type='refund' THEN entry.amount_ntd ELSE 0 END),0) AS amount "
        "FROM client_ledger_entries entry LEFT JOIN client_ledger_entries original "
        "ON original.id=entry.reversal_of_entry_id WHERE entry.case_no=%s",
        (case_no,),
    )
    return int(cursor.fetchone()["amount"])


CANCELLATION_ALLOCATED_CASH_SQL = (
    "SELECT entry.case_no,entry.id,entry.created_at,a.obligation_identity,original.id AS original_id,"
    "CASE WHEN entry.entry_type='receipt' OR original.entry_type='refund' THEN a.amount_ntd "
    "WHEN entry.entry_type='refund' OR original.entry_type='receipt' THEN -a.amount_ntd "
    "ELSE 0 END AS cash_delta "
    "FROM client_ledger_obligation_allocations a JOIN client_ledger_entries entry ON entry.id=a.ledger_entry_id "
    "LEFT JOIN client_ledger_entries original ON original.id=entry.reversal_of_entry_id AND entry.entry_type='reversal' "
    "WHERE entry.entry_type IN ('receipt','refund','reversal') "
    "UNION ALL SELECT entry.case_no,entry.id,entry.created_at,NULL,original.id,"
    "CASE WHEN original.entry_type='receipt' THEN -entry.amount_ntd ELSE entry.amount_ntd END "
    "FROM client_ledger_entries entry JOIN client_ledger_entries original ON original.id=entry.reversal_of_entry_id "
    "WHERE entry.entry_type='reversal' AND original.entry_type IN ('receipt','refund')"
)
_CANCELLATION_CASH_CUTOFF = "CAST(JSON_UNQUOTE(JSON_EXTRACT(receipt.result_snapshot,'$.cancellation_settlement.cash_entry_id')) AS UNSIGNED)"
CANCELLATION_CASH_JOIN = (
    f"entry.case_no=receipt.case_no AND entry.id>{_CANCELLATION_CASH_CUTOFF} AND ("
    "(entry.obligation_identity=JSON_UNQUOTE(JSON_EXTRACT(receipt.result_snapshot,'$.cancellation_settlement.obligation_identity')) "
    f"AND (entry.original_id IS NULL OR entry.original_id>{_CANCELLATION_CASH_CUTOFF})) OR "
    # A reversal of an original cash entry adjusts the latest baseline that included it.
    f"(entry.obligation_identity IS NULL AND entry.original_id<={_CANCELLATION_CASH_CUTOFF} AND NOT EXISTS ("
    "SELECT 1 FROM client_finance_apply_receipts later WHERE later.case_no=receipt.case_no AND later.id>receipt.id "
    "AND CAST(JSON_UNQUOTE(JSON_EXTRACT(later.result_snapshot,'$.cancellation_settlement.cash_entry_id')) AS UNSIGNED)<entry.id)))"
)


def query_cancellation_accounting(connection, case_no, *, cancellation_event_id=None):
    from subsystems.client_finance.case_accounting_query import ClientCancellationAccounting
    from domains.client_finance.obligation_planning import cancellation_fee_collected
    from datetime import date
    import json

    event_filter = (
        "AND EXISTS (SELECT 1 FROM order_lifecycle_control_state state "
        "JOIN order_cancellation_apply_receipts receipt ON receipt.case_no=state.case_no "
        "AND receipt.cancellation_control_event_id=state.current_event_id "
        "WHERE state.case_no=finance.case_no AND state.control_type='cancellation' "
        "AND state.control_key='order_cancelled' AND state.state='active' "
        "AND receipt.cancellation_event_id=JSON_EXTRACT(finance.result_snapshot,'$.cancellation_settlement.cancellation_event_id')) "
    )
    params = (case_no,)
    if cancellation_event_id is not None:
        event_filter = "AND JSON_EXTRACT(result_snapshot, '$.cancellation_settlement.cancellation_event_id')=%s "
        params = (case_no, cancellation_event_id)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, JSON_EXTRACT(result_snapshot, '$.cancellation_settlement') AS settlement "
            "FROM client_finance_apply_receipts finance WHERE case_no=%s "
            "AND JSON_CONTAINS_PATH(result_snapshot, 'one', '$.cancellation_settlement') "
            + event_filter + "ORDER BY resulting_account_version DESC, id DESC LIMIT 1",
            params,
        )
        row = cursor.fetchone()
    if row is None:
        return None
    payload = row["settlement"]
    facts = json.loads(payload) if isinstance(payload, (str, bytes)) else payload
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COALESCE(SUM(entry.cash_delta),0) AS amount FROM client_finance_apply_receipts receipt "
            f"LEFT JOIN ({CANCELLATION_ALLOCATED_CASH_SQL}) entry ON {CANCELLATION_CASH_JOIN} "
            "WHERE receipt.id=%s", (row["id"],),
        )
        current_cash = facts["net_received_ntd"] + int(cursor.fetchone()["amount"])
    current_fee_received = cancellation_fee_collected(facts["fee_ntd"], facts["service_due_ntd"], current_cash)
    bank_refunded = transfer_fee = None
    if facts["refund_due_ntd"] and facts["obligation_identity"]:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT a.amount_ntd AS allocated, entry.amount_ntd AS bank_amount, entry.entry_type, "
                "(SELECT SUM(other.amount_ntd) FROM client_ledger_obligation_allocations other "
                "WHERE other.ledger_entry_id=entry.id) AS total_allocated "
                "FROM client_ledger_obligation_allocations a JOIN client_ledger_entries entry ON entry.id=a.ledger_entry_id "
                "LEFT JOIN client_ledger_entries original ON original.id=entry.reversal_of_entry_id "
                "WHERE a.obligation_identity=%s AND (entry.entry_type='refund' "
                "OR (entry.entry_type='reversal' AND original.entry_type='refund'))",
                (facts["obligation_identity"],),
            )
            bank_refunded = transfer_fee = 0
            for entry in cursor.fetchall():
                gross = int(entry["allocated"])
                total = int(entry["total_allocated"])
                fee = max(0, total - int(entry["bank_amount"]))
                if fee and total != gross:
                    bank_refunded = transfer_fee = None
                    break
                sign = -1 if entry["entry_type"] == "reversal" else 1
                bank_refunded += sign * (gross - fee)
                transfer_fee += sign * fee
    return ClientCancellationAccounting(
        date.fromisoformat(facts["processed_on"]), facts["service_due_ntd"], facts["fee_ntd"],
        facts["net_received_ntd"], current_fee_received, facts["refund_due_ntd"],
        facts["additional_charge_due_ntd"], facts["obligation_identity"], bank_refunded, transfer_fee,
        max(0, facts["service_due_ntd"] - current_cash), facts["fee_ntd"] - current_fee_received,
    )


def query_case_accounting(connection, case_no, *, for_update=False):
    """Project original obligation amounts and effective cash allocations only."""
    from subsystems.client_finance.case_accounting_query import (
        ClientAccountingItem, ClientAccountingTransaction,
    )
    lock = " FOR UPDATE" if for_update else ""
    with connection.cursor() as cursor:
        if for_update:
            cursor.execute("SELECT case_no FROM client_finance_accounts WHERE case_no=%s FOR UPDATE", (case_no,))
            cursor.fetchall()
            cursor.execute("SELECT obligation_identity FROM client_obligations WHERE case_no=%s FOR UPDATE", (case_no,))
            cursor.fetchall()
        cursor.execute(
            "SELECT o.obligation_identity,o.obligation_type,o.direction,o.due_date,o.status,"
            "o.amount_due_ntd,o.projection_version,e.after_amount_ntd,"
            "COALESCE(a.aggregate_version,0) AS account_version,c.name AS client_name,"
            "h.confirmation_kind,h.amount_snapshot_ntd,"
            "h.current_event_id AS historical_event,"
            "COALESCE((SELECT SUM(n.amount_ntd) FROM client_finance_noncash_events n WHERE n.target_identity=o.obligation_identity),0) AS recognized_ntd "
            "FROM client_obligations o JOIN client_obligation_events e ON e.id=o.current_event_id "
            "JOIN orders r ON r.case_no=o.case_no JOIN clients c ON c.id=r.client_id "
            "LEFT JOIN client_finance_accounts a ON a.case_no=o.case_no "
            "LEFT JOIN historical_client_payment_projections h ON h.obligation_identity=o.obligation_identity "
            "AND h.amount_snapshot_ntd=o.amount_due_ntd AND h.obligation_projection_version=o.projection_version "
            "WHERE o.case_no=%s AND o.status<>'cancelled' ORDER BY o.obligation_identity" + lock, (case_no,),
        )
        obligations = cursor.fetchall()
        cursor.execute(
            "SELECT l.id,l.entry_type,l.occurred_on,l.reversal_of_entry_id,"
            "base.entry_type AS reversed_type,x.obligation_identity,x.amount_ntd,b.format_id,l.reconciliation_reference,b.summary,"
            "CASE WHEN l.entry_type IN ('refund','subsidy_return','subsidy_advance') THEN l.amount_ntd ELSE NULL END AS bank_amount_ntd,"
            "CASE WHEN l.entry_type IN ('refund','subsidy_return','subsidy_advance') THEN GREATEST(0,"
            "(SELECT SUM(all_allocations.amount_ntd) FROM client_ledger_obligation_allocations all_allocations "
            "WHERE all_allocations.ledger_entry_id=l.id)-l.amount_ntd) ELSE NULL END AS transfer_fee_ntd "
            "FROM client_ledger_entries l JOIN client_ledger_obligation_allocations x ON x.ledger_entry_id=l.id "
            "LEFT JOIN client_ledger_entries base ON base.id=l.reversal_of_entry_id "
            "LEFT JOIN finance_import_rows b ON b.id=l.finance_import_row_id "
            "WHERE l.case_no=%s ORDER BY l.id,x.allocation_ordinal" + lock, (case_no,),
        )
        allocations = cursor.fetchall()
        cursor.execute(
            "SELECT d.receivable_obligation_identity,d.overage_amount_ntd "
            "FROM client_receipt_overage_dispositions d WHERE d.case_no=%s "
            "AND NOT EXISTS(SELECT 1 FROM client_ledger_entries r WHERE r.reversal_of_entry_id=d.receipt_ledger_entry_id)" + lock,
            (case_no,),
        )
        overages = cursor.fetchall()
        cursor.execute(
            "SELECT recovery.refund_obligation_identity AS receivable_obligation_identity,"
            "event.after_amount_ntd AS overage_amount_ntd "
            "FROM client_over_refund_recoveries recovery "
            "JOIN client_over_refund_recovery_events event ON event.recovery_identity=recovery.recovery_identity "
            "AND event.event_type='established' WHERE recovery.case_no=%s "
            "AND NOT EXISTS (SELECT 1 FROM client_ledger_entries reversal "
            "WHERE reversal.reversal_of_entry_id=recovery.refund_ledger_entry_id)" + lock,
            (case_no,),
        )
        refund_overages = cursor.fetchall()
        cursor.execute('SELECT r.*,e.after_amount_ntd original,c.name client_name,COALESCE((SELECT SUM(x.before_amount_ntd-x.after_amount_ntd) FROM client_over_refund_recovery_events x WHERE x.recovery_identity=r.recovery_identity AND x.event_type=%s),0) collected,'
            'COALESCE((SELECT SUM(n.amount_ntd) FROM client_finance_noncash_events n WHERE n.target_identity=r.recovery_identity),0) recognized '
            'FROM client_over_refund_recoveries r JOIN client_over_refund_recovery_events e ON e.recovery_identity=r.recovery_identity AND e.event_type=%s '
            'JOIN orders o ON o.case_no=r.case_no JOIN clients c ON c.id=o.client_id WHERE r.case_no=%s ORDER BY r.recovery_identity',('collected','established',case_no))
        recovery_rows=cursor.fetchall()
        cursor.execute('SELECT e.id,e.recovery_identity,e.before_amount_ntd-e.after_amount_ntd amount,l.occurred_on,b.format_id '
            'FROM client_over_refund_recovery_events e JOIN client_over_refund_recoveries r ON r.recovery_identity=e.recovery_identity '
            'JOIN client_ledger_entries l ON l.id=e.receipt_ledger_entry_id LEFT JOIN finance_import_rows b ON b.id=e.finance_import_row_id '
            "WHERE r.case_no=%s AND e.event_type='collected' ORDER BY e.id",(case_no,))
        recovery_transactions=cursor.fetchall()
    sums, transactions = {}, []
    for row in allocations:
        kind = row["entry_type"]
        if kind not in {"receipt", "refund", "subsidy_return", "subsidy_advance", "reversal", "subsidy_return_reversal"}:
            continue
        if kind in {"reversal", "subsidy_return_reversal"} and row["reversed_type"] not in {"receipt", "refund", "subsidy_return", "subsidy_advance"}:
            continue
        identity = row["obligation_identity"]
        amount = int(row["amount_ntd"]) * (-1 if kind in {"reversal", "subsidy_return_reversal"} else 1)
        sums[identity] = sums.get(identity, 0) + amount
        bank = "manual" if ((row.get("reconciliation_reference") or "").startswith("manual") or row.get("summary") == "人工補登") else row["format_id"]
        transactions.append(ClientAccountingTransaction(
            f"client-entry:{row['id']}:{identity}", identity, str(row["occurred_on"]), kind,
            amount, bank,
            None if row.get('bank_amount_ntd') is None else int(row['bank_amount_ntd']),
            None if row.get('transfer_fee_ntd') is None else int(row['transfer_fee_ntd']),
        ))
    allocated = dict(sums)
    for row in (*overages, *refund_overages):
        identity = row["receivable_obligation_identity"]
        sums[identity] = sums.get(identity, 0) + int(row["overage_amount_ntd"])
    labels = {"deposit": "訂金", "first": "第一期", "second": "第二期", "refund": "客戶退款", "subsidy_return": "補助退款／工會代墊", "adjustment": "帳務調整"}
    items = []
    for row in obligations:
        identity = row["obligation_identity"]
        # Client obligations are remaining-balance projections, including after
        # date-only owner events. Nominal amount is remaining plus effective
        # allocated cash; explicit surplus is displayed only in actual cash.
        recognized = int(row.get('recognized_ntd') or 0)
        expected = int(row["amount_due_ntd"]) + allocated.get(identity, 0) + recognized
        if row['status']=='settled':
            expected = max(expected,int(row['after_amount_ntd']))
        paid = sums.get(identity, 0)
        if row["confirmation_kind"] == "paid":
            paid += int(row["amount_snapshot_ntd"])
        label = labels.get(row["obligation_type"], "帳務款項")
        if identity.startswith("client-cancellation:"):
            label = "取消結算退款" if row["direction"] == "payable_to_client" else "取消結算補收"
        items.append(ClientAccountingItem(
            identity, "receivable" if row["direction"] == "receivable_from_client" else "payable",
            label, str(row["client_name"]), expected,
            paid, identity in sums or row["confirmation_kind"] == "paid",
            f"{row['account_version']}:{row['projection_version']}:{row['historical_event'] or 0}",
            None if row["due_date"] is None else str(row["due_date"]),
            settled=row["confirmation_kind"] == "settled" or row["status"] == "settled",
            recognized_ntd=recognized,
            payment_stage=row["obligation_type"] if row["obligation_type"] in {"deposit", "first", "second"} else None,
        ))
    valid = {item.identity for item in items}
    for row in recovery_rows:
        items.append(ClientAccountingItem(row['recovery_identity'],'receivable','客戶退款超付追償',row['client_name'],int(row['original']),int(row['collected']),int(row['collected'])>0,
            f"recovery:{row['projection_version']}",None,settled=row['status'] in ('recovered','adjusted','settled','cancelled'),recognized_ntd=int(row['recognized'])))
    transactions.extend(ClientAccountingTransaction(f"client-recovery:{r['id']}",r['recovery_identity'],str(r['occurred_on']),'receipt',int(r['amount']),r['format_id']) for r in recovery_transactions)
    valid.update(row['recovery_identity'] for row in recovery_rows)
    return tuple(items), tuple(row for row in transactions if row.item_identity in valid)
