"""Read the durable shared FAQ activation evidence for the selected database."""

from __future__ import annotations

import json
import re


READY_KEY = "migration:shared-line-faq:reader-ready:v1"
READY_CONTRACT = "shared-line-faq-reader-ready/v1"
_SHA256 = re.compile(r"[0-9a-f]{64}")


def shared_faq_ready_fingerprint(connection) -> str | None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT command_fingerprint,receipt_json FROM knowledge_apply_receipts "
            "WHERE idempotency_key=%s",
            (READY_KEY,),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    receipt = row["receipt_json"]
    try:
        if isinstance(receipt, (str, bytes)):
            receipt = json.loads(receipt)
        fingerprint = receipt["dataset_fingerprint"]
        if (
            receipt["contract"] != READY_CONTRACT
            or _SHA256.fullmatch(fingerprint) is None
            or fingerprint != row["command_fingerprint"]
        ):
            raise ValueError("invalid ready receipt")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("faq_cutover_ready_receipt_invalid") from error
    return fingerprint


def shared_faq_reader_ready(connection) -> bool:
    return shared_faq_ready_fingerprint(connection) is not None
