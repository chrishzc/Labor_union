"""Preview and allocate annual non-citizen case numbers."""

from datetime import datetime

from domains.case_import.non_citizen_registration import non_citizen_case_number
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationConflictError
from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account


def _lock_non_citizen_case_year(cursor, year: int) -> int:
    cursor.execute(
        "INSERT INTO non_citizen_case_sequences (roc_year,next_sequence) VALUES (%s,1) "
        "ON DUPLICATE KEY UPDATE roc_year=VALUES(roc_year)", (year,),
    )
    cursor.execute("SELECT next_sequence FROM non_citizen_case_sequences WHERE roc_year=%s FOR UPDATE", (year,))
    row = cursor.fetchone()
    return int(row["next_sequence"] if isinstance(row, dict) else row[0])


def preview_non_citizen_case_number(connection, approved_at: datetime) -> tuple[str, str]:
    year = approved_at.astimezone(TAIPEI_TIME_ZONE).year - 1911
    with connection.cursor() as cursor:
        cursor.execute("SELECT next_sequence FROM non_citizen_case_sequences WHERE roc_year=%s", (year,))
        row = cursor.fetchone()
        sequence = int(row["next_sequence"] if isinstance(row, dict) else row[0]) if row else 1
        return _next_available(cursor, approved_at, sequence, for_update=False)[1:]


def allocate_non_citizen_case_number(connection, approved_at: datetime) -> str:
    year = approved_at.astimezone(TAIPEI_TIME_ZONE).year - 1911
    with connection.cursor() as cursor:
        sequence = _lock_non_citizen_case_year(cursor, year)
        sequence, case_no, _ = _next_available(cursor, approved_at, sequence, for_update=True)
        cursor.execute(
            "UPDATE non_citizen_case_sequences SET next_sequence=%s WHERE roc_year=%s", (sequence + 1, year),
        )
    return case_no


def _next_available(cursor, approved_at, start, *, for_update):
    lock = " FOR UPDATE" if for_update else ""
    for sequence in range(start, 500):
        case_no = non_citizen_case_number(approved_at, sequence)
        account = build_client_virtual_account(case_no)
        cursor.execute("SELECT 1 FROM clients WHERE case_no=%s LIMIT 1" + lock, (case_no,))
        if cursor.fetchone() is not None:
            continue
        citizen_case_no = f"{case_no[1:4]}000{account[-3:]}"
        cursor.execute("SELECT 1 FROM orders WHERE case_no IN (%s,%s) LIMIT 1" + lock, (case_no, citizen_case_no))
        if cursor.fetchone() is not None:
            continue
        cursor.execute(
            "SELECT 1 FROM client_legacy_virtual_accounts WHERE virtual_account=%s LIMIT 1" + lock,
            (account,),
        )
        if cursor.fetchone() is None:
            return sequence, case_no, account
    raise ProvisionalRegistrationConflictError("non_citizen_case_sequence_exhausted")
