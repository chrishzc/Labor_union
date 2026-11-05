"""One effective BeClass refund-account reader for financial snapshot writers."""
from __future__ import annotations

import json

from domains.case_import.refund_account import RefundAccount, effective_refund_account


def load_effective_refund_account(cursor, case_no: str) -> RefundAccount | None:
    cursor.execute(
        "SELECT br.refund_bank_code,br.refund_account_no,cs.effective_values_json "
        "FROM beclass_records br LEFT JOIN beclass_record_correction_states cs "
        "ON cs.beclass_record_id=br.id WHERE br.bound_case_no=%s ORDER BY br.id LIMIT 2",
        (case_no,),
    )
    rows = tuple(cursor.fetchall() or ())
    if len(rows) != 1:
        return None
    raw = rows[0].get("effective_values_json")
    try:
        corrections = raw if isinstance(raw, dict) else json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return None
    if not isinstance(corrections, dict):
        return None
    return effective_refund_account(rows[0], corrections)
