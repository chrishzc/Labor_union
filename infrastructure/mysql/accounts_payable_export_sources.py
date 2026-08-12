"""MySQL root-fact sources for the accounts-payable export."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from domains.staff_payables.reconciliation import StaffPayableStatus
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.accounts_payable_export import (
    ClientRefundExportFact,
    GovernmentOverpaymentReturnExportFact,
    StaffPayableExportFact,
)


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
        self._connection.rollback()


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
        return tuple(_staff_fact(row) for row in rows)


class MySqlClientRefundExportSource:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(
        self,
        target_payment_date: date,
    ) -> tuple[ClientRefundExportFact, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_CLIENT_REFUNDS_SQL, (target_payment_date,))
            rows = tuple(cursor.fetchall())
        return tuple(_refund_fact(row) for row in rows)


class MySqlGovernmentOverpaymentReturnExportSource:
    def __init__(self, connection) -> None:
        self._connection = connection

    def load(
        self, target_payment_date: date
    ) -> tuple[GovernmentOverpaymentReturnExportFact, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_GOVERNMENT_RETURNS_SQL, (target_payment_date,))
            rows = tuple(cursor.fetchall())
        return tuple(_government_return_fact(row) for row in rows)


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


def _government_return_fact(row) -> GovernmentOverpaymentReturnExportFact:
    return GovernmentOverpaymentReturnExportFact(
        payable_identity=str(row["payable_identity"]),
        overpayment_identity=str(row["overpayment_identity"]),
        recipient_name=_clean_text(row["agency_name"]),
        bank_code=_clean_text(row["bank_code"]),
        bank_account=_clean_text(row["account_display"]),
        amount=MoneyNTD(_integer(row["remaining_amount_ntd"], "government return")),
        payment_date=_date_value(row["due_date"]),
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
LEFT JOIN staff_bank_accounts bank_accounts
  ON bank_accounts.staff_id = obligations.staff_id
 AND bank_accounts.is_primary = 1
WHERE obligations.due_date = %s
  AND obligations.direction = 'payable_to_staff'
  AND obligations.status <> 'cancelled'
  AND obligations.amount_due_ntd > 0
  AND COALESCE(projection.status, 'payable') IN ('payable', 'partially_paid')
GROUP BY obligations.obligation_identity,
         obligations.case_no,
         obligations.staff_id,
         staff.name,
         obligations.amount_due_ntd,
         obligations.due_date,
         projection.status
ORDER BY obligations.staff_id, obligations.obligation_identity
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
WHERE obligations.due_date = %s
  AND obligations.direction = 'payable_to_client'
  AND obligations.status <> 'cancelled'
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


_GOVERNMENT_RETURNS_SQL = """
SELECT payable_identity,overpayment_identity,agency_name,bank_code,account_display,
       remaining_amount_ntd,due_date
FROM government_overpayment_return_payables
WHERE due_date = %s
  AND status = 'payable'
  AND remaining_amount_ntd > 0
ORDER BY due_date,payable_identity
"""


__all__ = [
    "MySqlClientRefundExportSource",
    "MySqlGovernmentOverpaymentReturnExportSource",
    "MySqlReadOnlySnapshot",
    "MySqlStaffPayableExportSource",
]
