"""MySQL root-fact sources for the accounts-payable export."""

from __future__ import annotations

from datetime import date
from calendar import monthrange
from decimal import Decimal

from domains.staff_payables.reconciliation import StaffPayableStatus
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.accounts_payable_export import CaseStaffPayableAuditItem, ClientRefundExportFact, StaffPayableExportFact
from infrastructure.mysql.order_terms_read_model import select_current_assignments, select_scheduling_aggregate


class MySqlReadOnlySnapshot:
    def __init__(self, connection) -> None:
        self._connection = connection

    def __enter__(self):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
            )
            cursor.execute(
                "START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY"
            )
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        # The caller owns snapshot finalization.  This adapter only establishes
        # the read view and must not decide transaction success or failure.
        return None


class MySqlStaffPayableExportSource:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(
        self,
        target_payment_date: date,
    ) -> tuple[StaffPayableExportFact, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_STAFF_PAYABLES_SQL, (target_payment_date,))
            rows = tuple(cursor.fetchall())
        facts = tuple(_staff_fact(row) for row in rows)
        return tuple(sorted(facts, key=lambda item: (item.staff_id, item.obligation_identity)))

    def load_case(
        self, case_no: str, target_payment_date: date
    ) -> tuple[CaseStaffPayableAuditItem, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_STAFF_PAYABLE_CASE_AUDIT_SQL, (case_no,))
            formal_rows = tuple(cursor.fetchall())
            cursor.execute(_STAFF_PAYABLE_CASE_ORDER_FACTS_SQL, (case_no,))
            order_rows = tuple(cursor.fetchall())
            items = tuple(_formal_case_audit_item(row, target_payment_date) for row in formal_rows)
            if not order_rows:
                return items
            aggregate = select_scheduling_aggregate(cursor, case_no, lock=False)
            assignments = select_current_assignments(cursor, case_no, aggregate["effective_generation_id"])
            covered_staff = {item.staff_id for item in items}
            missing = tuple({int(assignment["staff_id"]): assignment for assignment in assignments
                             if int(assignment["staff_id"]) not in covered_staff}.values())
            names = {}
            if missing:
                cursor.execute("SELECT id,name FROM staff WHERE id IN (" + ",".join("%s" for _ in missing) + ")",
                               tuple(item["staff_id"] for item in missing))
                names = {int(row["id"]): row["name"] for row in cursor.fetchall()}
        return items + tuple(_missing_case_audit_item({**row, "staff_id": assignment["staff_id"] if assignment else None,
            "recipient_name": names.get(int(assignment["staff_id"])) if assignment else None})
            for row in order_rows for assignment in (missing or (() if items else (None,))))


class MySqlClientRefundExportSource:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(
        self,
        target_payment_date: date,
    ) -> tuple[ClientRefundExportFact, ...]:
        with self._connection.cursor() as cursor:
            month_end = target_payment_date.replace(
                day=monthrange(target_payment_date.year, target_payment_date.month)[1]
            )
            cursor.execute(_CLIENT_REFUNDS_SQL, (month_end,))
            rows = tuple(cursor.fetchall())
        return tuple(_refund_fact(row) for row in rows)




def _staff_fact(row) -> StaffPayableExportFact:
    status = _staff_status(row)
    bank_code = _canonical_bank_value(row.get("bank_code"), status)
    bank_account = _canonical_bank_value(row.get("account_no"), status)
    return StaffPayableExportFact(
        obligation_identity=str(row["obligation_identity"]),
        case_no=str(row["case_no"]),
        staff_id=_integer(row["staff_id"], "staff id"),
        recipient_name=_clean_text(row.get("recipient_name")) or "missing",
        bank_code=bank_code,
        bank_account=bank_account,
        amount=MoneyNTD(_integer(row["export_amount_ntd"], "staff payable")),
        payment_date=_date_value(row["due_date"]),
        status=status,
        recipient_identity_card=_clean_text(row.get("identity_card")),
    )


def _formal_case_audit_item(row, target_payment_date: date) -> CaseStaffPayableAuditItem:
    due_date = row.get("due_date")
    payout_status = str(row.get("payout_status") or "payable")
    historical_confirmation = row.get("historical_confirmation_kind")
    status = _staff_status(row)
    if historical_confirmation is not None or payout_status == "completed":
        disposition, reason = "paid_or_settled", "已有有效付款／結清證據，不列入待付清冊。"
    elif status not in {StaffPayableStatus.PAYABLE, StaffPayableStatus.PARTIALLY_PAID}:
        disposition, reason = "blocked", "現行付款狀態或受款資料尚有 blocker。"
    elif due_date is None:
        disposition, reason = "date_not_formed", "月嫂應付日尚未形成。"
    elif _date_value(due_date) == target_payment_date:
        disposition, reason = "selected_month", "列入所選付款月份。"
    else:
        disposition, reason = "other_month", "案件屬於其他付款月份。"
    return CaseStaffPayableAuditItem(
        case_no=str(row["case_no"]),
        staff_id=_integer(row["staff_id"], "staff id"),
        recipient_name=_clean_text(row.get("recipient_name")) or None,
        obligation_identity=str(row["obligation_identity"]),
        amount_due=MoneyNTD(_integer(row["amount_due_ntd"], "staff payable")),
        balance=MoneyNTD(0 if historical_confirmation is not None else _integer(row["export_amount_ntd"], "staff payable balance")),
        order_due_date=row.get("order_due_date"),
        effective_due_date=due_date,
        source="formal_obligation",
        disposition=disposition,
        reason=reason,
        payment_status=(historical_confirmation if historical_confirmation is not None else
                        "paid" if payout_status in {"completed", "recovery_required"}
                            or _integer(row["export_amount_ntd"], "staff payable balance") < 0 else
                        "partially_paid" if payout_status == "partially_paid" else "pending"),
    )


def _missing_case_audit_item(row) -> CaseStaffPayableAuditItem:
    due_date = row.get("staff_payment_due_date")
    if due_date is None:
        disposition, reason = "date_not_formed", "尚未建立月嫂應付帳務與應付日，請由服務天數帳務流程補建。"
    else:
        disposition, reason = "missing_calculation_basis", "案件已有應付日，但尚未建立月嫂應付帳務；請由服務天數帳務流程補建。"
    staff_id = row.get("staff_id")
    return CaseStaffPayableAuditItem(
        case_no=str(row["case_no"]),
        staff_id=None if staff_id is None else _integer(staff_id, "staff id"),
        recipient_name=_clean_text(row.get("recipient_name")) or None,
        obligation_identity=None,
        amount_due=None,
        balance=None,
        order_due_date=due_date,
        effective_due_date=None,
        source="order_facts",
        disposition=disposition,
        reason=reason,
    )


def _staff_status(row) -> StaffPayableStatus:
    projected_status = StaffPayableStatus(str(row["payout_status"]))
    if projected_status not in {StaffPayableStatus.PAYABLE, StaffPayableStatus.PARTIALLY_PAID}:
        return projected_status
    if _integer(row["primary_account_count"], "primary account count") != 1:
        return StaffPayableStatus.ANOMALY
    if not _clean_text(row.get("recipient_name")):
        return StaffPayableStatus.ANOMALY
    if not _clean_text(row.get("bank_code")):
        return StaffPayableStatus.ANOMALY
    if not _clean_text(row.get("account_no")):
        return StaffPayableStatus.ANOMALY
    return projected_status


# One row is materialized cohesively so payable/anomaly cannot use different facts.
def _refund_fact(row) -> ClientRefundExportFact:
    amount_due = _integer(row["amount_due_ntd"], "client refund")
    net_refunded = _integer(row["net_refunded_ntd"], "net refunded")
    bank_code = _clean_text(row.get("refund_bank_code"))
    bank_account = _clean_text(row.get("refund_account_no"))
    recipient_name = _clean_text(row.get("recipient_name"))
    anomaly = _refund_has_anomaly(
        amount_due,
        net_refunded,
        recipient_name,
        bank_code,
        bank_account,
    )
    return ClientRefundExportFact(
        obligation_identity=str(row["obligation_identity"]),
        case_no=str(row["case_no"]),
        recipient_name=recipient_name or "missing",
        bank_code=bank_code or "missing",
        bank_account=bank_account or "missing",
        amount=MoneyNTD(amount_due),
        payment_date=_date_value(row["due_date"]),
        payable=not anomaly,
        anomaly=anomaly,
        refund_type=_export_refund_type(row["obligation_type"]),
    )


def _refund_has_anomaly(
    amount_due: int,
    net_refunded: int,
    recipient_name: str,
    bank_code: str,
    bank_account: str,
) -> bool:
    if not recipient_name or not bank_code or not bank_account:
        return True
    # The projection stores the remaining amount.  A prior canonical partial
    # refund is therefore valid and the remaining amount must reappear next month.
    return net_refunded < 0


def _export_refund_type(obligation_type: object) -> str:
    if obligation_type == "subsidy_return":
        return "subsidy_return"
    if obligation_type == "refund":
        return "customer_refund"
    raise ValueError("client payable obligation type is not exportable")


def _canonical_bank_value(value, status: StaffPayableStatus) -> str:
    text = _clean_text(value)
    if text:
        return text
    if status is StaffPayableStatus.ANOMALY:
        return ""
    raise RuntimeError("payable staff bank fact is missing")


def _clean_text(value) -> str:
    return str(value or "").strip()


def _integer(value, field_name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    raise TypeError(f"{field_name} must be an integer")


def _date_value(value) -> date:
    if isinstance(value, date):
        return value
    raise TypeError("payment date must be a date")


_STAFF_PAYABLES_SQL = """
SELECT obligations.obligation_identity,
       obligations.case_no,
       obligations.staff_id,
       staff.name AS recipient_name,
       staff.identity_card,
       obligations.amount_due_ntd,
       COALESCE(projection.balance_ntd, obligations.amount_due_ntd) AS export_amount_ntd,
       obligations.due_date,
       COALESCE(projection.status, 'payable') AS payout_status,
       COUNT(bank_accounts.id) AS primary_account_count,
       MAX(bank_accounts.bank_code) AS bank_code,
       MAX(bank_accounts.account_no) AS account_no
FROM staff_obligations obligations
JOIN staff ON staff.id = obligations.staff_id
LEFT JOIN staff_payable_projections projection
  ON projection.obligation_identity = obligations.obligation_identity
LEFT JOIN historical_staff_payout_projections historical_confirmation
  ON historical_confirmation.obligation_identity = obligations.obligation_identity
 AND historical_confirmation.amount_snapshot_ntd = obligations.amount_due_ntd
 AND historical_confirmation.obligation_payroll_version = obligations.payroll_version
LEFT JOIN staff_bank_accounts bank_accounts
  ON bank_accounts.staff_id = obligations.staff_id
 AND bank_accounts.is_primary = 1
WHERE obligations.due_date = %s
  AND obligations.direction = 'payable_to_staff'
  AND obligations.obligation_identity NOT LIKE 'staff-handover:%%'
  AND obligations.status <> 'cancelled'
  AND obligations.amount_due_ntd > 0
  AND COALESCE(projection.status, 'payable') IN ('payable', 'partially_paid')
  AND COALESCE(projection.balance_ntd, obligations.amount_due_ntd) > 0
  AND historical_confirmation.obligation_identity IS NULL
GROUP BY obligations.obligation_identity,
         obligations.case_no,
         obligations.staff_id,
         staff.name,
         obligations.amount_due_ntd,
         obligations.due_date,
         projection.balance_ntd,
         projection.status
ORDER BY obligations.staff_id, obligations.obligation_identity
"""


_STAFF_PAYABLE_CASE_AUDIT_SQL = """
SELECT obligations.obligation_identity,
       obligations.case_no,
       obligations.staff_id,
       staff.name AS recipient_name,
       staff.identity_card,
       COALESCE(projection.obligation_amount_ntd, obligations.amount_due_ntd) AS amount_due_ntd,
       COALESCE(projection.balance_ntd, obligations.amount_due_ntd) AS export_amount_ntd,
       obligations.due_date,
       COALESCE(orders.staff_payment_due_date, obligations.due_date) AS order_due_date,
       COALESCE(projection.status, 'payable') AS payout_status,
       historical_confirmation.confirmation_kind AS historical_confirmation_kind,
       COUNT(bank_accounts.id) AS primary_account_count,
       MAX(bank_accounts.bank_code) AS bank_code,
       MAX(bank_accounts.account_no) AS account_no
FROM staff_obligations obligations
JOIN orders ON orders.case_no = obligations.case_no
JOIN staff ON staff.id = obligations.staff_id
LEFT JOIN staff_payable_projections projection
  ON projection.obligation_identity = obligations.obligation_identity
LEFT JOIN historical_staff_payout_projections historical_confirmation
  ON historical_confirmation.obligation_identity = obligations.obligation_identity
 AND historical_confirmation.amount_snapshot_ntd = obligations.amount_due_ntd
 AND historical_confirmation.obligation_payroll_version = obligations.payroll_version
LEFT JOIN staff_bank_accounts bank_accounts
  ON bank_accounts.staff_id = obligations.staff_id
 AND bank_accounts.is_primary = 1
WHERE obligations.case_no = %s
  AND obligations.direction = 'payable_to_staff'
  AND obligations.obligation_identity NOT LIKE 'staff-handover:%%'
  AND obligations.status <> 'cancelled'
  AND obligations.amount_due_ntd > 0
GROUP BY obligations.obligation_identity,
         obligations.case_no,
         obligations.staff_id,
         staff.name,
         staff.identity_card,
         obligations.amount_due_ntd,
         projection.obligation_amount_ntd,
         obligations.due_date,
         orders.staff_payment_due_date,
         projection.balance_ntd,
         projection.status,
         historical_confirmation.confirmation_kind
ORDER BY obligations.staff_id, obligations.obligation_identity
"""


_STAFF_PAYABLE_CASE_ORDER_FACTS_SQL = """
SELECT orders.case_no,orders.staff_payment_due_date
FROM orders
WHERE orders.case_no = %s
"""


_CLIENT_REFUNDS_SQL = """
SELECT obligations.obligation_identity,
       obligations.case_no,
       obligations.obligation_type,
       clients.name AS recipient_name,
       obligations.amount_due_ntd,
       obligations.due_date,
       snapshot.bank_code AS refund_bank_code,
       snapshot.bank_account AS refund_account_no,
       COALESCE(
           SUM(
               CASE
                   WHEN ledger.entry_type IN (
                       'reversal',
                       'refund_reversal',
                       'subsidy_return_reversal',
                       'subsidy_advance_reversal'
                   )
                   THEN -allocations.amount_ntd
                   ELSE allocations.amount_ntd
               END
           ),
           0
       ) AS net_refunded_ntd
FROM client_obligations obligations
JOIN clients ON clients.case_no = obligations.case_no
LEFT JOIN client_refund_recipient_snapshots snapshot
  ON snapshot.refund_obligation_identity = obligations.obligation_identity
LEFT JOIN client_ledger_obligation_allocations allocations
  ON allocations.obligation_identity = obligations.obligation_identity
LEFT JOIN client_ledger_entries ledger
  ON ledger.id = allocations.ledger_entry_id
WHERE obligations.due_date <= %s
  AND obligations.direction = 'payable_to_client'
  AND obligations.status = 'open'
  AND obligations.amount_due_ntd > 0
GROUP BY obligations.obligation_identity,
         obligations.case_no,
         obligations.obligation_type,
         clients.name,
         obligations.amount_due_ntd,
         obligations.due_date,
         snapshot.bank_code,
         snapshot.bank_account
ORDER BY obligations.case_no, obligations.obligation_identity
"""




__all__ = ['MySqlClientRefundExportSource', 'MySqlReadOnlySnapshot', 'MySqlStaffPayableExportSource']
