"""Trusted manual identity evidence bound to a command and exact source row."""
import json


def manual_source_matches(cursor, row, *, case_no, direction, obligations):
    references = row.get("bank_references") or {}
    if isinstance(references, str):
        references = json.loads(references)
    proof = references.get("manual_supplement")
    if not isinstance(proof, dict):
        return False
    if (proof.get("case_no") != case_no or proof.get("direction") != direction
            or tuple(proof.get("obligations", ())) != tuple(obligations)):
        return False
    cursor.execute("SELECT command_digest,result_identity,actor FROM finance_statement_commands "
                   "WHERE idempotency_key=%s", (proof.get("key"),))
    receipt = cursor.fetchone()
    return bool(receipt and receipt["command_digest"] == proof.get("digest")
                and receipt["result_identity"] == f"manual:{row['id']}"
                and receipt["actor"] == proof.get("actor"))
