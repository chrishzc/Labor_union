"""MySQL adapter for the singleton Hsinchu City Government payer master."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from domains.government_subsidy.payer_master import (
    PAYER_IDENTITY, PAYER_NAME, GovernmentPayerMaster, GovernmentPayerMasterError,
    GovernmentRefundAccount, GovernmentRefundAccountVersion,
)


class MySqlGovernmentPayerMasterRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_master(self, *, lock: bool) -> GovernmentPayerMaster:
        clause = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT payer_identity,payer_name FROM government_payers WHERE payer_identity=%s" + clause, (PAYER_IDENTITY,))
            payer = cursor.fetchone()
            if payer is None:
                raise GovernmentPayerMasterError("government_payer_not_found")
            cursor.execute(_ACTIVE_ACCOUNT_SQL + clause, (PAYER_IDENTITY,))
            row = cursor.fetchone()
        return GovernmentPayerMaster(PAYER_IDENTITY, PAYER_NAME, _account_version(row))

    def append_account_version(self, account: GovernmentRefundAccount, actor_id: str) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute(_VERSION_SQL + " FOR UPDATE", (PAYER_IDENTITY, account.effective_from))
            existing = cursor.fetchone()
            if existing is not None:
                if _same_account(existing, account):
                    return False
                raise GovernmentPayerMasterError("government_payer_account_effective_date_conflict")
            cursor.execute(_ACTIVE_ACCOUNT_SQL + " FOR UPDATE", (PAYER_IDENTITY,))
            previous = cursor.fetchone()
            if previous is not None:
                cursor.execute(_CLOSE_PREVIOUS_SQL, (account.effective_from - timedelta(days=1), int(previous["id"])))
                if cursor.rowcount != 1:
                    raise GovernmentPayerMasterError("government_payer_account_version_conflict")
            cursor.execute(_INSERT_ACCOUNT_SQL, _account_values(account, actor_id))
        return True

    def account_display(self, account_number: str) -> str:
        return "*" * max(0, len(account_number) - 4) + account_number[-4:]


_ACTIVE_ACCOUNT_SQL = """
SELECT id,bank_code,account_number,account_name,effective_from,effective_until,reason,evidence_reference
FROM government_payer_receiving_accounts
WHERE payer_identity=%s AND effective_until IS NULL
ORDER BY effective_from DESC LIMIT 1
"""
_VERSION_SQL = "SELECT bank_code,account_number,account_name,reason,evidence_reference FROM government_payer_receiving_accounts WHERE payer_identity=%s AND effective_from=%s"
_CLOSE_PREVIOUS_SQL = "UPDATE government_payer_receiving_accounts SET effective_until=%s WHERE id=%s AND effective_until IS NULL"
_INSERT_ACCOUNT_SQL = """
INSERT INTO government_payer_receiving_accounts
(payer_identity,bank_code,account_number,account_name,effective_from,effective_until,reason,evidence_reference,created_by)
VALUES (%s,%s,%s,%s,%s,NULL,%s,%s,%s)
"""


def _account_version(row) -> GovernmentRefundAccountVersion | None:
    if row is None:
        return None
    return GovernmentRefundAccountVersion(
        GovernmentRefundAccount(row["bank_code"], row["account_number"], row["account_name"], row["effective_from"], row["reason"], row["evidence_reference"]),
        row["effective_until"],
    )


def _same_account(row, account) -> bool:
    return all(str(row[key]) == value for key, value in {
        "bank_code": account.bank_code, "account_number": account.account_number,
        "account_name": account.account_name, "reason": account.reason,
        "evidence_reference": account.evidence_reference,
    }.items())


def _account_values(account, actor_id):
    return (PAYER_IDENTITY, account.bank_code, account.account_number, account.account_name,
            account.effective_from, account.reason, account.evidence_reference, actor_id)
