"""Allocate an annual sequence in the caller's existing approval transaction."""

from datetime import datetime

from domains.case_import.non_citizen_registration import non_citizen_case_number
from shared_kernel.clock import TAIPEI_TIME_ZONE


def allocate_non_citizen_case_number(connection, approved_at: datetime) -> str:
    year = approved_at.astimezone(TAIPEI_TIME_ZONE).year - 1911
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO non_citizen_case_sequences (roc_year,next_sequence) VALUES (%s,1) "
            "ON DUPLICATE KEY UPDATE roc_year=VALUES(roc_year)", (year,),
        )
        cursor.execute("SELECT next_sequence FROM non_citizen_case_sequences WHERE roc_year=%s FOR UPDATE", (year,))
        row = cursor.fetchone()
        sequence = int(row["next_sequence"] if isinstance(row, dict) else row[0])
        case_no = non_citizen_case_number(approved_at, sequence)
        cursor.execute("UPDATE non_citizen_case_sequences SET next_sequence=next_sequence+1 WHERE roc_year=%s", (year,))
    return case_no
